from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import json
import uuid
from typing import Optional
from app.services.orchestrator import orchestrate_vision_scan
from app.services.reconciler import reconcile_results
from app.services.portion import estimate_portion_weight
from app.services.nutrition import lookup_nutrition
from app.core.db import db
import logging

logger = logging.getLogger("kalories.scans")
router = APIRouter(prefix="/scans", tags=["scans"])

@router.post("")
async def post_scan(
    image: UploadFile = File(...),
    depth_map: Optional[UploadFile] = File(None),
    meta: str = Form(...)
):
    try:
        # 1. Parse metadata
        meta_dict = {}
        if meta:
            try:
                meta_dict = json.loads(meta)
            except Exception as e:
                logger.warning(f"Failed to parse meta JSON: {e}. Using empty dict.")
        
        # 2. Read image bytes
        image_bytes = await image.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Empty image upload")
            
        # 3. Read depth map bytes if available
        depth_bytes = None
        if depth_map:
            depth_bytes = await depth_map.read()

        # 4. Run vision models in parallel
        filename = getattr(image, "filename", "") or ""
        model_outputs = await orchestrate_vision_scan(image_bytes, filename=filename)

        # 5. Extract depth-derived weight if depth map is present
        primary_food = "healthy food"
        primary_density = None
        for model_name in ["gemma-4-E4B-it", "gemini-2.5-flash", "gemma-4-12b", "huggingface-qwen", "gpt-4o", "claude-sonnet-4-6"]:
            if model_outputs.get(model_name, {}).get("items"):
                first_item = model_outputs[model_name]["items"][0]
                primary_food = first_item.get("food", "healthy food")
                primary_density = first_item.get("density_g_cm3")
                break
            
        depth_weight_g = None
        depth_mm = meta_dict.get("depth_mm")
        
        if depth_bytes:
            depth_weight_g = estimate_portion_weight(depth_bytes, meta_dict, primary_food, primary_density)
            
        # 6. Reconcile results from models
        reconciled_items = reconcile_results(model_outputs, depth_weight_g)

        # 7. Run Stage 2: Nutrition calculation and libido analysis
        from app.services.orchestrator import run_nutrition_and_analysis_llm
        analysis_data = await run_nutrition_and_analysis_llm(reconciled_items)
        
        final_items = []
        total_kcal = 0.0
        total_protein = 0.0
        total_carbs = 0.0
        total_fat = 0.0
        total_fiber = 0.0
        
        # Map confidence values back from Call 1 reconciled output
        conf_map = {item["name"].lower(): item["confidence"] for item in reconciled_items}
        
        for item in analysis_data.get("items", []):
            name = item.get("food", "unknown")
            portion_g = item.get("portion_g", 150.0)
            kcal = item.get("kcal", 0.0)
            macros = item.get("macros", {})
            
            p = macros.get("protein", 0.0)
            c = macros.get("carbs", 0.0)
            f = macros.get("fat", 0.0)
            fib = macros.get("fiber", 0.0)
            
            total_kcal += kcal
            total_protein += p
            total_carbs += c
            total_fat += f
            total_fiber += fib
            
            confidence = conf_map.get(name.lower(), 0.85)
            
            final_items.append({
                "food": name,
                "portion_g": portion_g,
                "kcal": round(kcal, 1),
                "confidence": confidence,
                "macros": {
                    "protein": round(p, 1),
                    "carbs": round(c, 1),
                    "fat": round(f, 1),
                    "fiber": round(fib, 1)
                }
            })
            
        libido_analysis = analysis_data.get("libido_analysis", {
            "impact_percent": 0,
            "impact_direction": "neutral",
            "key_factors": []
        })

        scan_id = str(uuid.uuid4())
        status = "complete"

        # 8. Store results in MongoDB if available
        if db is not None:
            try:
                await db.scans.insert_one({
                    "_id": scan_id,
                    "status": status,
                    "meta": meta_dict,
                    "items_count": len(final_items),
                    "total_kcal": round(total_kcal, 1),
                    "libido_analysis": libido_analysis
                })
                await db.model_runs.insert_one({
                    "scan_id": scan_id,
                    "model_outputs": model_outputs
                })
                await db.scan_results.insert_one({
                    "scan_id": scan_id,
                    "items": final_items,
                    "total_kcal": round(total_kcal, 1),
                    "total_macros": {
                        "protein": round(total_protein, 1),
                        "carbs": round(total_carbs, 1),
                        "fat": round(total_fat, 1),
                        "fiber": round(total_fiber, 1)
                    },
                    "libido_analysis": libido_analysis
                })
                logger.info(f"Scan {scan_id} saved to database.")
            except Exception as dbe:
                logger.error(f"Error saving scan to MongoDB: {dbe}")

        # 9. Formulate response
        response_data = {
            "scan_id": scan_id,
            "status": status,
            "items": final_items,
            "total_kcal": round(total_kcal, 1),
            "total_macros": {
                "protein": round(total_protein, 1),
                "carbs": round(total_carbs, 1),
                "fat": round(total_fat, 1),
                "fiber": round(total_fiber, 1)
            },
            "libido_analysis": libido_analysis,
            "depth_mm": depth_mm,
            "model": "ensemble"
        }
        
        return response_data
        
    except ValueError as e:
        if "NOT_FOOD" in str(e):
            raise HTTPException(status_code=422, detail={
                "error": "NOT_FOOD",
                "message": "Please scan actual food. Non-food items cannot be processed."
            })
        logger.error(f"ValueError processing scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class CoachMessage(BaseModel):
    message: str

@router.post("/coach")
async def post_coach_message(payload: CoachMessage):
    try:
        from app.services.orchestrator import run_coach_chat_llm
        reply_data = await run_coach_chat_llm(payload.message)
        return reply_data
    except Exception as e:
        logger.error(f"Error in coach chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
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
        for model_name in ["gemini-2.5-flash", "huggingface-qwen", "gpt-4o", "claude-sonnet-4-6"]:
            if model_outputs.get(model_name, {}).get("items"):
                primary_food = model_outputs[model_name]["items"][0].get("food", "healthy food")
                break
            
        depth_weight_g = None
        depth_mm = meta_dict.get("depth_mm")
        
        if depth_bytes:
            depth_weight_g = estimate_portion_weight(depth_bytes, meta_dict, primary_food)
            
        # 6. Reconcile results from models
        reconciled_items = reconcile_results(model_outputs, depth_weight_g)

        # 7. Lookup nutrition data per item and compute values
        final_items = []
        total_kcal = 0.0
        total_protein = 0.0
        total_carbs = 0.0
        total_fat = 0.0
        total_fiber = 0.0

        for item in reconciled_items:
            name = item["name"]
            portion_g = item["portion_g"]
            confidence = item["confidence"]
            
            nutrition = await lookup_nutrition(name)
            
            kcal = (portion_g / 100.0) * nutrition["kcal"]
            protein = (portion_g / 100.0) * nutrition["protein"]
            carbs = (portion_g / 100.0) * nutrition["carbs"]
            fat = (portion_g / 100.0) * nutrition["fat"]
            fiber = (portion_g / 100.0) * nutrition["fiber"]
            
            total_kcal += kcal
            total_protein += protein
            total_carbs += carbs
            total_fat += fat
            total_fiber += fiber

            final_items.append({
                "food": name,
                "portion_g": portion_g,
                "kcal": round(kcal, 1),
                "confidence": confidence,
                "macros": {
                    "protein": round(protein, 1),
                    "carbs": round(carbs, 1),
                    "fat": round(fat, 1),
                    "fiber": round(fiber, 1)
                }
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
                    "total_kcal": round(total_kcal, 1)
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
                    }
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
            "depth_mm": depth_mm,
            "model": "ensemble"
        }
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error processing scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
import json
import uuid
import asyncio
from typing import Optional
from datetime import datetime
from app.services.orchestrator import orchestrate_vision_scan
from app.services.reconciler import reconcile_results
from app.services.portion import estimate_portion_weight
from app.services.nutrition import lookup_nutrition
from app.core.db import db
from app.core.auth import get_current_user
from app.core.config import settings
import logging

logger = logging.getLogger("kalories.scans")
router = APIRouter(prefix="/scans", tags=["scans"])

# In-memory scan database fallback (for when MongoDB is offline)
MOCK_SCANS_DB = {}

async def process_scan_background(
    scan_id: str,
    image_bytes: bytes,
    depth_bytes: Optional[bytes],
    meta_dict: dict,
    filename: str,
    username: str
):
    """
    Asynchronous background task to run the full vision & nutritional estimation pipeline.
    Saves final status and results to MongoDB (or in-memory mock store).
    """
    try:
        logger.info(f"Background scan {scan_id} initiated for user '{username}'.")
        
        # 1. Run vision models in parallel (Call 1)
        model_outputs = await orchestrate_vision_scan(image_bytes, filename=filename)

        # Check if vision scan detected non-food (error = True, error_code = NOT_FOOD)
        is_not_food = False
        error_msg = "Please scan actual food."
        for model_name, m_out in model_outputs.items():
            if m_out and m_out.get("error") and m_out.get("error_code") == "NOT_FOOD":
                is_not_food = True
                error_msg = m_out.get("error_message", "Please scan actual food. Non-food items cannot be processed.")
                break

        if is_not_food:
            raise ValueError(f"NOT_FOOD: {error_msg}")

        # 2. Extract depth-derived weight if depth map is present
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
            depth_weight_g = await asyncio.to_thread(estimate_portion_weight, depth_bytes, meta_dict, primary_food, primary_density)
            
        # 3. Reconcile results from models
        reconciled_items = reconcile_results(model_outputs, depth_weight_g)

        # 4. Run Stage 2: Nutrition calculation and libido analysis (Call 2 & 3)
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

        status = "complete"

        # 5. Store results atomically using transactions if MongoDB is available
        if db is not None:
            try:
                from app.core.db import transaction_session
                async with transaction_session() as session:
                    await db.scans.update_one(
                        {"_id": scan_id},
                        {
                            "$set": {
                                "status": status,
                                "items_count": len(final_items),
                                "total_kcal": round(total_kcal, 1),
                                "libido_analysis": libido_analysis
                            }
                        },
                        session=session
                    )
                    await db.model_runs.insert_one({
                        "scan_id": scan_id,
                        "model_outputs": model_outputs
                    }, session=session)
                    
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
                    }, session=session)
                logger.info(f"Scan {scan_id} fully processed and saved to database.")
            except Exception as dbe:
                logger.error(f"Error saving background scan results to MongoDB: {dbe}")
                if settings.ENVIRONMENT == "production":
                    raise dbe
        else:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Database connection offline during background scan save")
            # Fallback to local memory storage
            MOCK_SCANS_DB[scan_id] = {
                "scan_id": scan_id,
                "user_id": username,
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
            logger.info(f"Scan {scan_id} saved to mock in-memory database fallback.")

    except Exception as e:
        logger.error(f"Error processing background scan: {e}")
        err_msg = str(e)
        is_not_food = "NOT_FOOD" in err_msg
        clean_msg = err_msg.replace("NOT_FOOD: ", "") if is_not_food else err_msg
        
        if db is not None:
            try:
                await db.scans.update_one(
                    {"_id": scan_id},
                    {
                        "$set": {
                            "status": "failed",
                            "error": clean_msg,
                            "error_type": "NOT_FOOD" if is_not_food else "SYSTEM"
                        }
                    }
                )
            except Exception as dbe:
                logger.error(f"Failed to save error status to database: {dbe}")
                if settings.ENVIRONMENT == "production":
                    raise dbe
        else:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Database connection offline during background scan error save")
            MOCK_SCANS_DB[scan_id] = {
                "scan_id": scan_id,
                "user_id": username,
                "status": "failed",
                "error": clean_msg,
                "error_type": "NOT_FOOD" if is_not_food else "SYSTEM"
            }

@router.post("")
async def post_scan(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    depth_map: Optional[UploadFile] = File(None),
    meta: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Decoupled vision estimation endpoint.
    Saves an initial 'pending' record and schedules the heavy vision/nutrient pipeline in the background.
    """
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

        scan_id = str(uuid.uuid4())
        status = "pending"
        username = current_user["username"]

        # 4. Save initial pending state
        if db is not None:
            try:
                await db.scans.insert_one({
                    "_id": scan_id,
                    "user_id": username,
                    "status": status,
                    "meta": meta_dict,
                    "created_at": datetime.utcnow()
                })
                logger.info(f"Scan {scan_id} pending record saved to MongoDB.")
            except Exception as dbe:
                logger.error(f"Error creating scans collection record: {dbe}")
                if settings.ENVIRONMENT == "production":
                    raise HTTPException(status_code=503, detail="Database save failed")
        else:
            if settings.ENVIRONMENT == "production":
                raise HTTPException(status_code=503, detail="Database connection offline")
            MOCK_SCANS_DB[scan_id] = {
                "scan_id": scan_id,
                "user_id": username,
                "status": status,
                "meta": meta_dict
            }
            logger.info(f"Scan {scan_id} pending record saved to Mock DB.")

        # 5. Push task to BackgroundTasks worker
        filename = getattr(image, "filename", "") or ""
        background_tasks.add_task(
            process_scan_background,
            scan_id,
            image_bytes,
            depth_bytes,
            meta_dict,
            filename,
            username
        )

        return {
            "scan_id": scan_id,
            "status": status
        }

    except Exception as e:
        logger.error(f"Error initializing scan task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{scan_id}")
async def get_scan_status(
    scan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Polling endpoint to retrieve background scan status and reconciled results.
    """
    # 1. Fetch scan metadata from DB
    scan_record = None
    if db is not None:
        try:
            scan_record = await db.scans.find_one({"_id": scan_id, "user_id": current_user["username"]})
        except Exception as e:
            logger.error(f"Failed to lookup scan {scan_id} in MongoDB: {e}")
            if settings.ENVIRONMENT == "production":
                raise HTTPException(status_code=503, detail="Database read failed")
    else:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(status_code=503, detail="Database connection offline")
        scan_record = MOCK_SCANS_DB.get(scan_id)
        if scan_record and scan_record.get("user_id") != current_user["username"]:
            scan_record = None

    if not scan_record:
        raise HTTPException(status_code=404, detail="Scan not found.")

    status = scan_record.get("status")

    if status == "pending":
        return {
            "scan_id": scan_id,
            "status": "pending"
        }

    elif status == "failed":
        error_type = scan_record.get("error_type", "SYSTEM")
        error_msg = scan_record.get("error", "An unknown error occurred during scanning.")
        if error_type == "NOT_FOOD":
            raise HTTPException(status_code=422, detail={
                "error": "NOT_FOOD",
                "message": error_msg
            })
        raise HTTPException(status_code=500, detail=error_msg)

    elif status == "complete":
        # 2. Retrieve final results
        if db is not None:
            try:
                results = await db.scan_results.find_one({"scan_id": scan_id})
                if results:
                    return {
                        "scan_id": scan_id,
                        "status": "complete",
                        "items": results.get("items", []),
                        "total_kcal": results.get("total_kcal", 0.0),
                        "total_macros": results.get("total_macros", {}),
                        "libido_analysis": results.get("libido_analysis", {}),
                        "depth_mm": scan_record.get("meta", {}).get("depth_mm", 120),
                        "model": "ensemble"
                    }
            except Exception as e:
                logger.error(f"Failed to load scan results for {scan_id}: {e}")
                raise HTTPException(status_code=500, detail="Failed to load scan results.")
        else:
            return scan_record

    raise HTTPException(status_code=500, detail="Invalid scan status.")

@router.get("")
async def get_user_scans(
    current_user: dict = Depends(get_current_user),
    limit: int = 10
):
    """
    Retrieve history of completed food scans for the authenticated user.
    """
    try:
        username = current_user["username"]
        if db is not None:
            cursor = db.scans.find(
                {"user_id": username, "status": "complete"}
            ).sort("created_at", -1).limit(limit)
            scans = await cursor.to_list(length=limit)
            result = []
            for scan in scans:
                result.append({
                    "scan_id": scan.get("_id"),
                    "total_kcal": scan.get("total_kcal", 0.0),
                    "libido_analysis": scan.get("libido_analysis", {}),
                    "created_at": scan.get("created_at", datetime.utcnow()).isoformat()
                })
            result.reverse()
            return result
        else:
            user_scans = []
            for scan_id, scan in MOCK_SCANS_DB.items():
                if scan.get("user_id") == username and scan.get("status") == "complete":
                    user_scans.append({
                        "scan_id": scan_id,
                        "total_kcal": scan.get("total_kcal", 0.0),
                        "libido_analysis": scan.get("libido_analysis", {}),
                        "created_at": datetime.utcnow().isoformat()
                    })
            return user_scans[-limit:]
    except Exception as e:
        logger.error(f"Error fetching user scans: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class CoachMessage(BaseModel):
    message: str

@router.post("/coach")
async def post_coach_message(
    payload: CoachMessage,
    current_user: dict = Depends(get_current_user)
):
    """
    Coach endpoint protected by user authentication.
    """
    try:
        from app.services.orchestrator import run_coach_chat_llm
        reply_data = await run_coach_chat_llm(payload.message)
        return reply_data
    except Exception as e:
        logger.error(f"Error in coach chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import httpx
import logging
import redis.asyncio as aioredis
import json
import urllib.parse
from app.core.config import settings

logger = logging.getLogger("kalories.nutrition")

# Predefined fallback database per 100g
NUTRITION_MOCK_DB = {
    "rice": {"kcal": 130.0, "protein": 2.7, "carbs": 28.0, "fat": 0.3, "fiber": 0.4},
    "chicken": {"kcal": 165.0, "protein": 31.0, "carbs": 0.0, "fat": 3.6, "fiber": 0.0},
    "beef": {"kcal": 250.0, "protein": 26.0, "carbs": 0.0, "fat": 15.0, "fiber": 0.0},
    "salad": {"kcal": 15.0, "protein": 1.4, "carbs": 2.9, "fat": 0.2, "fiber": 1.3},
    "pasta": {"kcal": 131.0, "protein": 5.0, "carbs": 25.0, "fat": 1.1, "fiber": 1.2},
    "egg": {"kcal": 155.0, "protein": 13.0, "carbs": 1.1, "fat": 11.0, "fiber": 0.0},
    "oysters": {"kcal": 81.0, "protein": 9.0, "carbs": 5.0, "fat": 2.5, "fiber": 0.0},
    "apple": {"kcal": 52.0, "protein": 0.3, "carbs": 14.0, "fat": 0.2, "fiber": 2.4},
    "banana": {"kcal": 89.0, "protein": 1.1, "carbs": 23.0, "fat": 0.3, "fiber": 2.6},
    "bread": {"kcal": 265.0, "protein": 9.0, "carbs": 49.0, "fat": 3.2, "fiber": 2.7},
    "soup": {"kcal": 50.0, "protein": 1.5, "carbs": 8.0, "fat": 1.2, "fiber": 1.0},
    "potato": {"kcal": 77.0, "protein": 2.0, "carbs": 17.0, "fat": 0.1, "fiber": 2.2},
    "oats": {"kcal": 389.0, "protein": 16.9, "carbs": 66.3, "fat": 6.9, "fiber": 10.6},
    "oatmeal": {"kcal": 68.0, "protein": 2.4, "carbs": 12.0, "fat": 1.4, "fiber": 1.7},
    "watermelon": {"kcal": 30.0, "protein": 0.6, "carbs": 7.6, "fat": 0.2, "fiber": 0.4},
    "orange": {"kcal": 47.0, "protein": 0.9, "carbs": 12.0, "fat": 0.1, "fiber": 2.4},
    "paneer": {"kcal": 265.0, "protein": 18.0, "carbs": 1.2, "fat": 20.0, "fiber": 0.0},
    "roti": {"kcal": 120.0, "protein": 3.5, "carbs": 26.0, "fat": 0.4, "fiber": 4.0},
    "dal": {"kcal": 116.0, "protein": 9.0, "carbs": 20.0, "fat": 0.4, "fiber": 8.0},
    "biryani": {"kcal": 150.0, "protein": 7.0, "carbs": 22.0, "fat": 4.0, "fiber": 1.5}
}

redis_client = None

async def init_redis():
    global redis_client
    try:
        pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2
        )
        redis_client = aioredis.Redis(connection_pool=pool)
        await redis_client.ping()
        logger.info("✅ Redis async client connected successfully!")
    except Exception as e:
        logger.warning(f"⚠️ Redis connection failed: {e}. Caching will be disabled.")
        redis_client = None

async def close_redis():
    global redis_client
    if redis_client is not None:
        try:
            await redis_client.close()
            logger.info("Redis connection closed.")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")
        redis_client = None

async def lookup_nutrition(food_name: str) -> dict:
    """
    Looks up nutrition information (per 100g) for a food name from USDA FoodData Central.
    Utilizes Redis to cache lookup results (expires in 24 hours).
    Falls back to a local nutrition database if the API key is not present or if the request fails.
    """
    food_key = food_name.lower().strip()
    
    # 1. Try fetching from Redis cache first
    if redis_client is not None:
        try:
            cached_data = await redis_client.get(f"nutrition:{food_key}")
            if cached_data:
                logger.info(f"⚡ Redis cache hit for nutrition of '{food_name}'")
                return json.loads(cached_data)
        except Exception as ce:
            logger.warning(f"Failed to fetch from Redis cache: {ce}")

    # 2. Local fallback database lookup if Redis missed or failed
    local_match = None
    for k, v in NUTRITION_MOCK_DB.items():
        if k in food_key or food_key in k:
            local_match = v
            break
            
    fallback_data = local_match or {"kcal": 100.0, "protein": 5.0, "carbs": 15.0, "fat": 2.0, "fiber": 1.0}
    
    # 3. USDA API Query
    api_key = settings.USDA_API_KEY
    if not api_key:
        logger.info(f"No USDA API key. Using local lookup for '{food_name}'.")
        result_data = fallback_data
    else:
        try:
            safe_food_name = urllib.parse.quote(food_name)
            url = f"https://api.nal.usda.gov/fdc/v1/foods/search?api_key={api_key}&query={safe_food_name}&pageSize=1"
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    foods = data.get("foods", [])
                    if foods:
                        food_item = foods[0]
                        nutrients = food_item.get("foodNutrients", [])
                        
                        kcal = 0.0
                        protein = 0.0
                        carbs = 0.0
                        fat = 0.0
                        fiber = 0.0
                        
                        for n in nutrients:
                            name = n.get("nutrientName", "").lower()
                            value = float(n.get("value", 0.0))
                            
                            if "energy" in name or "kcal" in name:
                                unit = n.get("unitName", "").lower()
                                if unit == "kcal" or "kcal" in name:
                                    kcal = value
                            elif "protein" in name:
                                protein = value
                            elif "carbohydrate" in name:
                                carbs = value
                            elif "lipid" in name or "fat" in name:
                                if "saturated" not in name:
                                    fat = value
                            elif "fiber" in name:
                                fiber = value
                                
                        logger.info(f"USDA API match for '{food_name}': kcal={kcal}")
                        result_data = {
                            "kcal": kcal if kcal > 0 else fallback_data["kcal"],
                            "protein": protein,
                            "carbs": carbs,
                            "fat": fat,
                            "fiber": fiber
                        }
                    else:
                        logger.warning(f"USDA search returned empty for '{food_name}'.")
                        result_data = fallback_data
                else:
                    logger.warning(f"USDA search failed for '{food_name}'. Status={response.status_code}")
                    result_data = fallback_data
        except Exception as e:
            logger.error(f"Error querying USDA FDC for '{food_name}': {e}")
            result_data = fallback_data

    # 4. Save result to Redis cache (24 hours expiration)
    if redis_client is not None:
        try:
            await redis_client.setex(f"nutrition:{food_key}", 86400, json.dumps(result_data))
        except Exception as ce:
            logger.warning(f"Failed to write to Redis cache: {ce}")
            
    return result_data

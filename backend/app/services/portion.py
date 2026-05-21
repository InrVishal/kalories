import numpy as np
import logging

logger = logging.getLogger("kalories.portion")

def estimate_portion_weight(depth_bytes: bytes, meta: dict, food_name: str) -> float:
    """
    Parses a raw Depth16 map (uint16 in mm) and estimates weight in grams.
    Formula:
       Volume = sum(dz * dx * dy)
       Weight = Volume * Density
    """
    # Standard food densities (g/cm3)
    density_map = {
        "rice": 0.8,
        "chicken": 1.0,
        "beef": 1.05,
        "salad": 0.3,
        "pasta": 0.85,
        "egg": 1.0,
        "oysters": 1.1,
        "apple": 0.6,
        "banana": 0.9,
        "bread": 0.35,
        "soup": 1.0,
        "potato": 0.85
    }
    
    # Try finding density for food name (simple substring match)
    density = 0.9
    for k, v in density_map.items():
        if k in food_name.lower():
            density = v
            break
            
    if not depth_bytes:
        # Fallback if no depth map is provided
        logger.info("No depth map provided. Using default portion estimation.")
        return meta.get("fallback_portion_g", 150.0)

    try:
        # Parse depth map
        depth_data = np.frombuffer(depth_bytes, dtype=np.uint16)
        if len(depth_data) == 0:
            return 150.0
            
        # Filter out 0 (invalid depth values)
        valid_depths = depth_data[depth_data > 0]
        if len(valid_depths) == 0:
            return 150.0
            
        # Quick volume estimation:
        # We find the plate depth (e.g. 90th percentile) and food minimum depth (5th percentile)
        plate_depth = float(np.percentile(valid_depths, 90))
        food_min_depth = float(np.percentile(valid_depths, 5))
        
        height_mm = max(0.0, plate_depth - food_min_depth)
        
        # Approximate size of food item: assume radius of 50mm (10cm diameter circle)
        radius_mm = 50.0
        volume_mm3 = np.pi * (radius_mm ** 2) * height_mm
        volume_cm3 = volume_mm3 / 1000.0  # 1 mm3 = 0.001 cm3
        
        weight_g = volume_cm3 * density
        # Clamp weight between 20g and 1000g
        weight_g = max(20.0, min(1000.0, weight_g))
        
        logger.info(f"Portion calculated: plate_depth={plate_depth:.1f}mm, height={height_mm:.1f}mm, weight={weight_g:.1f}g")
        return round(weight_g, 1)
        
    except Exception as e:
        logger.error(f"Error parsing depth map: {e}. Falling back to default.")
        return 150.0

import logging

logger = logging.getLogger("kalories.reconciler")

def clean_food_name(name: str) -> str:
    name = name.lower().strip()
    # Simple normalization mapping
    mappings = {
        "chicken breast": ["grilled chicken breast", "grilled chicken", "chicken breast", "chicken", "roasted chicken", "baked chicken", "fried chicken"],
        "brown rice": ["brown rice", "cooked rice", "rice", "white rice", "steamed rice", "basmati rice", "jasmine rice"],
        "broccoli": ["steamed broccoli", "broccoli", "broccoli florets", "broccoli crowns", "roasted broccoli"],
        "salad": ["salad", "green salad", "mixed salad", "caesar salad", "garden salad"],
        "pasta": ["pasta", "spaghetti", "penne", "noodles", "macaroni", "fettuccine"],
        "bread": ["bread", "toast", "naan", "roti", "chapati", "pita"],
        "potato": ["potato", "mashed potato", "baked potato", "french fries", "fries", "roasted potato"],
        "egg": ["egg", "fried egg", "scrambled egg", "boiled egg", "omelette", "omelet"],
    }
    for standard_name, synonyms in mappings.items():
        if any(syn in name for syn in synonyms) or name in synonyms:
            return standard_name
    return name.title()

def reconcile_results(model_outputs: dict, depth_weight_g: float = None) -> list:
    """
    Groups outputs from multiple models, aggregates confidence, averages portion weights,
    and applies depth check if available.
    """
    logger.info("Reconciling outputs from models...")
    food_groups = {}
    
    for model_name, output in model_outputs.items():
        items = output.get("items", [])
        for item in items:
            raw_name = item.get("food", "")
            norm_name = clean_food_name(raw_name)
            portion_g = float(item.get("portion_g", 150.0))
            confidence = float(item.get("confidence", 0.9))
            
            if norm_name not in food_groups:
                food_groups[norm_name] = {
                    "raw_names": [],
                    "portions": [],
                    "confidences": [],
                    "models": []
                }
                
            food_groups[norm_name]["raw_names"].append(raw_name)
            food_groups[norm_name]["portions"].append(portion_g)
            food_groups[norm_name]["confidences"].append(confidence)
            food_groups[norm_name]["models"].append(model_name)

    reconciled_items = []
    
    for name, data in food_groups.items():
        total_conf = sum(data["confidences"])
        if total_conf > 0:
            weighted_portion = sum(p * c for p, c in zip(data["portions"], data["confidences"])) / total_conf
            avg_confidence = total_conf / len(data["confidences"])
        else:
            weighted_portion = sum(data["portions"]) / len(data["portions"])
            avg_confidence = 0.8
            
        reconciled_items.append({
            "name": name,
            "portion_g": round(weighted_portion, 1),
            "confidence": round(avg_confidence, 2),
            "source_models": data["models"]
        })
        
    # If a global depth weight is provided, scale all portions to sum up to it
    if depth_weight_g is not None and depth_weight_g > 0 and len(reconciled_items) > 0:
        total_model_weight = sum(item["portion_g"] for item in reconciled_items)
        if total_model_weight > 0:
            scale_factor = depth_weight_g / total_model_weight
            # Ensure scale factor is reasonable (between 0.5 and 1.5) to avoid excessive scaling
            scale_factor = max(0.5, min(1.5, scale_factor))
            for item in reconciled_items:
                item["portion_g"] = round(item["portion_g"] * scale_factor, 1)
            logger.info(f"Scaled items by {scale_factor:.2f} based on depth weight ({depth_weight_g}g)")

    return reconciled_items

import asyncio
import logging
import json
import base64
from app.core.config import settings

logger = logging.getLogger("kalories.orchestrator")

# ── Prompt for all vision models ──────────────────────────────────────────────
FOOD_IDENTIFY_PROMPT = """You are a food recognition system with a critical safety filter.

STEP 1 — VERIFY IT IS ACTUALLY FOOD
Before identifying anything, check: is this genuinely a photo of food/drink meant for consumption?

Reject and return the error JSON if the image contains:
- Documents (Aadhaar, PAN, passport, ID cards, certificates)
- Human faces or body parts
- Text-heavy images (forms, receipts, screenshots, menus)
- Objects (phones, utensils, furniture, vehicles)
- Animals that are not being served as food
- Landscapes, buildings, or scenes
- Blank/solid color images
- Memes, cartoons, or illustrated content
- Currency notes or cards

If ANY of the above is detected, return ONLY this JSON:
{
  "error": true,
  "error_code": "NOT_FOOD",
  "error_message": "No food detected in image",
  "detected_as": "describe what was actually in the image here",
  "items": []
}

STEP 2 — ONLY IF GENUINE FOOD IS CONFIRMED, identify and return:
{
  "error": false,
  "items": [
    {
      "food": "specific food name",
      "portion_g": 150,
      "confidence": 0.85,
      "density_g_cm3": 0.8,
      "cuisine": "Indian"
    }
  ]
}

Return ONLY valid JSON. No markdown. No explanation. Note: "density_g_cm3" is the estimated density of the food in grams per cubic centimeter (g/cm3), e.g. 0.3 for salad, 0.8 for rice/grains, 1.0 for chicken/meat, 1.05 for beef, etc. Estimating this dynamically is critical for volume calculations."""

FOOD_ANALYSIS_PROMPT = settings.FOOD_ANALYSIS_PROMPT or FOOD_IDENTIFY_PROMPT

COACH_CHAT_PROMPT = """You are a health and nutrition coach for Kalories, a smart nutrition and metabolic tracking app.
The user says: "{message}"

CRITICAL RULES:
1. You MUST ONLY answer questions or discuss topics related to health, nutrition, diet, fitness, metabolism, energy levels, and general well-being.
2. You can respond to basic greetings (like "hi", "hello", "how are you?") and basic statements of appetite (like "i am hungry").
3. If the user's message is NOT related to health, nutrition, fitness, or basic greetings/appetite (e.g. asking about programming, history, math, pop culture, fixing cars, general knowledge, etc.), you MUST politely decline to answer, redirecting them back to their health and nutrition goals.
   - For decline responses, set:
     * "reply": "I'm your health and nutrition coach, so I can only help you with diet, wellness, and fitness questions. Let me know if you want to discuss your meals or energy levels!"
     * "recommended_food": "None"
     * "recommended_benefit": "Not applicable"

Your response MUST be a valid JSON object with the following fields:
1. "reply": A string containing your direct response to the user. Keep it friendly, empathetic, and expert (approx. 2-3 sentences).
2. "recommended_food": A string recommending a specific food or combination of foods (e.g., "Oysters & Lemon", "Salmon & Avocado", "Dark Chocolate", "Spinach & Almonds"). Set to "None" if declining an unrelated query.
3. "recommended_benefit": A brief description of the specific benefit of the recommended food. Set to "Not applicable" if declining an unrelated query.

Return ONLY a valid JSON response in this format:
{{
  "reply": "your response here",
  "recommended_food": "recommended food item",
  "recommended_benefit": "brief benefit description"
}}
"""

# ── Mock data & Dynamic Mock Generator (used when API keys are missing or suspended) ──
MOCK_VISION_OUTPUTS = {
    "gemini-2.5-flash": {
        "items": [
            {"food": "chicken breast", "portion_g": 130.0, "confidence": 0.92, "density_g_cm3": 1.0},
            {"food": "cooked rice", "portion_g": 140.0, "confidence": 0.94, "density_g_cm3": 0.8},
            {"food": "broccoli", "portion_g": 90.0, "confidence": 0.85, "density_g_cm3": 0.3}
        ]
    },
    "gpt-4o": {
        "items": [
            {"food": "grilled chicken breast", "portion_g": 120.0, "confidence": 0.95, "density_g_cm3": 1.0},
            {"food": "brown rice", "portion_g": 150.0, "confidence": 0.90, "density_g_cm3": 0.8},
            {"food": "steamed broccoli", "portion_g": 80.0, "confidence": 0.88, "density_g_cm3": 0.3}
        ]
    },
    "claude-sonnet-4-6": {
        "items": [
            {"food": "grilled chicken", "portion_g": 115.0, "confidence": 0.93, "density_g_cm3": 1.0},
            {"food": "rice", "portion_g": 160.0, "confidence": 0.89, "density_g_cm3": 0.8},
            {"food": "broccoli florets", "portion_g": 75.0, "confidence": 0.91, "density_g_cm3": 0.3}
        ]
    }
}

def generate_dynamic_mock(image_bytes: bytes, filename: str = "") -> dict:
    """
    Generates a dynamic mock response based on filename keywords or image color heuristics.
    """
    logger.info(f"Generating dynamic mock: filename='{filename}'")
    filename_lower = filename.lower() if filename else ""
    
    items = []
    
    # 1. Filename heuristic
    if "not_food" in filename_lower or "document" in filename_lower or "receipt" in filename_lower:
        return {
            "error": True,
            "error_code": "NOT_FOOD",
            "error_message": "No food detected in image",
            "detected_as": "document",
            "items": []
        }
    elif "oat" in filename_lower:
        items.append({"food": "oats", "portion_g": 120.0, "confidence": 0.95})
    elif "watermelon" in filename_lower:
        items.append({"food": "watermelon", "portion_g": 200.0, "confidence": 0.94})
    elif "orange" in filename_lower:
        items.append({"food": "orange", "portion_g": 150.0, "confidence": 0.93})
    elif "paneer" in filename_lower:
        items.append({"food": "paneer", "portion_g": 100.0, "confidence": 0.90})
    elif "roti" in filename_lower or "chapati" in filename_lower:
        items.append({"food": "roti", "portion_g": 60.0, "confidence": 0.95})
    elif "dal" in filename_lower:
        items.append({"food": "dal", "portion_g": 150.0, "confidence": 0.92})
    elif "biryani" in filename_lower:
        items.append({"food": "biryani", "portion_g": 300.0, "confidence": 0.94})
    elif "chicken" in filename_lower:
        items.append({"food": "chicken breast", "portion_g": 130.0, "confidence": 0.92})
    elif "rice" in filename_lower:
        items.append({"food": "brown rice", "portion_g": 140.0, "confidence": 0.94})
    elif "broccoli" in filename_lower:
        items.append({"food": "broccoli", "portion_g": 90.0, "confidence": 0.85})
    elif "salad" in filename_lower:
        items.append({"food": "salad", "portion_g": 100.0, "confidence": 0.90})
    elif "pasta" in filename_lower:
        items.append({"food": "pasta", "portion_g": 180.0, "confidence": 0.88})
    elif "egg" in filename_lower:
        items.append({"food": "egg", "portion_g": 60.0, "confidence": 0.96})
    elif "apple" in filename_lower:
        items.append({"food": "apple", "portion_g": 150.0, "confidence": 0.95})
    elif "banana" in filename_lower:
        items.append({"food": "banana", "portion_g": 120.0, "confidence": 0.94})
    elif "bread" in filename_lower:
        items.append({"food": "bread", "portion_g": 80.0, "confidence": 0.91})
    elif "soup" in filename_lower:
        items.append({"food": "soup", "portion_g": 250.0, "confidence": 0.89})
    elif "potato" in filename_lower:
        items.append({"food": "potato", "portion_g": 150.0, "confidence": 0.90})
        
    # 2. If no matching keyword, use image color analysis
    if not items and image_bytes:
        try:
            from PIL import Image
            import io
            
            img = Image.open(io.BytesIO(image_bytes))
            img = img.convert("RGB")
            # Resize to 8x8 to get color distribution
            img_small = img.resize((8, 8))
            pixels = list(img_small.getdata())
            
            green_count = 0
            red_count = 0
            yellow_count = 0
            
            for r, g, b in pixels:
                # Green pixel check
                if g > r + 10 and g > b + 10:
                    green_count += 1
                # Red/pink pixel check
                elif r > g + 20 and r > b + 20 and r > 100:
                    red_count += 1
                # Yellow/beige pixel check
                elif r > 150 and g > 130 and b < 140:
                    yellow_count += 1
            
            logger.info(f"Color profiling: Red={red_count}, Green={green_count}, Yellow={yellow_count}")
            
            # Dynamic heuristic matching
            if red_count >= 5 and green_count >= 2:
                # Watermelon: vibrant red interior + green rind
                items.append({"food": "watermelon", "portion_g": 200.0, "confidence": 0.91})
            elif green_count >= 15:
                # Salad / broccoli: mostly green
                items.append({"food": "salad", "portion_g": 110.0, "confidence": 0.85})
            elif red_count >= 10:
                # Meat / Beef: mostly red/brown
                items.append({"food": "beef", "portion_g": 140.0, "confidence": 0.88})
            elif yellow_count >= 15:
                # Oats / Roti / Bread: beige / yellow
                items.append({"food": "oats", "portion_g": 130.0, "confidence": 0.82})
        except Exception as e:
            logger.error(f"Error performing image color analysis: {e}")
            
    # 3. Default fallback if still empty
    if not items:
        items = [
            {"food": "chicken breast", "portion_g": 130.0, "confidence": 0.92},
            {"food": "cooked rice", "portion_g": 140.0, "confidence": 0.94},
            {"food": "broccoli", "portion_g": 90.0, "confidence": 0.85}
        ]
        
    # Dynamic density lookup for mock output
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
        "potato": 0.85,
        "oats": 0.4,
        "watermelon": 0.9,
        "orange": 0.9,
        "paneer": 1.0,
        "roti": 0.4,
        "dal": 1.0,
        "biryani": 0.85
    }
    for item in items:
        fd = item["food"].lower()
        d_val = 0.9
        for k, v in density_map.items():
            if k in fd:
                d_val = v
                break
        item["density_g_cm3"] = d_val

    return {"items": items}

# ── Real Gemini Vision ────────────────────────────────────────────────────────

async def run_gemini_vision(image_bytes: bytes, filename: str = "") -> dict:
    """Call Gemini 2.5 Flash with the food image for analysis."""
    if not settings.GEMINI_API_KEY:
        logger.info("Gemini API key missing. Returning mock response.")
        await asyncio.sleep(0.3)
        return generate_dynamic_mock(image_bytes, filename)

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)

        model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")

        # Build the image part
        image_part = {
            "mime_type": "image/jpeg",
            "data": image_bytes
        }

        logger.info("Calling Gemini 2.5 Flash vision API...")
        response = await asyncio.to_thread(
            model.generate_content,
            [FOOD_ANALYSIS_PROMPT, image_part]
        )

        raw_text = response.text.strip()
        logger.info(f"Gemini raw response: {raw_text[:300]}")

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines).strip()

        parsed = json.loads(raw_text)

        # Validate structure
        if "items" not in parsed or not isinstance(parsed["items"], list):
            logger.warning("Gemini response missing 'items' key. Wrapping.")
            if isinstance(parsed, list):
                parsed = {"items": parsed}
            else:
                raise ValueError("Unexpected response structure")

        # Validate each item
        for item in parsed["items"]:
            item.setdefault("food", "unknown food")
            item["portion_g"] = float(item.get("portion_g", 150.0))
            item["confidence"] = float(item.get("confidence", 0.8))
            if "density_g_cm3" in item:
                try:
                    item["density_g_cm3"] = float(item["density_g_cm3"])
                except Exception:
                    pass

        logger.info(f"Gemini identified {len(parsed['items'])} food items.")
        return parsed

    except json.JSONDecodeError as je:
        logger.error(f"Failed to parse Gemini JSON response: {je}")
        return generate_dynamic_mock(image_bytes, filename)
    except Exception as e:
        logger.error(f"Error calling Gemini: {e}")
        return generate_dynamic_mock(image_bytes, filename)


# ── GPT-4o Vision (mock until key provided) ───────────────────────────────────

async def run_gpt4o_vision(image_bytes: bytes) -> dict:
    if not settings.OPENAI_API_KEY:
        logger.info("OpenAI API key missing. Skipping GPT-4o.")
        return None  # Return None to indicate this model was not used

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        logger.info("Calling GPT-4o vision API...")

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": FOOD_ANALYSIS_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }],
            max_tokens=1000,
            temperature=0.1
        )

        raw_text = response.choices[0].message.content.strip()
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines).strip()

        parsed = json.loads(raw_text)
        if "items" not in parsed:
            parsed = {"items": parsed} if isinstance(parsed, list) else {"items": []}
        for item in parsed.get("items", []):
            item.setdefault("food", "unknown food")
            item["portion_g"] = float(item.get("portion_g", 150.0))
            item["confidence"] = float(item.get("confidence", 0.8))
            if "density_g_cm3" in item:
                try:
                    item["density_g_cm3"] = float(item["density_g_cm3"])
                except Exception:
                    pass
        return parsed

    except Exception as e:
        logger.error(f"Error calling GPT-4o: {e}")
        return None


# ── Claude Vision (mock until key provided) ───────────────────────────────────

async def run_claude_vision(image_bytes: bytes) -> dict:
    if not settings.ANTHROPIC_API_KEY:
        logger.info("Anthropic API key missing. Skipping Claude.")
        return None

    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        logger.info("Calling Claude vision API...")

        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64_image}},
                    {"type": "text", "text": FOOD_ANALYSIS_PROMPT}
                ]
            }]
        )

        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines).strip()

        parsed = json.loads(raw_text)
        if "items" not in parsed:
            parsed = {"items": parsed} if isinstance(parsed, list) else {"items": []}
        for item in parsed.get("items", []):
            item.setdefault("food", "unknown food")
            item["portion_g"] = float(item.get("portion_g", 150.0))
            item["confidence"] = float(item.get("confidence", 0.8))
            if "density_g_cm3" in item:
                try:
                    item["density_g_cm3"] = float(item["density_g_cm3"])
                except Exception:
                    pass
        return parsed

    except Exception as e:
        logger.error(f"Error calling Claude: {e}")
        return None


async def check_ollama_model(model_name: str) -> str:
    """Checks if Ollama is running and has the model loaded/pulled. Returns exact name or None."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.OLLAMA_URL}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                for m in models:
                    name = m.get("name", "")
                    if name == model_name or name.startswith(f"{model_name}:"):
                        return name
    except Exception:
        pass
    return None

# ── Local Gemma-4-E4B-it Lazy Loading & Generation Helpers ───────────────────

_hf_processor = None
_hf_model = None

def get_local_gemma_model():
    global _hf_processor, _hf_model
    if _hf_model is not None:
        return _hf_processor, _hf_model
        
    try:
        from transformers import AutoProcessor, AutoModelForMultimodalLM
        import torch
        model_id = settings.GEMMA_MODEL_NAME
        logger.info(f"Loading local {model_id} model...")
        
        _hf_processor = AutoProcessor.from_pretrained(model_id)
        # Load in float32 for CPU to avoid half-precision issues if not supported
        _hf_model = AutoModelForMultimodalLM.from_pretrained(
            model_id,
            device_map="cpu",
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True
        )
        logger.info("Local Gemma model loaded successfully.")
        return _hf_processor, _hf_model
    except Exception as e:
        logger.error(f"Error loading local Gemma model: {e}")
        return None, None

async def run_local_gemma_multimodal(image_bytes: bytes, prompt: str) -> str:
    processor, model = get_local_gemma_model()
    if not model:
        raise RuntimeError("Local Gemma model not available")
        
    def _run():
        from PIL import Image
        import io
        import torch
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
            formatted = processor.apply_chat_template(messages, add_generation_prompt=True)
            inputs = processor(images=img, text=formatted, return_tensors="pt")
        except Exception:
            inputs = processor(images=img, text=prompt, return_tensors="pt")
            
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=512)
        return processor.decode(outputs[0], skip_special_tokens=True)
        
    return await asyncio.to_thread(_run)

async def run_local_gemma_text(prompt: str) -> str:
    processor, model = get_local_gemma_model()
    if not model:
        raise RuntimeError("Local Gemma model not available")
        
    def _run():
        import torch
        try:
            messages = [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            formatted = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=formatted, return_tensors="pt")
        except Exception:
            inputs = processor(text=prompt, return_tensors="pt")
            
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=512)
        return processor.decode(outputs[0], skip_special_tokens=True)
        
    return await asyncio.to_thread(_run)

# ── Hugging Face Inference API Gated Fallbacks ───────────────────────────────

async def run_gemma4_hf_vision(image_bytes: bytes, prompt: str) -> str:
    if not settings.HF_API_KEY:
        raise ValueError("HF API key missing")
    
    import httpx
    model_id = settings.GEMMA_MODEL_NAME
    url = f"https://api-inference.huggingface.co/models/{model_id}/v1/chat/completions"
    
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    headers = {
        "Authorization": f"Bearer {settings.HF_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }
        ],
        "max_tokens": 1000,
        "temperature": 0.1
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            raise RuntimeError(f"HF API returned status {response.status_code}: {response.text}")

async def run_gemma4_hf_text(prompt: str) -> str:
    if not settings.HF_API_KEY:
        raise ValueError("HF API key missing")
    
    import httpx
    model_id = settings.GEMMA_MODEL_NAME
    url = f"https://api-inference.huggingface.co/models/{model_id}/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {settings.HF_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000,
        "temperature": 0.1
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            raise RuntimeError(f"HF API returned status {response.status_code}: {response.text}")

# ── Legacy/Compatibility Model Runners ────────────────────────────────────────

async def run_gemma4_vision(image_bytes: bytes, filename: str = "") -> dict:
    """Call Google Gemma 4 vision model (via local Ollama or Hugging Face Inference API)."""
    gemma_model = settings.GEMMA_MODEL_NAME
    ollama_model_name = await check_ollama_model("gemma-4") or await check_ollama_model(gemma_model)

    if ollama_model_name:
        try:
            import base64
            import httpx
            
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            url = f"{settings.OLLAMA_URL}/api/chat"
            
            payload = {
                "model": ollama_model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": FOOD_ANALYSIS_PROMPT,
                        "images": [b64_image]
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1
                }
            }
            
            logger.info(f"Calling local Ollama with {ollama_model_name}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    raw_text = response.json().get("message", {}).get("content", "").strip()
                    logger.info(f"Ollama Gemma 4 response: {raw_text[:200]}")
                    
                    if raw_text.startswith("```"):
                        lines = raw_text.split("\n")
                        lines = [l for l in lines if not l.strip().startswith("```")]
                        raw_text = "\n".join(lines).strip()
                        
                    parsed = json.loads(raw_text)
                    if "items" not in parsed:
                        parsed = {"items": parsed} if isinstance(parsed, list) else {"items": []}
                        
                    for item in parsed.get("items", []):
                        item.setdefault("food", "unknown food")
                        item["portion_g"] = float(item.get("portion_g", 150.0))
                        item["confidence"] = float(item.get("confidence", 0.8))
                        if "density_g_cm3" in item:
                            try:
                                item["density_g_cm3"] = float(item["density_g_cm3"])
                            except Exception:
                                pass
                            
                    return parsed
        except Exception as oe:
            logger.warning(f"Failed to query local Ollama: {oe}. Falling back to Hugging Face / Mock.")

    if settings.HF_API_KEY:
        try:
            raw = await run_gemma4_hf_vision(image_bytes, FOOD_ANALYSIS_PROMPT)
            parsed = json.loads(raw)
            if "items" not in parsed:
                parsed = {"items": parsed} if isinstance(parsed, list) else {"items": []}
            return parsed
        except Exception as hfe:
            logger.error(f"Error calling Hugging Face Gemma 4 model: {hfe}")

    logger.info("Gemma 4 API/Ollama unavailable. Returning dynamic mock.")
    return generate_dynamic_mock(image_bytes, filename)

async def run_hf_vision(image_bytes: bytes) -> dict:
    """Call Hugging Face Inference API using Qwen2-VL-7B-Instruct model."""
    if not settings.HF_API_KEY:
        logger.info("Hugging Face API key missing. Skipping Hugging Face model.")
        return None

    try:
        import base64
        import httpx
        
        model_id = "Qwen/Qwen2-VL-7B-Instruct"
        url = f"https://api-inference.huggingface.co/models/{model_id}/v1/chat/completions"
        
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        headers = {
            "Authorization": f"Bearer {settings.HF_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": FOOD_ANALYSIS_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                    ]
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.1
        }
        
        logger.info(f"Calling Hugging Face Inference API for {model_id}...")
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                raw_text = result["choices"][0]["message"]["content"].strip()
                logger.info(f"Hugging Face raw response: {raw_text[:300]}")
                
                if raw_text.startswith("```"):
                    lines = raw_text.split("\n")
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    raw_text = "\n".join(lines).strip()
                    
                parsed = json.loads(raw_text)
                if "items" not in parsed:
                    parsed = {"items": parsed} if isinstance(parsed, list) else {"items": []}
                    
                for item in parsed.get("items", []):
                    item.setdefault("food", "unknown food")
                    item["portion_g"] = float(item.get("portion_g", 150.0))
                    item["confidence"] = float(item.get("confidence", 0.8))
                    if "density_g_cm3" in item:
                        try:
                            item["density_g_cm3"] = float(item["density_g_cm3"])
                        except Exception:
                            pass
                    
                return parsed
            else:
                logger.error(f"Hugging Face API returned error status {response.status_code}: {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"Error calling Hugging Face Vision: {e}")
        return None

# ── Helper for Parsing JSON ──────────────────────────────────────────────────

def parse_json_response(text: str) -> dict:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except Exception:
        # Try finding JSON block
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start:end+1])
        except Exception:
            pass
    return None

# ── 3-Stage Pipeline - Call 1, 2, and 3 ───────────────────────────────────────

async def run_call_1_vision(image_bytes: bytes, filename: str = "") -> dict:
    """LLM Call 1 (Vision): Identify the food type and the portion it covered."""
    prompt = FOOD_IDENTIFY_PROMPT
    
    # 1. Try local transformers Gemma 4
    try:
        raw_text = await run_local_gemma_multimodal(image_bytes, prompt)
        parsed = parse_json_response(raw_text)
        if parsed and "items" in parsed:
            logger.info("Call 1 (Vision) succeeded using local Gemma-4-E4B-it.")
            return parsed
    except Exception as e:
        logger.warning(f"Call 1 local Gemma-4-E4B-it failed: {e}. Trying HF API...")

    # 2. Try Hugging Face Inference API for Gemma-4-E4B-it
    if settings.HF_API_KEY:
        try:
            raw_text = await run_gemma4_hf_vision(image_bytes, prompt)
            parsed = parse_json_response(raw_text)
            if parsed and "items" in parsed:
                logger.info("Call 1 (Vision) succeeded using Hugging Face Inference API.")
                return parsed
        except Exception as e:
            logger.warning(f"Call 1 Hugging Face Inference API failed: {e}. Trying Gemini...")

    # 3. Try Gemini API
    if settings.GEMINI_API_KEY:
        try:
            parsed = await run_gemini_vision(image_bytes, filename)
            if parsed and "items" in parsed:
                logger.info("Call 1 (Vision) succeeded using Gemini API.")
                return parsed
        except Exception as e:
            logger.warning(f"Call 1 Gemini API failed: {e}. Trying local Ollama vision...")

    # 4. Try local Ollama vision
    try:
        parsed = await run_gemma4_vision(image_bytes, filename)
        if parsed and "items" in parsed:
            logger.info("Call 1 (Vision) succeeded using Ollama Vision.")
            return parsed
    except Exception as e:
        logger.warning(f"Call 1 Ollama Vision failed: {e}. Using dynamic mock...")

    # 5. Dynamic Mock Fallback
    logger.info("Call 1 (Vision) using dynamic mock fallback.")
    return generate_dynamic_mock(image_bytes, filename)

async def run_call_2_nutrition(reconciled_items: list) -> dict:
    """LLM Call 2 (Text): Take Call 1 output and estimate Calories (Kalories) & Protein (Proties)."""
    cleaned_items = []
    for item in reconciled_items:
        cleaned_items.append({
            "food": item.get("name", item.get("food", "")),
            "portion_g": item.get("portion_g", 150.0)
        })
        
    prompt = """You are an expert nutritionist.
    Given the following list of food items and portion weights:
    {items_json}

    For each food item, estimate:
    1. Calories (kcal)
    2. Protein (g)
    Also estimate other macros (carbs, fat, fiber in grams) to the best of your ability.
    
    Return ONLY a valid JSON response in this format:
    {{
      "items": [
        {{
          "food": "food name",
          "portion_g": 150.0,
          "kcal": 120.0,
          "macros": {{
            "protein": 5.0,
            "carbs": 25.0,
            "fat": 0.5,
            "fiber": 2.0
          }}
        }}
      ]
    }}
    """.format(items_json=json.dumps(cleaned_items, indent=2))

    # 1. Try local transformers Gemma 4
    try:
        raw_text = await run_local_gemma_text(prompt)
        parsed = parse_json_response(raw_text)
        if parsed and "items" in parsed:
            logger.info("Call 2 (Nutrition) succeeded using local Gemma-4-E4B-it.")
            return parsed
    except Exception as e:
        logger.warning(f"Call 2 local Gemma failed: {e}. Trying HF API...")

    # 2. Try Hugging Face Inference API
    if settings.HF_API_KEY:
        try:
            raw_text = await run_gemma4_hf_text(prompt)
            parsed = parse_json_response(raw_text)
            if parsed and "items" in parsed:
                logger.info("Call 2 (Nutrition) succeeded using HF Inference API.")
                return parsed
        except Exception as e:
            logger.warning(f"Call 2 HF API failed: {e}. Trying Gemini...")

    # 3. Try Gemini API
    if settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = await asyncio.to_thread(model.generate_content, prompt)
            parsed = parse_json_response(response.text)
            if parsed and "items" in parsed:
                logger.info("Call 2 (Nutrition) succeeded using Gemini API.")
                return parsed
        except Exception as e:
            logger.warning(f"Call 2 Gemini API failed: {e}. Trying Ollama...")

    # 4. Try local Ollama
    try:
        ollama_res = await run_ollama_text(prompt)
        parsed = parse_json_response(ollama_res)
        if parsed and "items" in parsed:
            logger.info("Call 2 (Nutrition) succeeded using local Ollama.")
            return parsed
    except Exception as e:
        logger.warning(f"Call 2 Ollama failed: {e}. Using local mock database...")

    # 5. Local Mock DB Fallback
    logger.info("Call 2 (Nutrition) using local mock database fallback.")
    items_out = []
    for item in reconciled_items:
        name = item.get("name", item.get("food", ""))
        portion_g = item.get("portion_g", 150.0)
        
        nut = {"kcal": 100.0, "protein": 5.0, "carbs": 15.0, "fat": 2.0, "fiber": 1.0}
        try:
            from app.services.nutrition import NUTRITION_MOCK_DB
            for k, v in NUTRITION_MOCK_DB.items():
                if k in name.lower() or name.lower() in k:
                    nut = v
                    break
        except Exception:
            pass
            
        kcal = (portion_g / 100.0) * nut["kcal"]
        protein = (portion_g / 100.0) * nut["protein"]
        carbs = (portion_g / 100.0) * nut["carbs"]
        fat = (portion_g / 100.0) * nut["fat"]
        fiber = (portion_g / 100.0) * nut["fiber"]
        
        items_out.append({
            "food": name,
            "portion_g": portion_g,
            "kcal": round(kcal, 1),
            "macros": {
                "protein": round(protein, 1),
                "carbs": round(carbs, 1),
                "fat": round(fat, 1),
                "fiber": round(fiber, 1)
            }
        })
    return {"items": items_out}

async def run_call_3_libido(nutrition_data: dict) -> dict:
    """LLM Call 3 (Text): Take nutrition estimation and compute Libido Score (Libio Score)."""
    prompt = """You are an expert health and libido coach specializing in testosterone and hormone optimization.
    Given the following meal items and their estimated nutritional content:
    {nutrition_json}

    Calculate the Libido (Libio) Score (from 0 to 100) representing the impact of this meal on libido, energy, and testosterone levels.
    Determine whether the overall impact direction is a "boost", "neutral", or "decrease".
    List 3 key physiological factors explaining why (e.g. "Rich in Zinc", "Increases Nitric Oxide", "Optimizes Testosterone", "High in Healthy Fats", "Promotes Blood Flow", "Increases Inflammation", "Spikes Insulin").
    
    Return ONLY a JSON response in the following format:
    {{
      "libido_analysis": {{
        "impact_percent": 75,
        "impact_direction": "boost", // "boost", "neutral", or "decrease"
        "key_factors": [
          "key factor 1",
          "key factor 2",
          "key factor 3"
        ]
      }}
    }}
    """.format(nutrition_json=json.dumps(nutrition_data, indent=2))

    # 1. Try local transformers Gemma 4
    try:
        raw_text = await run_local_gemma_text(prompt)
        parsed = parse_json_response(raw_text)
        if parsed and "libido_analysis" in parsed:
            logger.info("Call 3 (Libido) succeeded using local Gemma-4-E4B-it.")
            return parsed
    except Exception as e:
        logger.warning(f"Call 3 local Gemma failed: {e}. Trying HF API...")

    # 2. Try Hugging Face Inference API
    if settings.HF_API_KEY:
        try:
            raw_text = await run_gemma4_hf_text(prompt)
            parsed = parse_json_response(raw_text)
            if parsed and "libido_analysis" in parsed:
                logger.info("Call 3 (Libido) succeeded using HF Inference API.")
                return parsed
        except Exception as e:
            logger.warning(f"Call 3 HF API failed: {e}. Trying Gemini...")

    # 3. Try Gemini API
    if settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = await asyncio.to_thread(model.generate_content, prompt)
            parsed = parse_json_response(response.text)
            if parsed and "libido_analysis" in parsed:
                logger.info("Call 3 (Libido) succeeded using Gemini API.")
                return parsed
        except Exception as e:
            logger.warning(f"Call 3 Gemini API failed: {e}. Trying Ollama...")

    # 4. Try local Ollama
    try:
        ollama_res = await run_ollama_text(prompt)
        parsed = parse_json_response(ollama_res)
        if parsed and "libido_analysis" in parsed:
            logger.info("Call 3 (Libido) succeeded using local Ollama.")
            return parsed
    except Exception as e:
        logger.warning(f"Call 3 Ollama failed: {e}. Using rules-based fallback...")

    # 5. Rules-based Fallback
    logger.info("Call 3 (Libido) using rules-based fallback.")
    libido_pct = 0
    libido_dir = "neutral"
    libido_factors = ["Balanced Macros", "Provides Energy", "General Nutrition"]
    
    has_oysters = False
    has_chocolate = False
    has_avocado = False
    
    for item in nutrition_data.get("items", []):
        name = item.get("food", "").lower()
        if "oyster" in name:
            has_oysters = True
        if "chocolate" in name or "pomegranate" in name or "honey" in name:
            has_chocolate = True
        if "avocado" in name or "salmon" in name or "egg" in name:
            has_avocado = True
            
    if has_oysters:
        libido_pct = 78
        libido_dir = "boost"
        libido_factors = ["Rich in Zinc", "Increases Testosterone", "Reduces Stress"]
    elif has_chocolate:
        libido_pct = 45
        libido_dir = "boost"
        libido_factors = ["Boosts Dopamine", "Improves Blood Flow", "Rich in Antioxidants"]
    elif has_avocado:
        libido_pct = 35
        libido_dir = "boost"
        libido_factors = ["High in Healthy Fats", "Optimizes Hormone Synthesis", "Sustains Energy"]

    return {
        "libido_analysis": {
            "impact_percent": libido_pct,
            "impact_direction": libido_dir,
            "key_factors": libido_factors
        }
    }

# ── Unified Orchestrator & Stage 2 Linkers ───────────────────────────────────

async def orchestrate_vision_scan(image_bytes: bytes, filename: str = "") -> dict:
    """Runs Call 1 (Vision) of the 3-stage pipeline."""
    logger.info(f"Starting Call 1 (Vision Scan) for {filename}...")
    call_1_res = await run_call_1_vision(image_bytes, filename)
    return {
        "gemma-4-E4B-it": call_1_res
    }

async def run_ollama_text(prompt: str) -> str:
    """Helper to query local Ollama with a text prompt using any available text model."""
    text_model = await check_ollama_model("llama3")
    
    if not text_model:
        # Check if there are any other models pulled in Ollama that we can use
        try:
            import httpx
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{settings.OLLAMA_URL}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    if models:
                        text_model = models[0].get("name", "llama3")
        except Exception:
            pass
            
    if text_model:
        try:
            import httpx
            url = f"{settings.OLLAMA_URL}/api/generate"
            payload = {
                "model": text_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1
                }
            }
            logger.info(f"Calling local Ollama text model {text_model}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    return result.get("response", "").strip()
        except Exception as e:
            logger.warning(f"Failed to query local Ollama for text: {e}")
    return None

async def run_nutrition_and_analysis_llm(reconciled_items: list) -> dict:
    """Runs Call 2 (Nutrition) followed by Call 3 (Libido) sequentially."""
    logger.info("Starting Call 2 (Nutrition estimation)...")
    nutrition_data = await run_call_2_nutrition(reconciled_items)
    
    logger.info("Starting Call 3 (Libido calculation)...")
    libido_data = await run_call_3_libido(nutrition_data)
    
    return {
        "items": nutrition_data.get("items", []),
        "libido_analysis": libido_data.get("libido_analysis", {})
    }

async def run_coach_chat_llm(message: str) -> dict:
    """Generate coach response using LLM."""
    # Baseline checks for greetings, appetite, and general health keywords
    ml = message.lower().strip()
    is_greeting = any(word in ml for word in ["hi", "hello", "hey", "greetings", "yo", "howdy", "sup"])
    is_appetite = any(word in ml for word in ["hungry", "starving", "want to eat", "crave"])
    
    health_keywords = [
        "health", "nutrition", "diet", "food", "calorie", "kcal", "protein", "carb", "fat", 
        "fiber", "eat", "meal", "recipe", "snack", "breakfast", "lunch", "dinner", "tired", 
        "energy", "fatigue", "testosterone", "libido", "sex", "sweet", "sugar", "chocolate", 
        "workout", "fitness", "exercise", "weight", "muscle", "test", "run", "water", "hydrate"
    ]
    is_health_related = any(keyword in ml for keyword in health_keywords)
    
    # Default fallback for unrelated messages
    fallback_response = {
        "reply": "I'm your health and nutrition coach, so I can only help you with diet, wellness, and fitness questions. Let me know if you want to discuss your meals or energy levels!",
        "recommended_food": "None",
        "recommended_benefit": "Not applicable"
    }
    
    if is_greeting:
        fallback_response = {
            "reply": "Hello! I am your Kalories health and nutrition coach. How can I help you support your diet, wellness, or energy goals today?",
            "recommended_food": "Water with Lemon",
            "recommended_benefit": "Boosts hydration and activates digestion."
        }
    elif is_appetite:
        fallback_response = {
            "reply": "When hunger strikes, it's best to feed your body clean, slow-burning fuel to prevent energy crashes. Let's aim for a balanced, nutrient-dense snack.",
            "recommended_food": "Almonds & Apple",
            "recommended_benefit": "Provides a clean mix of healthy fats, fiber, and complex carbs."
        }
    elif is_health_related or not ml:
        fallback_response = {
            "reply": "I recommend focusing on clean, nutrient-dense whole foods like leafy greens, healthy fats from avocados, and high-quality protein to support your testosterone and stamina.",
            "recommended_food": "Salmon & Avocado",
            "recommended_benefit": "High in Omega-3 and Zinc, optimizes hormone production"
        }
        
        # Specific override matches
        if "tired" in ml or "energy" in ml or "fatigue" in ml:
            fallback_response = {
                "reply": "Feeling tired is often a sign of low zinc, low magnesium, or hormone fatigue. Let's focus on restorative foods to boost your blood flow and energy.",
                "recommended_food": "Salmon & Avocado",
                "recommended_benefit": "High in Omega-3 and Zinc, optimizes hormone production"
            }
        elif "testosterone" in ml or "libido" in ml or "sex" in ml:
            fallback_response = {
                "reply": "To optimize your testosterone levels, prioritizing zinc-rich foods and magnesium is key. This stimulates free testosterone production.",
                "recommended_food": "Oysters & Lemon",
                "recommended_benefit": "Zinc powerhouse, immediately boosts nitric oxide"
            }
        elif "sweet" in ml or "sugar" in ml or "chocolate" in ml:
            fallback_response = {
                "reply": "A little dark chocolate is an excellent vasodilator! It contains phenylethylamine which triggers endorphins and boosts nitric oxide.",
                "recommended_food": "Dark Chocolate",
                "recommended_benefit": "Boosts nitric oxide and blood flow, rich in antioxidants"
            }

    prompt = COACH_CHAT_PROMPT.format(message=message)

    # 1. Try local transformers Gemma 4
    try:
        raw_text = await run_local_gemma_text(prompt)
        parsed = parse_json_response(raw_text)
        if parsed and "reply" in parsed:
            logger.info("Coach Chat succeeded using local Gemma-4-E4B-it.")
            return parsed
    except Exception as e:
        logger.warning(f"Coach Chat local Gemma failed: {e}. Trying HF API...")

    # 2. Try Hugging Face Inference API
    if settings.HF_API_KEY:
        try:
            raw_text = await run_gemma4_hf_text(prompt)
            parsed = parse_json_response(raw_text)
            if parsed and "reply" in parsed:
                logger.info("Coach Chat succeeded using HF Inference API.")
                return parsed
        except Exception as e:
            logger.warning(f"Coach Chat HF API failed: {e}. Trying Gemini...")

    # 3. Try Gemini API
    if settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = await asyncio.to_thread(model.generate_content, prompt)
            parsed = parse_json_response(response.text)
            if parsed and "reply" in parsed:
                logger.info("Coach Chat succeeded using Gemini API.")
                return parsed
        except Exception as e:
            logger.error(f"Error calling Gemini for Coach Chat: {e}. Attempting Ollama fallback...")

    # 4. Try Ollama local text generation
    try:
        ollama_res = await run_ollama_text(prompt)
        parsed = parse_json_response(ollama_res)
        if parsed and "reply" in parsed:
            logger.info("Successfully generated Coach Chat response using local Ollama.")
            return parsed
    except Exception as oe:
        logger.warning(f"Ollama fallback failed in run_coach_chat_llm: {oe}")

    logger.info("Both Gemini and Ollama Coach Chat failed. Returning mock response.")
    return fallback_response

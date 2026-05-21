# Kalories — Phase 1

Camera-based food recognition with ARCore depth and multi-model AI calorie estimation.

---

## Project Structure

```
kalories/
├── android/                  ← Open THIS folder in Android Studio
│   (all Kotlin/Compose files are inside app/src/main/java/com/kalories/)
└── backend/                  ← Python FastAPI backend
```

---

## Android Setup

### Requirements
- Android Studio Hedgehog (2023.1.1) or newer
- Android device with API 26+ (Android 8.0+)
- ARCore supported device for depth (optional — app falls back on unsupported devices)

### Steps
1. Open **Android Studio** → Open → select the `kalories/` root folder
2. Wait for Gradle sync to finish (first time downloads ~500MB of dependencies)
3. In `app/build.gradle.kts`, the `BASE_URL` is set to `http://10.0.2.2:8000/` (emulator localhost).
   - **Physical device**: change to your computer's local IP e.g. `http://192.168.1.X:8000/`
4. Connect your Android device (USB debugging on) or start an emulator
5. Hit ▶ Run

### What the app does
1. Requests camera permission on launch
2. Shows live camera preview with an ARCore scan reticle and scan-line animation
3. Badge in top-right shows whether ARCore Depth is active or using fallback
4. Tap the 📷 button → captures JPEG + Depth16 bytes (if ARCore available)
5. Uploads to `POST /scans` on the backend with depth_mm metadata
6. Shows a bottom sheet with: food items, portion grams, kcal, protein/carbs/fat macros

---

## Backend Setup

### Requirements
- Python 3.12
- MongoDB running locally (`mongod`) or MongoDB Atlas free tier
- API keys: OpenAI and/or Anthropic (at least one needed)

### Steps

```bash
cd backend

# 1. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your actual API keys and MongoDB URL

# 4. Run the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Test the API directly (without Android)
```bash
curl -X POST http://localhost:8000/scans \
  -F "image=@/path/to/food_photo.jpg" \
  -F 'meta={"depth_mm": null, "depth_supported": false}'
```

Expected response:
```json
{
  "scan_id": "...",
  "status": "complete",
  "items": [
    {"food": "rice", "portion_g": 150.0, "kcal": 195.0, "confidence": 0.88, "macros": {...}}
  ],
  "total_kcal": 195.0,
  "total_macros": {"protein": 4.0, "carbs": 43.0, "fat": 0.4, "fiber": 0.6},
  "depth_mm": null,
  "model": "ensemble"
}
```

---

## ARCore Depth behaviour

| Device            | Behaviour                                              |
|-------------------|--------------------------------------------------------|
| ARCore + Depth    | Captures Depth16 map, reads plate-centre depth in mm   |
| ARCore (no Depth) | depth_bytes = null, depth_mm = null, scan still works  |
| No ARCore         | Same as above — reference-object fallback (Phase 2)    |

The badge in the top-right of the camera screen shows which mode is active.

---

## Adding more vision models

To add Gemini, add this to `backend/app/services/vision/gemini_vision.py`
and register it in `orchestrator.py`:

```python
MODEL_RUNNERS = {
    "claude-sonnet-4-6": claude_vision.identify,
    "gpt-4o": gpt4o_vision.identify,
    "gemini-2.5-pro": gemini_vision.identify,   # add here
}
```

The reconciler automatically handles any number of models.

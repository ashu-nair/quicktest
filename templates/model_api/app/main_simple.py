# Simple model API for Python 3.7 compatibility
from fastapi import FastAPI
import joblib
import numpy as np
from pathlib import Path
import os

app = FastAPI()

# Load model on startup
MODEL = None
MODEL_PATH = Path(os.getenv("MODEL_PATH", "/model")) / "model.pkl"

@app.on_event("startup")
def startup():
    global MODEL
    try:
        MODEL = joblib.load(MODEL_PATH)
        print(f"✅ Model loaded from {MODEL_PATH}")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": MODEL is not None}

@app.post("/predict")
def predict(data: dict):
    if MODEL is None:
        return {"error": "Model not loaded"}
    try:
        features = data.get("features", [])
        if isinstance(features, dict):
            features = list(features.values())
        X = np.array([features])
        pred = MODEL.predict(X)
        return {"prediction": pred.tolist()}
    except Exception as e:
        return {"error": str(e)}

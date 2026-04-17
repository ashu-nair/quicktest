# Simple model API for Python 3.7 compatibility
from fastapi import FastAPI
import joblib
import numpy as np
from pathlib import Path
import os

app = FastAPI(title="MLOps Model API", version="1.0")

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

@app.get("/")
def root():
    return {
        "service": "MLOps Model API",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "predict": "POST /predict with JSON body: {\"features\": [1,2,3]}"
        }
    }

@app.get("/predict")
def predict_get():
    return {
        "message": "Use POST method to make predictions",
        "example": {
            "method": "POST",
            "url": "/predict",
            "body": {"features": [1.0, 2.0, 3.0, 4.0]}
        }
    }

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

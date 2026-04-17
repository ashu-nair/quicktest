# Simple model API for Python 3.7 compatibility
from fastapi import FastAPI
import joblib
import numpy as np
from pathlib import Path
import os

# Disable docs since they won't work correctly through proxy
app = FastAPI(title="MLOps Model API", version="1.0", docs_url=None, redoc_url=None)

# Load model on startup
MODEL = None
# Always use absolute path based on script location
# The model is in ../model/ relative to this script (in app/)
script_dir = Path(__file__).parent.absolute()  # .../deployments/XXX_v1/app/
model_dir = script_dir.parent / "model"  # .../deployments/XXX_v1/model/
MODEL_PATH = model_dir / "model.pkl"

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
        "model_loaded": MODEL is not None,
        "endpoints": {
            "health": "GET /health",
            "predict": "POST /predict with JSON body: {\"features\": [1.0, 2.0, 3.0]}"
        },
        "example_curl": "curl -X POST http://YOUR_SERVER/m/MODELID_v1/predict -H 'Content-Type: application/json' -d '{\"features\": [1.0, 2.0, 3.0, 4.0]}'"
    }

@app.get("/test")
def test():
    """Test endpoint - returns model info and a test prediction"""
    if MODEL is None:
        return {"error": "Model not loaded", "model_path": str(MODEL_PATH)}
    
    # Try a test prediction with dummy data
    try:
        test_features = [1.0, 2.0, 3.0, 4.0]  # Adjust based on your model
        X = np.array([test_features])
        pred = MODEL.predict(X)
        return {
            "model_loaded": True,
            "test_prediction": pred.tolist(),
            "model_type": type(MODEL).__name__,
            "message": "Model is working! Use POST /predict for real predictions."
        }
    except Exception as e:
        return {
            "model_loaded": True,
            "error": f"Test prediction failed: {str(e)}",
            "message": "Model loaded but test failed. Check feature count."
        }

@app.get("/predict")
def predict_get():
    return {
        "message": "Use POST method to make predictions",
        "test_url": "GET /test (to verify model is working)",
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

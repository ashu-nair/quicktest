import json
import joblib
import numpy as np
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time
import os
from typing import Any, Optional

MODEL_PATH = Path("/model/model.pkl")
CONFIG_PATH = Path("/model/model_config.json")
DEFAULT_SCALER_PATH = Path("/model/scaler.pkl")

ROOT_PATH = os.getenv("ROOT_PATH", "")
app = FastAPI(title="Deployed Model API", root_path=ROOT_PATH)


class PredictRequest(BaseModel):
    features: Optional[Any] = None
    # Backward-compatible fallback for older clients.
    data: Optional[Any] = None


def load_model():
    return joblib.load(MODEL_PATH)


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


MODEL = load_model()
CONFIG = load_config()
TARGET_CLASSES = CONFIG.get("target_classes", [])
FEATURES_LIST = CONFIG.get("features")


def load_scaler():
    scaler_path_raw = CONFIG.get("scaler_path")
    scaler_path = Path(scaler_path_raw) if scaler_path_raw else DEFAULT_SCALER_PATH
    if scaler_path.exists():
        return joblib.load(scaler_path)
    return None


def model_is_pipeline(model):
    # sklearn Pipeline exposes named_steps and handles preprocessing internally.
    return hasattr(model, "named_steps")


SCALER = load_scaler()

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {
        "service": "deployed-model-api",
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
    }


@app.post("/predict")
def predict(req: PredictRequest):
    start = time.time()

    payload = req.features if req.features is not None else req.data

    try:
        # payload is dict: {"f1":1, "f2":2}
        if isinstance(payload, dict):
            if not FEATURES_LIST:
                raise ValueError("model_config.json must define a non-empty 'features' list")

            missing_features = [f for f in FEATURES_LIST if f not in payload]
            if missing_features:
                raise ValueError(f"Missing required features: {missing_features}")

            row = [payload[f] for f in FEATURES_LIST]

            X = np.array([row], dtype=float)

        # payload is list: [1,2,3]
        elif isinstance(payload, list):
            X = np.array([payload], dtype=float)

        else:
            raise ValueError("features must be dict or list")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Input parsing failed: {str(e)}")

    try:
        X_for_model = X
        # If model.pkl already contains a Pipeline, keep raw ordered features.
        # Otherwise apply external scaler when available.
        if not model_is_pipeline(MODEL) and SCALER is not None:
            X_for_model = SCALER.transform(X)

        print("Input X:", X_for_model)

        pred_index = int(MODEL.predict(X_for_model)[0])

        if TARGET_CLASSES:
            if pred_index < 0 or pred_index >= len(TARGET_CLASSES):
                raise ValueError(
                    f"Prediction index {pred_index} out of range for target_classes"
                )
            pred_label = TARGET_CLASSES[pred_index]
        else:
            pred_label = str(pred_index)

        if hasattr(MODEL, "predict_proba"):
            proba = MODEL.predict_proba(X_for_model)[0]
            confidence = float(max(proba))
        else:
            confidence = None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model prediction failed: {str(e)}")

    latency = (time.time() - start) * 1000

    return {
        "prediction": pred_label,
        "prediction_index": pred_index,
        "confidence": confidence,
        "latency_ms": latency,
    }


#!/bin/bash
# AWS CloudShell Quick Deploy Script
# Run this in AWS CloudShell: https://console.aws.amazon.com/cloudshell

echo "🚀 Deploying MLOps Platform in CloudShell..."

# Create app directory
mkdir -p ~/mlops-app
cd ~/mlops-app

# Install dependencies
echo "📦 Installing Python packages..."
pip install --user fastapi uvicorn requests numpy scikit-learn joblib 2>&1 | tail -5

# Clone or create structure
echo "🔧 Setting up application..."
mkdir -p app templates storage deployments

# Create minimal app files
cat > app/__init__.py << 'EOF'
EOF

cat > app/config.py << 'EOF'
import os
IS_CLOUD = True
USE_NGROK = False
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000')
EOF

cat > app/db.py << 'EOF'
import sqlite3
from pathlib import Path

DB_PATH = Path("mlops.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS models (
        model_id TEXT PRIMARY KEY,
        model_name TEXT,
        created_at TEXT,
        active_version INTEGER DEFAULT 1
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_id TEXT,
        version INTEGER,
        status TEXT,
        folder_path TEXT,
        image_tag TEXT,
        container_id TEXT,
        internal_port INTEGER,
        created_at TEXT,
        error_log TEXT,
        is_active INTEGER DEFAULT 0,
        FOREIGN KEY(model_id) REFERENCES models(model_id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_id TEXT,
        version INTEGER,
        request_time TEXT,
        latency_ms REAL
    )
    """)
    conn.commit()
    conn.close()
EOF

cat > app/model_runner.py << 'EOF'
import subprocess
import sys
import os
import socket

running_processes = {}

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def start_model_process(model_folder: str, port: int):
    model_path = os.path.expanduser(model_folder)
    app_path = os.path.join(model_path, "app")
    env = os.environ.copy()
    env["MODEL_PATH"] = os.path.join(model_path, "model")
    env["PORT"] = str(port)
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", f"--port", str(port)],
        cwd=app_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return process

def stop_model_process(process_id: str):
    if process_id in running_processes:
        process, port = running_processes[process_id]
        try:
            process.terminate()
            process.wait(timeout=5)
        except:
            try:
                process.kill()
            except:
                pass
        finally:
            del running_processes[process_id]
        return True
    return False

def is_docker_available():
    return False  # CloudShell doesn't have Docker
EOF

# Create templates
cat > templates/model_api.py << 'EOF'
from fastapi import FastAPI
import joblib
import numpy as np
from pathlib import Path
import os

app = FastAPI()
model = None

@app.on_event("startup")
async def load_model():
    global model
    model_path = Path(os.getenv("MODEL_PATH", "/model")) / "model.pkl"
    if model_path.exists():
        model = joblib.load(model_path)
    else:
        print(f"Warning: Model not found at {model_path}")

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}

@app.post("/predict")
def predict(data: dict):
    if model is None:
        return {"error": "Model not loaded"}
    try:
        features = data.get("features", [])
        X = np.array([features])
        pred = model.predict(X)
        return {"prediction": pred.tolist()}
    except Exception as e:
        return {"error": str(e)}
EOF

echo "✅ Setup complete!"
echo ""
echo "📋 Next: Upload your app/main.py and index.html files"
echo "Or use the full project from GitHub"
echo ""
echo "🌐 To start: uvicorn app.main:app --host 0.0.0.0 --port 8000"

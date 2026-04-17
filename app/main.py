import uuid
import shutil
import zipfile
import os
from datetime import datetime
from pathlib import Path
from threading import Thread
import requests
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.db import init_db, get_conn
from app.docker_runner import docker_build, docker_run, docker_stop, get_free_port
from app.nginx_manager import write_routes, can_manage_nginx
from app.config import IS_AZURE, USE_NGROK, PUBLIC_BASE_URL as CFG_PUBLIC_BASE_URL
from fastapi.middleware.cors import CORSMiddleware

# ngrok integration (only for local development)
if USE_NGROK:
    from pyngrok import ngrok
else:
    ngrok = None

PUBLIC_BASE_URL = CFG_PUBLIC_BASE_URL
GLOBAL_PUBLIC_URL = PUBLIC_BASE_URL  # Will be updated with ngrok URL if available


def start_ngrok_tunnel():
    """
    Start ngrok tunnel on port 8000 and return the public URL.
    Falls back to localhost if ngrok fails.
    """
    global GLOBAL_PUBLIC_URL
    
    # Skip ngrok on Azure or if explicitly disabled
    if not USE_NGROK or ngrok is None:
        print(f"📡 Running on Azure: {PUBLIC_BASE_URL}")
        GLOBAL_PUBLIC_URL = PUBLIC_BASE_URL
        return PUBLIC_BASE_URL
    
    try:
        # Kill any existing ngrok processes first (Windows only)
        import subprocess
        import platform
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], capture_output=True)
        else:
            # Linux/Mac - use pkill
            subprocess.run(["pkill", "-f", "ngrok"], capture_output=True)

        # Check for authtoken in environment variable first
        import os
        ngrok_token = os.getenv("NGROK_AUTHTOKEN")
        if ngrok_token:
            print("Using NGROK_AUTHTOKEN from environment")
            ngrok.set_auth_token(ngrok_token)
        else:
            # Try to read from ngrok CLI config
            config_paths = [
                Path.home() / ".ngrok2/ngrok.yml",  # v2 default
                Path.home() / "AppData/Local/ngrok/ngrok.yml",  # Windows v3
                Path.home() / ".config/ngrok/ngrok.yml",  # Linux/mac
            ]

            for config_path in config_paths:
                if config_path.exists():
                    print(f"Checking ngrok config: {config_path}")
                    content = config_path.read_text()
                    # Parse YAML-like format for authtoken
                    for line in content.split("\n"):
                        line = line.strip()
                        if line.startswith("authtoken:") or line.startswith("token:"):
                            token = line.split(":", 1)[1].strip().strip('"').strip("'")
                            if token and token not in ['null', '~', '']:
                                ngrok.set_auth_token(token)
                                print("✅ Auth token loaded from config")
                                break
                    break

        # Connect with explicit parameters
        tunnel = ngrok.connect(addr="8000", proto="http", bind_tls=True)
        public_url = tunnel.public_url
        GLOBAL_PUBLIC_URL = public_url
        print(f"✅ ngrok tunnel started: {public_url}")
        return public_url
    except Exception as e:
        print(f"⚠️ ngrok tunnel failed: {e}")
        import traceback
        traceback.print_exc()
        print(f"⚠️ Falling back to: {PUBLIC_BASE_URL}")
        GLOBAL_PUBLIC_URL = PUBLIC_BASE_URL
        return PUBLIC_BASE_URL


def recover_on_startup():
    """
    After VM reboot, docker containers are gone.
    This function restarts active model versions automatically.
    """
    conn = get_conn()
    cur = conn.cursor()

    # Mark everything as STOPPED and inactive first (since docker doesn't persist)
    cur.execute("""
    UPDATE versions
    SET status='STOPPED', container_id=NULL, is_active=0
    WHERE status='RUNNING'
    """)

    # Find all models that have an active_version > 0
    cur.execute("""
    SELECT model_id, active_version
    FROM models
    WHERE active_version > 0
    """)
    active_models = cur.fetchall()

    for model_id, version in active_models:
        # get image tag for that version
        cur.execute("""
        SELECT image_tag
        FROM versions
        WHERE model_id=? AND version=?
        """, (model_id, version))
        row = cur.fetchone()

        if not row or not row[0]:
            continue

        image_tag = row[0]

        try:
            port = get_free_port()
            route_key = f"{model_id}_v{version}"
            container_id = docker_run(image_tag, port, f"/m/{route_key}")

            # wait for health (same logic as deploy)
            url = f"http://127.0.0.1:{port}/health"
            ok = False
            last_err = ""

            import time
            for _ in range(15):
                try:
                    r = requests.get(url, timeout=2)
                    if r.status_code == 200:
                        ok = True
                        break
                except Exception as e:
                    last_err = str(e)
                time.sleep(1)

            if not ok:
                docker_stop(container_id)
                cur.execute("""
                UPDATE versions
                SET status='FAILED', error_log=?
                WHERE model_id=? AND version=?
                """, (f"Recovery failed: {last_err}", model_id, version))
                continue

            cur.execute("""
            UPDATE versions
            SET status='RUNNING', internal_port=?, container_id=?, error_log=NULL, is_active=1
            WHERE model_id=? AND version=?
            """, (port, container_id, model_id, version))

        except Exception as e:
            cur.execute("""
            UPDATE versions
            SET status='FAILED', error_log=?
            WHERE model_id=? AND version=?
            """, (f"Recovery exception: {str(e)}", model_id, version))

    conn.commit()
    conn.close()

    # refresh nginx with recovered ports
    refresh_nginx()



STORAGE_DIR = Path("storage")
DEPLOYMENTS_DIR = Path("deployments")
TEMPLATE_DIR = Path("templates/model_api")
UI_INDEX_PATH = Path(__file__).resolve().parent.parent / "index.html"

STORAGE_DIR.mkdir(exist_ok=True)
DEPLOYMENTS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="MLOps Auto Deploy - Control API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

    # Start ngrok tunnel in background
    def bg():
        try:
            start_ngrok_tunnel()
        except Exception as e:
            print("ngrok startup failed:", e)

        try:
            recover_on_startup()
        except Exception as e:
            print("Startup recovery failed:", e)

    Thread(target=bg, daemon=True).start()


def get_active_routes():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT model_id, version, internal_port
    FROM versions
    WHERE is_active=1
    """)
    rows = cur.fetchall()
    conn.close()
    return {f"{model_id}_v{version}": port for model_id, version, port in rows}


def refresh_nginx():
    if not can_manage_nginx():
        print("Skipping nginx refresh: unsupported or missing nginx path.")
        return
    active_routes = get_active_routes()
    print(f"Nginx port mappings: {active_routes}")
    model_routes = {model_id: f"http://127.0.0.1:{port}/" for model_id, port in active_routes.items()}
    write_routes({
        "control": "http://127.0.0.1:8000/",
        "models": model_routes,
    })


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/public-url")
def get_public_url():
    """Returns the public URL (ngrok if available, otherwise localhost)."""
    return {"public_url": GLOBAL_PUBLIC_URL}


@app.get("/")
def root():
    if UI_INDEX_PATH.exists():
        return FileResponse(UI_INDEX_PATH)
    return {
        "service": "mlops-control-api",
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
        "ui_missing": str(UI_INDEX_PATH),
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload must be a ZIP file.")

    model_id = str(uuid.uuid4())[:8]
    model_name = Path(file.filename).stem
    model_dir = STORAGE_DIR / model_id
    model_dir.mkdir(parents=True, exist_ok=True)

    zip_path = model_dir / "upload.zip"
    with open(zip_path, "wb") as f:
        f.write(await file.read())

    # Extract
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(model_dir)

    # Find required files
    model_pkl = None
    config_json = None
    for p in model_dir.rglob("*"):
        if p.name == "model.pkl":
            model_pkl = p
        if p.name == "model_config.json":
            config_json = p

    if not model_pkl or not config_json:
        shutil.rmtree(model_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="ZIP must contain model.pkl and model_config.json")

    # Register model in DB
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO models(model_id, model_name, created_at, active_version)
    VALUES (?, ?, ?, ?)
    """, (model_id, model_name, datetime.utcnow().isoformat(), 0))

    conn.commit()
    conn.close()

    return {"model_id": model_id, "model_name": model_name, "message": "Uploaded successfully. Now deploy it."}


@app.post("/deploy/{model_id}")
def deploy(model_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT active_version FROM models WHERE model_id=?", (model_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Model not found")

    active_version = row[0]
    new_version = active_version + 1 if active_version and active_version > 0 else 1

    # prepare deployment folder
    deployment_folder = DEPLOYMENTS_DIR / f"{model_id}_v{new_version}"

    # wipe old deployment folder safely
    if deployment_folder.exists():
      shutil.rmtree(deployment_folder, ignore_errors=True)

    # create fresh deployment folder from template
    shutil.copytree(TEMPLATE_DIR, deployment_folder)

    # ensure model dir exists
    model_dir = deployment_folder / "model"
    model_dir.mkdir(parents=True, exist_ok=True)


    storage_model_dir = STORAGE_DIR / model_id
    model_pkl = next(storage_model_dir.rglob("model.pkl"), None)
    config_json = next(storage_model_dir.rglob("model_config.json"), None)
    if not model_pkl or not config_json:
        raise HTTPException(
            status_code=400,
            detail="Stored model files not found (model.pkl/model_config.json). Please re-upload model ZIP.",
        )

    shutil.copy(model_pkl, deployment_folder / "model/model.pkl")
    shutil.copy(config_json, deployment_folder / "model/model_config.json")

    # Check if Docker is available (not available on Azure B1 Linux runtime)
    from app.model_runner import is_docker_available
    use_docker = is_docker_available()
    
    # Get free port for the model
    port = get_free_port()
    route_key = f"{model_id}_v{new_version}"
    
    if use_docker:
        # === DOCKER MODE (Local development) ===
        import re
        safe_model_id = re.sub(r'[^a-z0-9_.-]', '-', model_id.lower())
        image_tag = f"mlops-{safe_model_id}:v{new_version}"
        
        from app.docker_runner import DOCKER_BIN, docker_build, docker_run
        print(f"Using Docker: {DOCKER_BIN}")
        try:
            docker_build(str(deployment_folder), image_tag)
        except Exception as e:
            conn = get_conn()
            cur = conn.cursor()
            error_msg = str(e)
            cur.execute("""
            INSERT INTO versions(model_id, version, status, folder_path, image_tag, container_id, internal_port, created_at, error_log)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (model_id, new_version, "FAILED", str(deployment_folder), image_tag, "", 0, datetime.utcnow().isoformat(), error_msg))
            conn.commit()
            conn.close()
            raise HTTPException(status_code=500, detail=f"Docker build failed:\n{error_msg}\n\nDocker binary: {DOCKER_BIN}")

        try:
            container_id = docker_run(image_tag, port, f"/m/{route_key}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Run failed: {str(e)}")
    else:
        # === SUBPROCESS MODE (Azure deployment) ===
        print("Docker not available, using subprocess mode")
        from app.model_runner import start_model_process
        try:
            process = start_model_process(str(deployment_folder), port)
            container_id = f"process-{process.pid}"  # Use PID as container ID
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Process start failed: {str(e)}")

    # test model endpoint
        # test model endpoint (retry because container may take time to start)
    url = f"http://127.0.0.1:{port}/health"
    ok = False
    last_err = ""

    for _ in range(15):  # ~15 seconds
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                ok = True
                break
        except Exception as e:
            last_err = str(e)

        import time
        time.sleep(1)

    if not ok:
        # Stop based on mode
        if use_docker:
            from app.docker_runner import docker_stop
            docker_stop(container_id)
        else:
            from app.model_runner import stop_model_process
            stop_model_process(container_id)
        raise HTTPException(status_code=500, detail=f"Container test failed: {last_err}")


    # stop previous running version (rollback-friendly)
    cur.execute("""
    SELECT container_id, folder_path FROM versions
    WHERE model_id=? AND status='RUNNING'
    """, (model_id,))
    prev = cur.fetchone()
    if prev and prev[0]:
        prev_container_id = prev[0]
        if use_docker:
            from app.docker_runner import docker_stop
            docker_stop(prev_container_id)
        else:
            from app.model_runner import stop_model_process
            stop_model_process(prev_container_id)

    # update DB: mark new version running and active
    cur.execute("""
    UPDATE models SET active_version=? WHERE model_id=?
    """, (new_version, model_id))

    # Deactivate all versions for this model
    cur.execute("""
    UPDATE versions SET status='STOPPED', is_active=0
    WHERE model_id=? AND status='RUNNING'
    """, (model_id,))

    # Insert new version as active
    # For subprocess mode, image_tag is the folder path
    tag_for_db = image_tag if use_docker else str(deployment_folder)
    cur.execute("""
    INSERT INTO versions(model_id, version, status, folder_path, image_tag, container_id, internal_port, created_at, error_log, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (model_id, new_version, "RUNNING", str(deployment_folder), tag_for_db, container_id, port, datetime.utcnow().isoformat(), "", 1))

    conn.commit()
    conn.close()

    try:
      refresh_nginx()
    except Exception as e:
      print("⚠️ Nginx refresh failed:", e)

    endpoint_predict = f"{GLOBAL_PUBLIC_URL}/m/{route_key}/predict"
    endpoint_docs = f"{GLOBAL_PUBLIC_URL}/m/{route_key}/docs"
    endpoint_health = f"{GLOBAL_PUBLIC_URL}/m/{route_key}/health"
    print(f"Generated endpoint: {endpoint_predict}")
    print(f"Port mapping: {route_key} -> {port}")
    if can_manage_nginx():
        try:
            route_check = requests.get(endpoint_health, timeout=3)
            print(
                f"Versioned route health check {endpoint_health}: "
                f"{route_check.status_code}"
            )
        except Exception as e:
            print(f"Versioned route health check failed: {e}")


    return {
        "model_id": model_id,
        "active_version": new_version,
        "endpoint_predict": endpoint_predict,
        "endpoint_docs": endpoint_docs
    }


@app.post("/rollback/{model_id}/{version}")
def rollback(model_id: str, version: int):
    from app.model_runner import is_docker_available
    use_docker = is_docker_available()
    
    conn = get_conn()
    cur = conn.cursor()

    # Validate model_id exists
    cur.execute("SELECT model_id FROM models WHERE model_id=?", (model_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Model not found")

    # Validate version exists and get its details
    cur.execute("""
    SELECT image_tag, is_active, internal_port, container_id, status, folder_path
    FROM versions
    WHERE model_id=? AND version=?
    """, (model_id, version))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Requested version not found")

    image_tag, is_active, existing_port, existing_container_id, version_status, folder_path = row

    # Check if version is already active
    if is_active:
        conn.close()
        return {
            "model_id": model_id,
            "rolled_back_to": version,
            "status": "already_active",
            "message": f"Version {version} is already the active version"
        }

    # Get current active version info (for potential rollback on failure)
    cur.execute("""
    SELECT version, container_id, internal_port, image_tag, folder_path
    FROM versions
    WHERE model_id=? AND is_active=1
    """, (model_id,))
    current_active = cur.fetchone()

    # Stop current active container/process if exists
    if current_active:
        current_version, current_container_id, _, _, _ = current_active
        if current_container_id:
            try:
                if use_docker:
                    docker_stop(current_container_id)
                else:
                    from app.model_runner import stop_model_process
                    stop_model_process(current_container_id)
                print(f"Stopped version {current_version}")
            except Exception as e:
                print(f"Warning: Failed to stop {current_container_id}: {e}")

    # Determine port: reuse if version was previously running, otherwise get new port
    if version_status == 'RUNNING' and existing_port:
        port = existing_port
    else:
        port = get_free_port()

    route_key = f"{model_id}_v{version}"
    new_container_id = None

    try:
        # Start selected version (Docker or subprocess)
        if use_docker:
            new_container_id = docker_run(image_tag, port, f"/m/{route_key}")
        else:
            from app.model_runner import start_model_process
            process = start_model_process(folder_path, port)
            new_container_id = f"process-{process.pid}"

        # Test health before committing changes
        url = f"http://127.0.0.1:{port}/health"
        ok = False
        last_err = ""
        for _ in range(15):
            try:
                r = requests.get(url, timeout=2)
                if r.status_code == 200:
                    ok = True
                    break
            except Exception as e:
                last_err = str(e)
            import time
            time.sleep(1)

        if not ok:
            raise RuntimeError(f"Health check failed: {last_err}")

    except Exception as e:
        # Container/process failed - rollback the change
        print(f"Rollback failed for version {version}: {e}")

        if new_container_id:
            try:
                if use_docker:
                    docker_stop(new_container_id)
                else:
                    from app.model_runner import stop_model_process
                    stop_model_process(new_container_id)
            except:
                pass

        # Restart previous version if it was active
        if current_active:
            _, current_container_id, current_port, current_image, current_folder = current_active
            try:
                if use_docker:
                    restarted = docker_run(current_image, current_port, f"/m/{model_id}_v{current_version}")
                else:
                    from app.model_runner import start_model_process
                    proc = start_model_process(current_folder, current_port)
                    restarted = f"process-{proc.pid}"
                
                # Restore previous state in DB
                cur.execute("""
                UPDATE versions SET status='RUNNING', container_id=?, is_active=1
                WHERE model_id=? AND version=?
                """, (restarted, model_id, current_version))
                conn.commit()
                refresh_nginx()
            except Exception as restart_err:
                print(f"Failed to restart previous version: {restart_err}")

        conn.close()
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}. Previous version restored.")

    # Update DB: deactivate all versions, activate selected
    cur.execute("""
    UPDATE versions SET is_active=0, status='STOPPED'
    WHERE model_id=? AND is_active=1
    """, (model_id,))

    cur.execute("""
    UPDATE versions SET status='RUNNING', container_id=?, internal_port=?, is_active=1
    WHERE model_id=? AND version=?
    """, (new_container_id, port, model_id, version))

    cur.execute("""
    UPDATE models SET active_version=? WHERE model_id=?
    """, (version, model_id))

    conn.commit()
    conn.close()

    refresh_nginx()

    endpoint_predict = f"{GLOBAL_PUBLIC_URL}/m/{route_key}/predict"
    endpoint_docs = f"{GLOBAL_PUBLIC_URL}/m/{route_key}/docs"

    print(f"[ROLLBACK] Model {model_id} rolled back to version {version}")
    print(f"Generated endpoint: {endpoint_predict}")
    print(f"Port mapping: {route_key} -> {port}")

    return {
        "model_id": model_id,
        "rolled_back_to": version,
        "status": "success",
        "previous_version": current_active[0] if current_active else None,
        "endpoint_predict": endpoint_predict,
        "endpoint_docs": endpoint_docs
    }
@app.get("/models")
def list_models():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT model_id, model_name, created_at, active_version
    FROM models
    ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()

    out = []
    for model_id, model_name, created_at, active_version in rows:
        out.append({
            "model_id": model_id,
            "name": model_name or model_id,
            "created_at": created_at,
            "active_version": active_version
        })

    return {"models": out}


@app.get("/models/{model_id}/versions")
def list_versions(model_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT version, status, image_tag, internal_port, created_at, error_log, is_active
    FROM versions
    WHERE model_id=?
    ORDER BY version DESC
    """, (model_id,))
    rows = cur.fetchall()
    conn.close()

    versions = []
    for v, status, tag, port, created_at, error_log, is_active in rows:
        versions.append({
            "version": v,
            "status": status,
            "image_tag": tag,
            "port": port,
            "created_at": created_at,
            "error_log": error_log,
            "is_active": bool(is_active)
        })

    return {"model_id": model_id, "versions": versions}


@app.post("/predict/{model_id}")
def control_predict(model_id: str, req: dict):
    """
    Proxy predict request to the currently running model container
    AND store latency metrics.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT active_version FROM models WHERE model_id=?", (model_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Model not found")

    version = row[0]

    cur.execute("""
    SELECT internal_port, is_active
    FROM versions
    WHERE model_id=? AND version=?
    """, (model_id, version))
    row = cur.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Active version not found")

    port, is_active = row
    if not is_active:
        conn.close()
        raise HTTPException(status_code=400, detail="Active model is not running")

    # proxy request
    import time
    start = time.time()
    r = requests.post(
        f"http://127.0.0.1:{port}/predict",
        json=req,
        timeout=10
    )
    latency = (time.time() - start) * 1000
    # store metrics
    cur.execute("""
    INSERT INTO metrics(model_id, version, request_time, latency_ms)
    VALUES (?, ?, ?, ?)
    """, (model_id, version, datetime.utcnow().isoformat(), latency))

    conn.commit()
    conn.close()
    try:
     model_resp = r.json()
    except Exception:
     model_resp = {"raw_text": r.text}

    return {
     "model_id": model_id,
     "version": version,
     "proxy_latency_ms": latency,
     "model_status_code": r.status_code,
     "model_response": model_resp
}

    

    


@app.get("/metrics/{model_id}")
def get_metrics(model_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT active_version FROM models WHERE model_id=?", (model_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Model not found")

    version = row[0]

    cur.execute("""
    SELECT COUNT(*), AVG(latency_ms)
    FROM metrics
    WHERE model_id=? AND version=?
    """, (model_id, version))
    count, avg_latency = cur.fetchone()

    conn.close()

    return {
        "model_id": model_id,
        "active_version": version,
        "requests": count,
        "avg_latency_ms": avg_latency
    }


@app.delete("/models/{model_id}")
def delete_model(model_id: str):
    conn = get_conn()
    cur = conn.cursor()

    # stop active container if exists
    cur.execute("""
    SELECT container_id FROM versions
    WHERE model_id=? AND is_active=1
    """, (model_id,))
    row = cur.fetchone()

    if row and row[0]:
        docker_stop(row[0])

    # delete folders
    storage_path = STORAGE_DIR / model_id
    if storage_path.exists():
        shutil.rmtree(storage_path, ignore_errors=True)

    # delete deployments for that model
    for p in DEPLOYMENTS_DIR.glob(f"{model_id}_v*"):
        shutil.rmtree(p, ignore_errors=True)

    # delete DB rows
    cur.execute("DELETE FROM metrics WHERE model_id=?", (model_id,))
    cur.execute("DELETE FROM versions WHERE model_id=?", (model_id,))
    cur.execute("DELETE FROM models WHERE model_id=?", (model_id,))

    conn.commit()
    conn.close()

    try:
      refresh_nginx()
    except Exception as e:
      print("⚠️ Nginx refresh failed:", e)


    return {"status": "deleted", "model_id": model_id}

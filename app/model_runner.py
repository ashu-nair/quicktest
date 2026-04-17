"""
Alternative model runner using subprocess instead of Docker.
Used on Azure where Docker isn't available inside the container.
"""
import subprocess
import sys
import os
import signal
from pathlib import Path
import socket

# Track running processes
running_processes = {}  # model_id: (process, port)


def get_free_port():
    """Get a free port on the system."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_model_process(model_folder: str, port: int):
    """
    Start a model API as a subprocess (non-Docker alternative).
    
    Args:
        model_folder: Path to the deployment folder containing app/ and model/
        port: Port to run the model API on
    
    Returns:
        process: The subprocess.Popen object
    """
    model_path = Path(model_folder)
    app_path = model_path / "app"
    
    print(f"Starting model process in: {app_path}")
    print(f"Model path: {model_path / 'model'}")
    print(f"Port: {port}")
    
    if not app_path.exists():
        raise RuntimeError(f"App path does not exist: {app_path}")
    
    # Set environment variables
    env = os.environ.copy()
    env["PORT"] = str(port)
    
    # Start the model API as a subprocess with unbuffered output
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", f"--port", str(port)],
        cwd=str(app_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    print(f"Model process started with PID: {process.pid}")
    
    # Wait a moment and check if process crashed immediately
    import time
    time.sleep(0.5)
    process.poll()
    if process.returncode is not None:
        stdout, stderr = process.communicate()
        print(f"❌ Process crashed immediately! Exit code: {process.returncode}")
        print(f"STDOUT: {stdout.decode()[:500]}")
        print(f"STDERR: {stderr.decode()[:500]}")
        raise RuntimeError(f"Model process failed to start: {stderr.decode()[:200]}")
    
    return process


def stop_model_process(process_id: str):
    """Stop a running model process."""
    if process_id in running_processes:
        process, port = running_processes[process_id]
        try:
            # Terminate gracefully first
            process.terminate()
            process.wait(timeout=5)
        except:
            # Force kill if not terminated
            try:
                process.kill()
            except:
                pass
        finally:
            del running_processes[process_id]
        return True
    return False


def is_docker_available():
    """Check if Docker is available on this system."""
    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def deploy_model(model_folder: str, model_id: str, version: int):
    """
    Deploy a model using subprocess (fallback when Docker unavailable).
    
    Returns:
        tuple: (process_id, port, url)
    """
    port = get_free_port()
    process = start_model_process(model_folder, port)
    
    process_id = f"{model_id}-v{version}"
    running_processes[process_id] = (process, port)
    
    # Build internal URL
    url = f"http://localhost:{port}"
    
    return process_id, port, url

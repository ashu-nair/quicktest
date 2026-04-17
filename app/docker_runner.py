import subprocess
import random
import socket
import os
from pathlib import Path

# Auto-detect Docker on Windows
DOCKER_BIN = os.getenv("DOCKER_BIN", "docker")

# Try to find Docker Desktop on Windows if not in PATH
def find_docker():
    global DOCKER_BIN
    if os.name == 'nt':  # Windows
        # Common Docker Desktop paths
        possible_paths = [
            Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe"),
            Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / "Docker/Docker/resources/bin/docker.exe",
            Path(os.environ.get('LOCALAPPDATA', '')) / "Docker/Docker/resources/bin/docker.exe",
        ]
        for path in possible_paths:
            if path.exists():
                DOCKER_BIN = str(path)
                return
        # Try to find in PATH
        import shutil
        docker_in_path = shutil.which("docker")
        if docker_in_path:
            DOCKER_BIN = docker_in_path

find_docker()


def run(cmd, cwd=None):
    try:
        # On Windows, use shell=False to avoid special character interpretation
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=False)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Docker binary not found: {cmd[0]}. "
            "Install Docker Desktop and ensure `docker` is in PATH, "
            "or set DOCKER_BIN environment variable."
        ) from e
    return result.returncode, result.stdout, result.stderr


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))  # OS assigns a free port
    port = s.getsockname()[1]
    s.close()
    return port


def docker_build(build_path: str, image_tag: str):
    # First check if Docker is available
    version_code, _, version_err = run([DOCKER_BIN, "version"])
    if version_code != 0:
        raise RuntimeError(
            f"Docker not available: {version_err}\n"
            "Please ensure Docker Desktop is installed and running."
        )
    
    code, out, err = run([DOCKER_BIN, "build", "-t", image_tag, "."], cwd=build_path)
    if code != 0:
        raise RuntimeError(f"Docker build failed:\n{err}")
    return out


def docker_run(image_tag: str, host_port: int, root_path: str):
    # container exposes 8000 internally
    code, out, err = run([
    DOCKER_BIN, "run", "-d",
    "-e", f"ROOT_PATH={root_path}",
    "-p", f"{host_port}:8000",
    image_tag
])

    if code != 0:
        raise RuntimeError(f"Docker run failed:\n{err}")
    return out.strip()


def docker_stop(container_id: str):
    run([DOCKER_BIN, "rm", "-f", container_id])

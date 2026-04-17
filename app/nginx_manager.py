from pathlib import Path
import subprocess
import os
import shutil

# Detect platform and set appropriate paths
IS_WINDOWS = os.name == 'nt'

if IS_WINDOWS:
    # Common Windows nginx installation paths
    possible_nginx_paths = [
        Path("C:/nginx"),
        Path("C:/Program Files/nginx"),
        Path("C:/Program Files (x86)/nginx"),
        Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / "nginx",
    ]

    NGINX_DIR = None
    for path in possible_nginx_paths:
        if (path / "nginx.exe").exists():
            NGINX_DIR = path
            break

    if NGINX_DIR is None:
        # Fallback - assume nginx is in PATH
        NGINX_DIR = Path(".")

    NGINX_CONF_PATH = NGINX_DIR / "conf/nginx.conf"
    NGINX_SITE_PATH = NGINX_DIR / "conf/sites/mlops.conf"
    # Project root directory where index.html is located
    UI_ROOT = Path(__file__).resolve().parent.parent
else:
    # Linux paths
    NGINX_SITE_PATH = Path("/etc/nginx/sites-available/mlops")
    NGINX_ENABLED_PATH = Path("/etc/nginx/sites-enabled/mlops")
    UI_ROOT = Path("/var/www/mlops-ui")


def get_nginx_bin():
    """Find nginx executable."""
    if IS_WINDOWS:
        if NGINX_DIR and (NGINX_DIR / "nginx.exe").exists():
            return str(NGINX_DIR / "nginx.exe")
        # Try PATH
        nginx_in_path = shutil.which("nginx")
        if nginx_in_path:
            return nginx_in_path
    else:
        return "nginx"
    return None


def can_manage_nginx() -> bool:
    """Check if nginx can be managed on this system."""
    if IS_WINDOWS:
        return get_nginx_bin() is not None
    else:
        return Path("/etc/nginx/sites-available").exists()


def write_routes(routes: dict):
    """
    routes format:
    {
      "control": "http://127.0.0.1:8000/",
      "models": {
          "54b2e32b_v2": "http://127.0.0.1:42037/",
          "683b2426_v1": "http://127.0.0.1:45217/"
      }
    }
    """
    if not can_manage_nginx():
        print("Nginx not available - skipping route configuration")
        return

    control_upstream = routes.get("control", "http://127.0.0.1:8000/")
    model_routes = routes.get("models", {})

    # Build nginx config
    conf = f"""
server {{
    listen 80;
    server_name _;

    client_max_body_size 50M;

    # ========= UI (ALWAYS ON) =========
    location / {{
        root {UI_ROOT};
        index index.html;
        try_files $uri $uri/ /index.html;
    }}

    # ========= Control API =========
    location /control/ {{
        proxy_pass {control_upstream};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}
"""

    # Add model routes
    for route_key, upstream in model_routes.items():
        conf += f"""
    location /m/{route_key}/ {{
        proxy_pass {upstream};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}
"""

    conf += "\n}\n"

    # Write config
    if IS_WINDOWS:
        # On Windows, ensure sites directory exists
        NGINX_SITE_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Write the site config
        NGINX_SITE_PATH.write_text(conf)
        print(f"Nginx site config written: {NGINX_SITE_PATH}")

        # Update main nginx.conf to include sites if not already
        if NGINX_CONF_PATH.exists():
            main_conf = NGINX_CONF_PATH.read_text()
            include_line = f"include {NGINX_SITE_PATH.parent}/*.conf;"
            if include_line not in main_conf and "include sites/" not in main_conf:
                # Add include directive in http block
                if "http {" in main_conf:
                    main_conf = main_conf.replace(
                        "http {",
                        f"http {{\n    {include_line}"
                    )
                    NGINX_CONF_PATH.write_text(main_conf)
                    print(f"Updated main nginx.conf to include sites")

        # Reload nginx (no sudo on Windows)
        nginx_bin = get_nginx_bin()
        if nginx_bin:
            try:
                subprocess.run([nginx_bin, "-t"], check=True)
                subprocess.run([nginx_bin, "-s", "reload"], check=True)
                print("Nginx reloaded successfully")
            except subprocess.CalledProcessError as e:
                print(f"Nginx reload failed: {e}")
                # Try starting nginx if not running
                try:
                    subprocess.Popen([nginx_bin], cwd=NGINX_DIR)
                    print("Nginx started")
                except Exception as start_err:
                    print(f"Nginx start failed: {start_err}")
    else:
        # Linux workflow
        NGINX_SITE_PATH.write_text(conf)
        print(f"Nginx config written: {NGINX_SITE_PATH}")

        # Ensure enabled symlink exists
        if not NGINX_ENABLED_PATH.exists():
            subprocess.run(["sudo", "ln", "-s", str(NGINX_SITE_PATH), str(NGINX_ENABLED_PATH)], check=False)

        # Reload nginx safely
        subprocess.run(["sudo", "nginx", "-t"], check=True)
        subprocess.run(["sudo", "nginx", "-s", "reload"], check=True)

"""Configuration settings for cloud deployment"""
import os

# Detect cloud environments
IS_AZURE = os.getenv('WEBSITE_SITE_NAME') is not None
IS_CLOUDSHELL = os.getenv('CLOUDSHELL_ENVIRONMENT') is not None or os.path.exists('/home/cloudshell-user')
IS_AWS = IS_CLOUDSHELL  # AWS CloudShell is our AWS environment

# Base URL
if IS_AZURE:
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 
                               f"https://{os.getenv('WEBSITE_HOSTNAME', 'localhost:8000')}")
elif IS_CLOUDSHELL:
    # CloudShell uses localhost with port forwarding
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000')
else:
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000')

# Disable ngrok on all cloud environments
USE_NGROK = not IS_AZURE and not IS_CLOUDSHELL and os.getenv('DISABLE_NGROK') != 'true'

# Database path - use Azure's persistent storage if available
DB_PATH = os.getenv('DB_PATH', 'mlops.db')

# Storage directories
STORAGE_DIR = os.getenv('STORAGE_DIR', 'storage')
DEPLOYMENTS_DIR = os.getenv('DEPLOYMENTS_DIR', 'deployments')

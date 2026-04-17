"""Configuration settings for Azure deployment"""
import os

# Detect if running on Azure
IS_AZURE = os.getenv('WEBSITE_SITE_NAME') is not None

# Base URL - Azure provides WEBSITE_HOSTNAME, or use localhost
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 
                           f"https://{os.getenv('WEBSITE_HOSTNAME', 'localhost:8000')}")

# Disable ngrok on Azure
USE_NGROK = not IS_AZURE and os.getenv('DISABLE_NGROK') != 'true'

# Database path - use Azure's persistent storage if available
DB_PATH = os.getenv('DB_PATH', 'mlops.db')

# Storage directories
STORAGE_DIR = os.getenv('STORAGE_DIR', 'storage')
DEPLOYMENTS_DIR = os.getenv('DEPLOYMENTS_DIR', 'deployments')

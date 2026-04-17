"""Configuration settings for cloud deployment"""
import os
import socket

# Detect cloud environments
IS_AZURE = os.getenv('WEBSITE_SITE_NAME') is not None
IS_CLOUDSHELL = os.getenv('CLOUDSHELL_ENVIRONMENT') is not None or os.path.exists('/home/cloudshell-user')
IS_EC2 = os.path.exists('/home/ec2-user') or os.path.isdir('/opt/aws')
IS_AWS = IS_CLOUDSHELL or IS_EC2

# Base URL
if IS_AZURE:
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 
                               f"https://{os.getenv('WEBSITE_HOSTNAME', 'localhost:8000')}")
elif IS_CLOUDSHELL:
    # CloudShell uses localhost with port forwarding
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000')
elif IS_EC2:
    # EC2 - try to get public IP from metadata service or use localhost
    ec2_ip = os.getenv('PUBLIC_BASE_URL')
    if not ec2_ip:
        try:
            import urllib.request
            # Try to get public IP from EC2 metadata service
            req = urllib.request.Request('http://169.254.169.254/latest/meta-data/public-ipv4', timeout=2)
            with urllib.request.urlopen(req) as response:
                public_ip = response.read().decode()
                ec2_ip = f"http://{public_ip}:8000"
        except:
            ec2_ip = 'http://localhost:8000'
    PUBLIC_BASE_URL = ec2_ip
else:
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000')

# Disable ngrok on all cloud environments
USE_NGROK = not IS_AZURE and not IS_CLOUDSHELL and not IS_EC2 and os.getenv('DISABLE_NGROK') != 'true'

# Database path - use Azure's persistent storage if available
DB_PATH = os.getenv('DB_PATH', 'mlops.db')

# Storage directories
STORAGE_DIR = os.getenv('STORAGE_DIR', 'storage')
DEPLOYMENTS_DIR = os.getenv('DEPLOYMENTS_DIR', 'deployments')

#!/bin/bash
# Azure App Service startup script (B1 Basic tier)
# Supports both Docker and subprocess-based model deployment

cd /home/site/wwwroot

echo "🚀 Starting MLOps Platform on Azure..."
echo "📍 Working directory: $(pwd)"

# Create necessary directories
mkdir -p storage deployments

# Install dependencies (if not already installed)
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Environment setup
echo "🔧 Setting up environment..."
export PYTHONUNBUFFERED=1

# Check if Docker is available (B1 tier with custom containers only)
if command -v docker &> /dev/null; then
    echo "🐳 Docker detected - using container mode"
else
    echo "⚙️  Docker not available - using subprocess mode"
fi

# Start the application
echo "🌐 Starting FastAPI server on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

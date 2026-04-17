# Azure Deployment Guide

## Option 1: Azure App Service (FREE TIER - F1)

### Step 1: Install Azure CLI
```powershell
# Download from https://aka.ms/installazurecliwindows
# Or use PowerShell:
Invoke-WebRequest -Uri https://aka.ms/installazurecliwindows -OutFile AzureCLI.msi
Start-Process msiexec.exe -Wait -ArgumentList '/I AzureCLI.msi /quiet'
```

### Step 2: Login to Azure
```powershell
az login
```

### Step 3: Create Resource Group and App Service
```powershell
# Create resource group
az group create --name mlops-rg --location eastus

# Create App Service Plan (FREE F1 tier)
az appservice plan create --name mlops-plan --resource-group mlops-rg --sku F1 --is-linux

# Create Web App with Python 3.11
az webapp create --name your-mlops-app --resource-group mlops-rg --plan mlops-plan --runtime "PYTHON:3.11"
```

### Step 4: Deploy Your Code
```powershell
# Navigate to project directory
cd C:\Users\ashit\OneDrive\Desktop\mlops

# Deploy via ZIP
az webapp deployment source config-zip --resource-group mlops-rg --name your-mlops-app --src mlops.zip
```

### Step 5: Set Startup Command
```powershell
az webapp config set --resource-group mlops-rg --name your-mlops-app --startup-file "startup.sh"
```

### Step 6: Access Your App
- URL: `https://your-mlops-app.azurewebsites.net`
- Always free, fixed URL, no ngrok needed!

## Option 2: Quick Deploy Script

Save and run this PowerShell script:

```powershell
# deploy.ps1
$appName = "mlops-$(Get-Random -Maximum 10000)"
$resourceGroup = "mlops-rg"
$location = "eastus"

Write-Host "Creating Azure resources..."

az group create --name $resourceGroup --location $location
az appservice plan create --name mlops-plan --resource-group $resourceGroup --sku F1 --is-linux
az webapp create --name $appName --resource-group $resourceGroup --plan mlops-plan --runtime "PYTHON:3.11"

Write-Host "Deploying application..."

# Create deployment zip
Compress-Archive -Path * -DestinationPath mlops.zip -Force

az webapp deployment source config-zip --resource-group $resourceGroup --name $appName --src mlops.zip
az webapp config set --resource-group $resourceGroup --name $appName --startup-file "startup.sh"

Write-Host "✅ Deployed! Access at: https://$appName.azurewebsites.net"
```

## Important Notes

1. **Free Tier Limits (F1):**
   - 1GB memory
   - 1GB storage
   - Custom domains supported (add your own domain for $10/year)
   - Runs 24/7

2. **Docker on Azure Free Tier:**
   - Docker doesn't work on Azure App Service Free tier (F1)
   - For Docker containers, use Azure Container Instances or upgrade to Basic tier (B1 - ~$13/month)

3. **Database:**
   - SQLite is used (file-based, no external DB needed)
   - Data persists in `/home/site/wwwroot/`

4. **To upgrade later:**
   ```powershell
   az appservice plan update --name mlops-plan --resource-group mlops-rg --sku B1
   ```

## Troubleshooting

**If deployment fails:**
```powershell
# Check logs
az webapp log tail --name your-mlops-app --resource-group mlops-rg
```

**If app doesn't start:**
- Check `startup.sh` permissions
- Verify Python version in Azure portal

**Custom domain (optional, paid):**
```powershell
az webapp config hostname add --webapp-name your-mlops-app --resource-group mlops-rg --hostname yourdomain.com
```

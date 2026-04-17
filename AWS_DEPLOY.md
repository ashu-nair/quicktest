# AWS Deployment Guide - MLOps Platform

## Option 1: AWS Elastic Beanstalk (Easiest - Free Tier)

### Step 1: Install AWS CLI
```powershell
# Download: https://awscli.amazonaws.com/AWSCLIV2.msi
# Or PowerShell:
msiexec.exe /i https://awscli.amazonaws.com/AWSCLIV2.msi /qn
```

### Step 2: Configure AWS
```powershell
aws configure
# Enter:
# - AWS Access Key ID (from IAM console)
# - AWS Secret Access Key
# - Default region: us-east-1
# - Output format: json
```

### Step 3: Create Application
```powershell
# Create Elastic Beanstalk application
aws elasticbeanstalk create-application --application-name mlops-platform

# Create environment (t2.micro is free tier)
aws elasticbeanstalk create-environment \
  --application-name mlops-platform \
  --environment-name mlops-env \
  --solution-stack-name "64bit Amazon Linux 2023 v4.0.0 running Python 3.11" \
  --option-settings \
  Namespace=aws:autoscaling:launchconfiguration,OptionName=InstanceType,Value=t2.micro \
  Namespace=aws:elasticbeanstalk:environment,OptionName=EnvironmentType,Value=SingleInstance
```

### Step 4: Deploy Code
```powershell
# Create deployment package
cd C:\Users\ashit\OneDrive\Desktop\mlops
Compress-Archive -Path app, templates, index.html, requirements.txt, .ebextensions -DestinationPath mlops-aws.zip -Force

# Upload and deploy
aws elasticbeanstalk create-application-version \
  --application-name mlops-platform \
  --version-label v1 \
  --source-bundle S3Bucket=your-bucket,S3Key=mlops-aws.zip

aws elasticbeanstalk update-environment \
  --environment-name mlops-env \
  --version-label v1
```

## Option 2: AWS EC2 (More Control - Free Tier)

### Quick Deploy Script
Save as `deploy-to-aws.ps1`:

```powershell
# deploy-to-aws.ps1
param(
    [string]$KeyName = "mlops-key",
    [string]$InstanceType = "t2.micro"
)

Write-Host "🚀 Deploying to AWS EC2..."

# Create key pair if doesn't exist
aws ec2 create-key-pair --key-name $KeyName --query 'KeyMaterial' --output text | Out-File -FilePath "$KeyName.pem" -Encoding ascii

# Create security group
$sgId = aws ec2 create-security-group --group-name mlops-sg --description "MLOps security group" --query 'GroupId' --output text
aws ec2 authorize-security-group-ingress --group-id $sgId --protocol tcp --port 22 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $sgId --protocol tcp --port 8000 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $sgId --protocol tcp --port 80 --cidr 0.0.0.0/0

# Launch instance
$amiId = aws ec2 describe-images --owners amazon --filters "Name=name,Values=amzn2-ami-hvm-*-x86_64-gp2" --query 'Images[0].ImageId' --output text
$instanceId = aws ec2 run-instances --image-id $amiId --count 1 --instance-type $InstanceType --key-name $KeyName --security-group-ids $sgId --query 'Instances[0].InstanceId' --output text

Write-Host "⏳ Waiting for instance to start..."
aws ec2 wait instance-running --instance-ids $instanceId

$publicIp = aws ec2 describe-instances --instance-ids $instanceId --query 'Reservations[0].Instances[0].PublicIpAddress' --output text

Write-Host "🌐 Instance running at: $publicIp"
Write-Host "📦 Deploying application..."

# Create deploy script
$deployScript = @"
#!/bin/bash
yum update -y
yum install -y python3 python3-pip git
mkdir -p /app
cd /app
# Clone or copy your code here
pip3 install -r requirements.txt
# Start app
uvicorn app.main:app --host 0.0.0.0 --port 8000
"@

# Save connection info
@{
    InstanceId = $instanceId
    PublicIP = $publicIp
    KeyFile = "$KeyName.pem"
} | ConvertTo-Json | Out-File aws-deployment-info.json

Write-Host "🎉 DEPLOYED!"
Write-Host "URL: http://$publicIp:8000"
Write-Host "SSH: ssh -i $KeyName.pem ec2-user@$publicIp"
```

## Option 3: One-Click Deploy (Simplest)

### Using AWS CloudShell (Browser-based, no install needed)

1. Go to: https://console.aws.amazon.com/cloudshell
2. Paste these commands:

```bash
# In AWS CloudShell (browser)
git clone https://github.com/yourusername/mlops.git  # Or upload your files
cd mlops
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## AWS Free Tier Limits

| Resource | Free Tier | Your Use |
|----------|----------|----------|
| EC2 t2.micro | 750 hours/month | ✅ 1 instance |
| Elastic Beanstalk | Same as EC2 | ✅ Free |
| Data Transfer | 100GB/month | ✅ Fine |
| Storage (EBS) | 30GB | ✅ Fine |

## Quick Test URL

After deploy, access at:
- **EC2:** `http://<EC2-IP>:8000`
- **Elastic Beanstalk:** `http://mlops-env.<region>.elasticbeanstalk.com`

## Delete to Save Credits

```powershell
# EC2
cd C:\Users\ashit\OneDrive\Desktop\mlops
$info = Get-Content aws-deployment-info.json | ConvertFrom-Json
aws ec2 terminate-instances --instance-ids $info.InstanceId

# Elastic Beanstalk
aws elasticbeanstalk terminate-environment --environment-name mlops-env
```

## Recommended: EC2 t2.micro (Simplest)

- Free for 12 months
- Full control
- Fixed IP (can assign Elastic IP)
- Easy to deploy

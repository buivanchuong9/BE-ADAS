# WINDOWS SERVER DEPLOYMENT GUIDE
# ================================
# Production deployment guide for ADAS Backend on Windows Server with IIS

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [SQL Server Setup](#sql-server-setup)
3. [Python Environment](#python-environment)
4. [Application Configuration](#application-configuration)
5. [IIS Configuration](#iis-configuration)
6. [SSL Certificate](#ssl-certificate)
7. [Testing](#testing)
8. [Monitoring](#monitoring)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Hardware Requirements
- **CPU**: Intel Xeon or AMD EPYC (8+ cores recommended)
- **RAM**: 16GB minimum, 32GB recommended
- **GPU**: NVIDIA GPU with CUDA 11.8+ (optional but recommended)
  - GTX 1660 or better for development
  - RTX 3060 or better for production
- **Storage**: 
  - 100GB SSD for OS and applications
  - 500GB+ HDD for video storage

### Software Requirements
- **OS**: Windows Server 2019/2022 (64-bit)
- **SQL Server**: 2019 Developer/Standard/Enterprise Edition
- **IIS**: 10.0+
- **Python**: 3.11.x (64-bit)
- **CUDA Toolkit**: 11.8 or 12.1 (if using NVIDIA GPU)
- **.NET Framework**: 4.8+

---

## SQL Server Setup

### 1. Install SQL Server 2019

```powershell
# Download SQL Server 2019 Developer Edition (free)
# https://www.microsoft.com/en-us/sql-server/sql-server-downloads

# During installation:
# - Choose "Database Engine Services"
# - Enable "Mixed Mode" authentication
# - Set SA password: YourStrongPassword123!
# - Add current Windows user as SQL admin
```

### 2. Enable TCP/IP Protocol

```powershell
# Open SQL Server Configuration Manager
# Navigate to: SQL Server Network Configuration > Protocols for MSSQLSERVER
# Enable TCP/IP protocol
# Restart SQL Server service
```

### 3. Create Database

```sql
-- Connect with SSMS or Azure Data Studio

-- Create ADAS database
CREATE DATABASE adas_production;
GO

-- Create application user
USE adas_production;
GO

CREATE LOGIN adas_user WITH PASSWORD = 'AdasUser2025!@#';
CREATE USER adas_user FOR LOGIN adas_user;
ALTER ROLE db_owner ADD MEMBER adas_user;
GO

-- Verify connection
SELECT @@VERSION;
```

### 4. Configure Firewall

```powershell
# Allow SQL Server through Windows Firewall
New-NetFirewallRule -DisplayName "SQL Server" -Direction Inbound -Protocol TCP -LocalPort 1433 -Action Allow
```

---

## Python Environment

### 1. Install Python 3.11

```powershell
# Download Python 3.11.x from python.org (Windows x64 installer)
# https://www.python.org/downloads/windows/

# During installation:
# ✓ Add Python to PATH
# ✓ Install for all users
# Installation path: C:\Python311
```

### 2. Install Microsoft ODBC Driver

```powershell
# Download Microsoft ODBC Driver 18 for SQL Server
# https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

# Run installer: msodbcsql.msi
```

### 3. Create Virtual Environment

```powershell
# Navigate to project directory
cd C:\inetpub\wwwroot\adas-backend

# Create virtual environment
C:\Python311\python.exe -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip setuptools wheel
```

### 4. Install Dependencies

```powershell
# Install production requirements
pip install -r requirements.txt

# Install CUDA-enabled PyTorch (if using NVIDIA GPU)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# Verify installations
python -c "import torch; print(torch.cuda.is_available())"
python -c "import cv2; print(cv2.__version__)"
python -c "import pyodbc; print(pyodbc.drivers())"
```

---

## Application Configuration

### 1. Environment Variables

Create `.env` file in project root:

```env
# Database Configuration
DATABASE_URL=mssql+pyodbc://adas_user:AdasUser2025!@#@localhost/adas_production?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes

# Application Settings
APP_NAME=ADAS Production API
APP_VERSION=2.0.0
DEBUG=False
HOST=0.0.0.0
PORT=52000

# Security
SECRET_KEY=change-this-to-random-64-char-string-in-production
JWT_SECRET_KEY=change-this-to-another-random-64-char-string

# CORS
CORS_ORIGINS=https://adas-api.aiotlab.edu.vn,https://dashboard.aiotlab.edu.vn

# Storage
STORAGE_BASE_PATH=C:/inetpub/wwwroot/adas-backend/backend/storage
MAX_UPLOAD_SIZE_MB=500

# Processing
MAX_CONCURRENT_JOBS=4
JOB_TIMEOUT_SECONDS=3600

# Domain
API_DOMAIN=https://adas-api.aiotlab.edu.vn:52000
```

### 2. Initialize Database

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run Alembic migrations
cd backend
alembic upgrade head

# Verify tables created
python -c "from app.db.session import engine; print(engine.table_names())"
```

### 3. Create Storage Directories

```powershell
# Create storage structure
New-Item -Path "backend\storage\raw" -ItemType Directory -Force
New-Item -Path "backend\storage\result" -ItemType Directory -Force
New-Item -Path "backend\storage\audio_cache" -ItemType Directory -Force
New-Item -Path "backend\storage\images" -ItemType Directory -Force

# Set permissions (IIS_IUSRS needs write access)
icacls "backend\storage" /grant "IIS_IUSRS:(OI)(CI)M" /T
```

---

## IIS Configuration

### 1. Install IIS and HttpPlatformHandler

```powershell
# Install IIS with ASP.NET
Install-WindowsFeature -name Web-Server -IncludeManagementTools
Install-WindowsFeature -name Web-Asp-Net45

# Download HttpPlatformHandler v1.2
# https://www.iis.net/downloads/microsoft/httpplatformhandler

# Install HttpPlatformHandler MSI
```

### 2. Create IIS Application Pool

```powershell
# Open IIS Manager
# Create new Application Pool:
#   Name: AdasBackendPool
#   .NET CLR Version: No Managed Code
#   Managed Pipeline Mode: Integrated
#   Identity: ApplicationPoolIdentity

# Advanced Settings:
#   Start Mode: AlwaysRunning
#   Idle Timeout: 0 (disable)
```

### 3. Create IIS Website

```powershell
# Create website in IIS Manager:
#   Site name: ADAS-Backend-API
#   Application pool: AdasBackendPool
#   Physical path: C:\inetpub\wwwroot\adas-backend
#   Binding: 
#     Type: https
#     IP: All Unassigned
#     Port: 52000
#     Hostname: adas-api.aiotlab.edu.vn
```

### 4. Configure web.config

Create `web.config` in project root:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="httpPlatformHandler" path="*" verb="*" modules="httpPlatformHandler" resourceType="Unspecified" requireAccess="Script" />
    </handlers>
    <httpPlatform 
      processPath="C:\inetpub\wwwroot\adas-backend\venv\Scripts\python.exe"
      arguments="-m uvicorn app.main:app --host 0.0.0.0 --port %HTTP_PLATFORM_PORT%"
      startupTimeLimit="60" 
      startupRetryCount="3"
      stdoutLogEnabled="true"
      stdoutLogFile=".\logs\stdout.log">
      <environmentVariables>
        <environmentVariable name="PYTHONUNBUFFERED" value="1" />
        <environmentVariable name="PYTHONIOENCODING" value="utf-8" />
      </environmentVariables>
    </httpPlatform>
    <security>
      <requestFiltering>
        <requestLimits maxAllowedContentLength="524288000" /> <!-- 500 MB -->
      </requestFiltering>
    </security>
  </system.webServer>
</configuration>
```

---

## SSL Certificate

### 1. Generate Self-Signed Certificate (Development)

```powershell
# Create self-signed certificate
$cert = New-SelfSignedCertificate `
    -DnsName "adas-api.aiotlab.edu.vn" `
    -CertStoreLocation "cert:\LocalMachine\My" `
    -NotAfter (Get-Date).AddYears(2)

# Export certificate
$pwd = ConvertTo-SecureString -String "CertPassword123" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath "C:\certs\adas-api.pfx" -Password $pwd

# Import to Trusted Root
Import-PfxCertificate -FilePath "C:\certs\adas-api.pfx" -CertStoreLocation "cert:\LocalMachine\Root" -Password $pwd
```

### 2. Bind Certificate to IIS

```powershell
# In IIS Manager > Site > Bindings:
# - Add HTTPS binding
# - Port: 52000
# - SSL certificate: adas-api.aiotlab.edu.vn
```

### 3. Production Certificate (Let's Encrypt)

```powershell
# Install win-acme for Let's Encrypt certificates
# https://www.win-acme.com/

# Run win-acme to generate certificate
wacs.exe --target iis --siteid 1 --installation iis --store pemfiles --pemfilespath C:\certs
```

---

## Testing

### 1. Test Locally

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run application
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 52000

# Test in browser
# https://localhost:52000/docs
```

### 2. Test IIS Deployment

```powershell
# Restart IIS site
iisreset

# Check logs
Get-Content "C:\inetpub\wwwroot\adas-backend\logs\stdout.log" -Tail 50

# Test API
curl https://adas-api.aiotlab.edu.vn:52000/health
curl https://adas-api.aiotlab.edu.vn:52000/docs
```

### 3. Load Testing

```powershell
# Install Apache Bench (via Chocolatey)
choco install apache-httpd

# Run load test
ab -n 1000 -c 10 https://adas-api.aiotlab.edu.vn:52000/health
```

---

## Monitoring

### 1. Application Logs

```powershell
# View application logs
Get-Content "backend\logs\app.log" -Tail 100 -Wait

# View IIS logs
Get-Content "C:\inetpub\logs\LogFiles\W3SVC1\*.log" | Select-Object -Last 100
```

### 2. Performance Counters

```powershell
# Monitor CPU/Memory
Get-Counter '\Processor(_Total)\% Processor Time'
Get-Counter '\Memory\Available MBytes'

# Monitor IIS
Get-Counter '\Web Service(_Total)\Current Connections'
Get-Counter '\ASP.NET Applications(__Total__)\Requests/Sec'
```

### 3. SQL Server Monitoring

```sql
-- Check active connections
SELECT * FROM sys.dm_exec_connections;

-- Check running queries
SELECT * FROM sys.dm_exec_requests;

-- Check database size
EXEC sp_spaceused;
```

---

## Troubleshooting

### Common Issues

#### 1. "Module not found" errors
```powershell
# Ensure virtual environment is activated
.\venv\Scripts\Activate.ps1

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

#### 2. SQL Server connection fails
```powershell
# Test ODBC connection
sqlcmd -S localhost -U adas_user -P "AdasUser2025!@#"

# Check SQL Server service
Get-Service MSSQLSERVER

# Enable TCP/IP in SQL Server Configuration Manager
```

#### 3. IIS returns 500 error
```powershell
# Check stdout log
Get-Content ".\logs\stdout.log"

# Check IIS application pool
Get-IISAppPool -Name "AdasBackendPool"

# Restart application pool
Restart-WebAppPool -Name "AdasBackendPool"
```

#### 4. Port 52000 already in use
```powershell
# Find process using port
netstat -ano | findstr :52000

# Kill process
taskkill /PID <process_id> /F
```

### Performance Optimization

```powershell
# Increase IIS request timeout
Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' `
    -Filter "system.webServer/httpPlatform" `
    -Name "requestTimeout" -Value "00:30:00"

# Enable IIS compression
Enable-WindowsOptionalFeature -Online -FeatureName IIS-HttpCompressionDynamic
```

---

## Maintenance

### Daily Tasks
- Check application logs for errors
- Monitor disk space in storage directories
- Review SQL Server performance

### Weekly Tasks
- Analyze API usage statistics
- Clean old video files (>30 days)
- Update dependencies if needed

### Monthly Tasks
- Full database backup
- Review and rotate logs
- Check for security updates

---

## Production Checklist

- [ ] SQL Server installed and configured
- [ ] Database created with proper permissions
- [ ] Python 3.11 installed
- [ ] Virtual environment created
- [ ] All dependencies installed
- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] Storage directories created with permissions
- [ ] IIS installed with HttpPlatformHandler
- [ ] Application pool created
- [ ] Website configured in IIS
- [ ] SSL certificate installed and bound
- [ ] Firewall rules configured
- [ ] Application starts successfully
- [ ] API documentation accessible
- [ ] Health check endpoint responds
- [ ] Load testing completed
- [ ] Monitoring configured
- [ ] Backup strategy implemented

---

## Support

For issues or questions:
- Email: support@aiotlab.edu.vn
- Documentation: https://adas-api.aiotlab.edu.vn:52000/docs
- Repository: Internal GitLab

**Document Version**: 2.0  
**Last Updated**: 2025-12-26  
**Author**: Senior ADAS Engineer

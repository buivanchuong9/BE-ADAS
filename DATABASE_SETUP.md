# Database Setup Guide

## Overview

This guide explains how to set up the SQL Server database for the ADAS backend system.

**IMPORTANT**: The database schema is defined in `database_schema.sql` and is the **single source of truth**. Do NOT modify the database manually or run Alembic migrations.

## Prerequisites

### 1. SQL Server Installation

You need Microsoft SQL Server installed. Supported versions:
- SQL Server 2019 or later
- SQL Server Express (free)
- SQL Server Developer Edition (free for development)

**Download**: https://www.microsoft.com/en-us/sql-server/sql-server-downloads

### 2. ODBC Driver 18 for SQL Server

**CRITICAL**: The backend requires ODBC Driver 18 (not Driver 17).

#### Windows Installation
```powershell
# Download and install from Microsoft
# https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

# Or use winget
winget install Microsoft.ODBCDriver.18
```

#### macOS Installation
```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew update
brew install msodbcsql18
```

#### Linux (Ubuntu/Debian) Installation
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

#### Verify Installation
```bash
# Windows
odbcad32

# macOS/Linux
odbcinst -q -d
```

You should see "ODBC Driver 18 for SQL Server" in the list.

## Database Setup

### Step 1: Create Database

Run the schema creation script:

```bash
# Using sqlcmd (comes with SQL Server)
sqlcmd -S localhost -U sa -P YourStrong@Passw0rd -i database_schema.sql

# Or using SQL Server Management Studio (SSMS)
# 1. Open SSMS
# 2. Connect to your SQL Server instance
# 3. Open database_schema.sql
# 4. Execute (F5)
```

This script will:
- Create the `adas_production` database
- Create all 9 tables with proper schema
- Add indexes for performance
- Insert sample data (admin user, sample vehicle, model versions)

### Step 2: Verify Database

Connect to SQL Server and verify:

```sql
USE adas_production;

-- Check all tables exist
SELECT TABLE_NAME 
FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;

-- Should show:
-- alerts
-- driver_states
-- model_versions
-- safety_events
-- traffic_signs
-- trips
-- users
-- vehicles
-- video_jobs

-- Verify sample data
SELECT * FROM users;
SELECT * FROM vehicles;
SELECT * FROM model_versions;
```

## Backend Configuration

### Step 1: Environment Variables

Create or update `.env` file in the project root:

```env
# Database Configuration
DB_HOST=localhost
DB_PORT=1433
DB_NAME=adas_production
DB_USER=sa
DB_PASSWORD=YourStrong@Passw0rd
DB_DRIVER=ODBC Driver 18 for SQL Server

# IMPORTANT: For ODBC Driver 18
# TrustServerCertificate=yes is required for local/dev environments
# This is already configured in config.py

# Application
DEBUG=True
ENVIRONMENT=development

# Security
SECRET_KEY=your-secret-key-change-in-production-min-32-characters-long
```

### Step 2: Test Connection

```bash
cd /Users/chuong/Desktop/AI/backend-python
python backend/scripts/test_connection.py
```

Expected output:
```
✓ Connected to SQL Server successfully
✓ Database: adas_production
✓ Tables found: 9
```

### Step 3: Start Backend

```bash
cd /Users/chuong/Desktop/AI/backend-python
python run.py
```

Expected output:
```
================================================================================
ADAS Backend API v2.0.0 Starting...
================================================================================
Initializing database connection...
✓ Database initialized successfully
✓ Job service initialized with 2 workers
API Documentation: http://0.0.0.0:52000/docs
================================================================================
```

### Step 4: Verify API

Open browser to: http://localhost:52000/docs

You should see the Swagger UI with all API endpoints.

## Migration Strategy

### Why Alembic is Disabled

This project uses **manual SQL schema management** instead of Alembic migrations because:

1. **Database is the source of truth**: `database_schema.sql` defines the complete schema
2. **Manual modifications**: Database has been manually modified for production
3. **Stability**: Prevents migration conflicts and schema drift
4. **Simplicity**: Direct SQL is easier to review and understand

### Alembic Status

- **Alembic is installed** but migrations are NOT auto-executed
- `alembic.ini` is configured but marked as disabled
- Future schema changes should:
  1. Update `database_schema.sql` first
  2. Apply changes to database manually
  3. Update SQLAlchemy models to match
  4. Optionally create Alembic migration for documentation

### DO NOT RUN

```bash
# ❌ DO NOT RUN THIS
alembic upgrade head

# ❌ DO NOT RUN THIS
alembic revision --autogenerate
```

The database schema is already correct from `database_schema.sql`.

## Troubleshooting

### Error: "Can't open lib 'ODBC Driver 18 for SQL Server'"

**Solution**: Install ODBC Driver 18 (see Prerequisites section)

### Error: "SSL Provider: The certificate chain was issued by an authority that is not trusted"

**Solution**: This is already handled by `TrustServerCertificate=yes` in the connection string. If you still see this error, verify your `config.py` has been updated.

### Error: "Login failed for user 'sa'"

**Solution**: 
1. Verify SQL Server is running
2. Check username/password in `.env` file
3. Ensure SQL Server authentication is enabled (not just Windows auth)

### Error: "Invalid column name 'job_id'"

**Solution**: 
1. Drop and recreate database: `DROP DATABASE adas_production;`
2. Run `database_schema.sql` again
3. Restart backend

### Error: "Cannot connect to SQL Server"

**Solution**:
1. Verify SQL Server is running: `services.msc` (Windows) or `systemctl status mssql-server` (Linux)
2. Check firewall allows port 1433
3. Verify SQL Server is listening on TCP/IP (SQL Server Configuration Manager)

## Database Schema Reference

### Tables

1. **users** - User accounts (admin, operator, viewer, driver)
2. **vehicles** - Vehicle fleet management
3. **trips** - Driving trip records
4. **video_jobs** - Video processing jobs
5. **safety_events** - Detected safety events (FCW, LDW, etc.)
6. **driver_states** - Driver monitoring data
7. **traffic_signs** - Traffic sign detections
8. **alerts** - Real-time alerts
9. **model_versions** - AI model version tracking

### Default Credentials

**Admin User**:
- Username: `admin`
- Password: `Admin123!@#`
- Email: `admin@adas.vn`

**Database**:
- User: `sa`
- Password: `YourStrong@Passw0rd` (change in production!)

## Production Deployment

For production deployment:

1. **Change default passwords**:
   - SQL Server `sa` password
   - Admin user password
   - `SECRET_KEY` in `.env`

2. **SSL Certificates**:
   - Install valid SSL certificate on SQL Server
   - Update connection string: `TrustServerCertificate=no`

3. **Firewall**:
   - Restrict SQL Server port 1433 to backend server only
   - Use VPN or private network

4. **Backup**:
   - Set up automated database backups
   - Test restore procedures

5. **Monitoring**:
   - Enable SQL Server audit logging
   - Monitor connection pool usage
   - Set up alerts for failed logins

## Additional Resources

- [SQL Server Documentation](https://learn.microsoft.com/en-us/sql/sql-server/)
- [ODBC Driver 18 Documentation](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- [SQLAlchemy SQL Server Dialect](https://docs.sqlalchemy.org/en/20/dialects/mssql.html)

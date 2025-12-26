# PHASE 1: DATABASE MIGRATION COMPLETE
# =====================================
# SQL Server Setup Guide for Windows

## Prerequisites

### 1. Install SQL Server Developer Edition (Free)

Download from Microsoft:
https://www.microsoft.com/en-us/sql-server/sql-server-downloads

1. Download SQL Server 2022 Developer Edition
2. Run installer
3. Choose "Basic" installation
4. Accept license terms
5. Wait for installation to complete
6. Note the connection string shown at the end

**Default credentials:**
- Server: localhost or (localdb)\MSSQLLocalDB
- Authentication: Windows Authentication or SQL Server Authentication
- Username: sa
- Password: (set during installation)

### 2. Install ODBC Driver 17 for SQL Server

Download from:
https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

Or install via command:
```powershell
# Windows PowerShell (Run as Administrator)
winget install Microsoft.ODBCDriver
```

### 3. Install SQL Server Management Studio (SSMS) - Optional but Recommended

Download from:
https://aka.ms/ssmsfullsetup

SSMS provides a GUI to manage databases.

## Python Environment Setup

### 1. Install Python Dependencies

```bash
cd /Users/chuong/Desktop/AI/backend-python
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` and update database credentials:
```env
DB_HOST=localhost
DB_PORT=1433
DB_NAME=adas_production
DB_USER=sa
DB_PASSWORD=YourStrong@Passw0rd  # Change this!
DB_DRIVER=ODBC Driver 17 for SQL Server
```

## Database Setup

### Option A: Using Alembic (Recommended for Production)

1. **Create database manually in SSMS or via SQL:**

```sql
-- Connect to SQL Server and run:
CREATE DATABASE adas_production;
GO
```

2. **Generate initial migration:**

```bash
alembic revision --autogenerate -m "Initial database schema"
```

3. **Apply migration:**

```bash
alembic upgrade head
```

4. **Seed initial data:**

```bash
python backend/scripts/seed_data.py
```

### Option B: Quick Setup for Development

```bash
# This will create all tables directly (skip Alembic)
python backend/scripts/init_db.py

# Then seed data
python backend/scripts/seed_data.py
```

## Verify Database Setup

### Using Python Script

Create `backend/scripts/test_connection.py`:

```python
import asyncio
from app.db.session import engine
from sqlalchemy import text

async def test_connection():
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT @@VERSION"))
        version = result.scalar()
        print(f"✓ Connected to SQL Server:")
        print(f"  {version}")

if __name__ == "__main__":
    asyncio.run(test_connection())
```

Run it:
```bash
python backend/scripts/test_connection.py
```

### Using SSMS

1. Open SQL Server Management Studio
2. Connect to `localhost`
3. Expand Databases
4. You should see `adas_production`
5. Expand Tables - you should see:
   - dbo.users
   - dbo.vehicles
   - dbo.trips
   - dbo.video_jobs
   - dbo.safety_events
   - dbo.traffic_signs
   - dbo.driver_states
   - dbo.alerts
   - dbo.alert_history
   - dbo.model_versions

## Database Schema Overview

```
users (10 columns)
├── id, username, email, password_hash, role
├── full_name, phone, is_active
└── created_at, updated_at, last_login

vehicles (10 columns)
├── id, plate_number, vin, make, model, year, color
├── user_id (FK → users.id)
└── created_at, updated_at, notes

trips (20+ columns)
├── id, driver_id (FK), vehicle_id (FK)
├── start_time, end_time, status
├── start/end location, distance, duration, speed metrics
├── safety_score, events_count, critical_events_count
└── created_at, updated_at

video_jobs (16 columns)
├── id, job_id (UUID), trip_id (FK)
├── filename, video_type, status, device
├── input_path, output_path
├── progress tracking, error handling
└── timestamps (created, started, completed)

safety_events (18 columns)
├── id, trip_id (FK), video_job_id (FK), vehicle_id (FK)
├── event_type, severity, risk_score, time_to_event
├── timestamp, frame_number, description, explanation
├── context_data (JSON), snapshot_path
└── created_at

traffic_signs (12 columns)
├── id, trip_id (FK), video_job_id (FK)
├── sign_type, sign_value, confidence
├── timestamp, frame_number, bbox coordinates
└── created_at

driver_states (16 columns)
├── id, trip_id (FK), video_job_id (FK)
├── timestamp, frame_number
├── fatigue/distraction scores, eye/mouth metrics
├── head pose (yaw, pitch, roll)
├── metrics (JSON)
└── created_at

alerts (14 columns)
├── id, trip_id (FK), safety_event_id (FK)
├── alert_type, severity, status
├── message, tts_text
├── delivery and acknowledgement tracking
└── timestamps

alert_history (archival table)
model_versions (AI model tracking)
```

## Common Issues & Solutions

### Issue: "Login failed for user 'sa'"

**Solution:**
1. Ensure SQL Server authentication is enabled
2. Reset sa password in SSMS
3. Update `.env` file with correct password

### Issue: "ODBC Driver not found"

**Solution:**
Install ODBC Driver 17:
```powershell
winget install Microsoft.ODBCDriver
```

### Issue: "Database does not exist"

**Solution:**
Create database in SSMS:
```sql
CREATE DATABASE adas_production;
```

### Issue: "Connection timeout"

**Solution:**
1. Check SQL Server is running: Services → SQL Server (MSSQLSERVER)
2. Enable TCP/IP in SQL Server Configuration Manager
3. Restart SQL Server service

## Next Steps

After database is set up:

1. **Test the API:**
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 52000
   ```

2. **Test authentication:**
   ```bash
   curl -X POST https://adas-api.aiotlab.edu.vn:52000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "admin123"}'
   ```

3. **Proceed to Phase 2:** Async Job Processing

## Maintenance

### Backup Database

```sql
BACKUP DATABASE adas_production
TO DISK = 'C:\Backups\adas_production.bak'
WITH FORMAT;
```

### Restore Database

```sql
RESTORE DATABASE adas_production
FROM DISK = 'C:\Backups\adas_production.bak'
WITH REPLACE;
```

### View Migration History

```bash
alembic history
alembic current
```

### Rollback Migration

```bash
alembic downgrade -1  # Go back one migration
alembic downgrade base  # Rollback everything
```

## Support

For issues, check:
1. SQL Server error logs: `C:\Program Files\Microsoft SQL Server\MSSQL15.MSSQLSERVER\MSSQL\Log\ERRORLOG`
2. Application logs: `backend/app/storage/logs/`
3. Alembic output for migration errors

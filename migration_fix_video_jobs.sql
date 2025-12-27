-- ================================================
-- MIGRATION: Add missing columns to video_jobs table
-- Date: 2025-12-27
-- Purpose: Fix schema mismatch between model and database
-- ================================================

USE adas_production;
GO

-- Add job_id column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'job_id')
BEGIN
    ALTER TABLE video_jobs ADD job_id NVARCHAR(36) NULL;
    PRINT 'Added column: job_id';
END
ELSE
BEGIN
    PRINT 'Column job_id already exists';
END
GO

-- Add trip_id column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'trip_id')
BEGIN
    ALTER TABLE video_jobs ADD trip_id INT NULL;
    PRINT 'Added column: trip_id';
    
    -- Add foreign key constraint
    IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_video_jobs_trip_id')
    BEGIN
        ALTER TABLE video_jobs 
        ADD CONSTRAINT FK_video_jobs_trip_id 
        FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE SET NULL;
        PRINT 'Added foreign key constraint: FK_video_jobs_trip_id';
    END
END
ELSE
BEGIN
    PRINT 'Column trip_id already exists';
END
GO

-- Add video_filename column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'video_filename')
BEGIN
    ALTER TABLE video_jobs ADD video_filename NVARCHAR(255) NULL;
    PRINT 'Added column: video_filename';
END
ELSE
BEGIN
    PRINT 'Column video_filename already exists';
END
GO

-- Add video_path column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'video_path')
BEGIN
    ALTER TABLE video_jobs ADD video_path NVARCHAR(500) NULL;
    PRINT 'Added column: video_path';
END
ELSE
BEGIN
    PRINT 'Column video_path already exists';
END
GO

-- Add video_size_mb column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'video_size_mb')
BEGIN
    ALTER TABLE video_jobs ADD video_size_mb FLOAT NULL;
    PRINT 'Added column: video_size_mb';
END
GO

-- Add duration_seconds column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'duration_seconds')
BEGIN
    ALTER TABLE video_jobs ADD duration_seconds INT NULL;
    PRINT 'Added column: duration_seconds';
END
GO

-- Add fps column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'fps')
BEGIN
    ALTER TABLE video_jobs ADD fps FLOAT NULL;
    PRINT 'Added column: fps';
END
GO

-- Add resolution column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'resolution')
BEGIN
    ALTER TABLE video_jobs ADD resolution NVARCHAR(50) NULL;
    PRINT 'Added column: resolution';
END
GO

-- Add status column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'status')
BEGIN
    ALTER TABLE video_jobs ADD status NVARCHAR(20) NOT NULL DEFAULT 'pending';
    PRINT 'Added column: status';
END
GO

-- Add progress_percent column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'progress_percent')
BEGIN
    ALTER TABLE video_jobs ADD progress_percent INT NOT NULL DEFAULT 0;
    PRINT 'Added column: progress_percent';
END
GO

-- Add result_path column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'result_path')
BEGIN
    ALTER TABLE video_jobs ADD result_path NVARCHAR(500) NULL;
    PRINT 'Added column: result_path';
END
GO

-- Add error_message column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'error_message')
BEGIN
    ALTER TABLE video_jobs ADD error_message NVARCHAR(MAX) NULL;
    PRINT 'Added column: error_message';
END
GO

-- Add started_at column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'started_at')
BEGIN
    ALTER TABLE video_jobs ADD started_at DATETIME NULL;
    PRINT 'Added column: started_at';
END
GO

-- Add completed_at column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'completed_at')
BEGIN
    ALTER TABLE video_jobs ADD completed_at DATETIME NULL;
    PRINT 'Added column: completed_at';
END
GO

-- Add processing_time_seconds column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'processing_time_seconds')
BEGIN
    ALTER TABLE video_jobs ADD processing_time_seconds INT NULL;
    PRINT 'Added column: processing_time_seconds';
END
GO

-- Add created_at column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'created_at')
BEGIN
    ALTER TABLE video_jobs ADD created_at DATETIME NOT NULL DEFAULT GETDATE();
    PRINT 'Added column: created_at';
END
GO

-- Add updated_at column if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('video_jobs') AND name = 'updated_at')
BEGIN
    ALTER TABLE video_jobs ADD updated_at DATETIME NOT NULL DEFAULT GETDATE();
    PRINT 'Added column: updated_at';
END
GO

-- Create unique index on job_id if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'UQ_video_jobs_job_id' AND object_id = OBJECT_ID('video_jobs'))
BEGIN
    CREATE UNIQUE INDEX UQ_video_jobs_job_id ON video_jobs(job_id) WHERE job_id IS NOT NULL;
    PRINT 'Created unique index on job_id';
END
GO

PRINT '==============================================';
PRINT 'Migration completed successfully!';
PRINT 'video_jobs table structure updated';
PRINT '==============================================';
GO

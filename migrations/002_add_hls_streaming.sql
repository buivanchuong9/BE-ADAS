-- ================================================
-- MIGRATION 002: HLS Streaming Support
-- ================================================
-- Author: Principal AI Architect
-- Date: 2026-02-08
-- Purpose: Add HLS streaming fields for progressive video playback

-- Add HLS fields to job_queue
ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS hls_playlist_path VARCHAR(500);
ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS hls_ready BOOLEAN DEFAULT FALSE;
ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS segments_generated INT DEFAULT 0;
ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS total_segments INT DEFAULT 0;

-- Add video_path and video_filename if missing (for compatibility)
ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS video_path VARCHAR(500);
ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS video_filename VARCHAR(255);

-- Create index for HLS polling queries
CREATE INDEX IF NOT EXISTS idx_jobs_hls_ready 
    ON job_queue(hls_ready, job_id) 
    WHERE status IN ('processing', 'completed');

-- Add comments
COMMENT ON COLUMN job_queue.hls_playlist_path IS 'Path to HLS playlist.m3u8 file';
COMMENT ON COLUMN job_queue.hls_ready IS 'True when first segment is ready for playback';
COMMENT ON COLUMN job_queue.segments_generated IS 'Number of HLS segments generated so far';
COMMENT ON COLUMN job_queue.total_segments IS 'Total expected segments (estimated from video duration)';

-- Verify migration
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'job_queue' 
  AND column_name IN ('hls_playlist_path', 'hls_ready', 'segments_generated', 'total_segments');

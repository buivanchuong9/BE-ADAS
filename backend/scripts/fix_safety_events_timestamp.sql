-- FIX: Add missing 'timestamp' column to safety_events table

-- 1. Check if column exists, if not add it
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'safety_events'
        AND column_name = 'timestamp'
    ) THEN
        ALTER TABLE safety_events ADD COLUMN timestamp TIMESTAMP WITHOUT TIME ZONE;
        CREATE INDEX ix_safety_events_timestamp ON safety_events (timestamp);
        RAISE NOTICE 'Added timestamp column to safety_events table';
    ELSE
        RAISE NOTICE 'Column timestamp already exists in safety_events table';
    END IF;
END
$$;

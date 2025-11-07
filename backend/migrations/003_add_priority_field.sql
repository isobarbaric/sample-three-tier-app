-- Migration 003: Add priority field to todos
-- Allow users to set priority levels for their todos

ALTER TABLE todos ADD COLUMN priority INTEGER DEFAULT 0;

-- Create index on priority for sorting
CREATE INDEX IF NOT EXISTS idx_todos_priority ON todos(priority DESC);


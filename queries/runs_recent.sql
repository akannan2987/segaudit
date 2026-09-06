-- The last ten commands that wrote tables.
-- Needs: runs
SELECT started_at, run_id, track, command, seed, segaudit_version, config_file
FROM runs
ORDER BY started_at DESC
LIMIT 10

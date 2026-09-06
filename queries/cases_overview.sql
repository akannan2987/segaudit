-- What did the inventory find?
-- One row per data source: cases, how many have labels, QA failures, spacing range.
-- Needs: cases
SELECT
    source,
    COUNT(*)                                        AS cases,
    CAST(SUM(CASE WHEN label_path <> '' THEN 1 ELSE 0 END) AS INTEGER) AS with_labels,
    CAST(SUM(CASE WHEN qa_errors > 0 THEN 1 ELSE 0 END) AS INTEGER) AS qa_failed,
    ROUND(MIN(spacing_x_mm), 3)                     AS min_spacing_mm,
    ROUND(MAX(spacing_x_mm), 3)                     AS max_spacing_mm,
    MIN(orientation)                                AS orientation_min,
    MAX(orientation)                                AS orientation_max
FROM cases
GROUP BY source
ORDER BY source

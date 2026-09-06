-- Which cases failed input QA, and why?
-- Needs: qa_issues, cases
SELECT
    q.case_id,
    q.check,
    q.severity,
    q.message,
    c.orientation,
    ROUND(c.spacing_x_mm, 3) AS spacing_x_mm
FROM qa_issues q
JOIN cases c USING (case_id)
WHERE q.severity = 'error'
ORDER BY q.case_id, q.check

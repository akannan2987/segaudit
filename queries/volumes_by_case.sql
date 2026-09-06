-- Hippocampal volumes per case, in millilitres, largest total first.
-- Needs: cases  (volumes are NaN for cases without labels)
SELECT
    case_id,
    ROUND(volume_label1_ml, 3)                         AS anterior_ml,
    ROUND(volume_label2_ml, 3)                         AS posterior_ml,
    ROUND(volume_label1_ml + volume_label2_ml, 3)      AS total_ml,
    qa_errors
FROM cases
WHERE label_path <> ''
ORDER BY total_ml DESC

DECLARE is_full_refresh BOOL DEFAULT FALSE;
BEGIN
    CREATE TEMP TABLE t1 AS
    SELECT id, name FROM project.dataset.src;
    IF is_full_refresh THEN
        INSERT INTO project.dataset.tgt SELECT * FROM t1;
    END IF;
EXCEPTION WHEN ERROR THEN
    RAISE USING MESSAGE = FORMAT(@@error.message);
END;

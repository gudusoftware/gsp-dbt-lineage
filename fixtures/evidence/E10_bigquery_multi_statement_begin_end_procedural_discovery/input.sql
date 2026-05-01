BEGIN
    CREATE TEMP TABLE t1 AS SELECT * FROM project.ds.src;
    INSERT INTO project.ds.tgt SELECT * FROM t1;
END;

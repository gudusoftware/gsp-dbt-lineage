CREATE PROCEDURE schName.s
AS
BEGIN
    SELECT columnName INTO #temp FROM schName.sourceTable;
    INSERT INTO schName.targetTable (columnName) SELECT columnName FROM #temp;
END

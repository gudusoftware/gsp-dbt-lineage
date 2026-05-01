SELECT
    Id,
    CASE
        WHEN Id > 10 THEN 'IS_GREATER_THAN_TEN'
        WHEN Id > 5 THEN 'IS_GREATER_THAN_FIVE'
        ELSE 'IS_SMALL'
    END AS foo,
    bar
FROM mySchema.myTable

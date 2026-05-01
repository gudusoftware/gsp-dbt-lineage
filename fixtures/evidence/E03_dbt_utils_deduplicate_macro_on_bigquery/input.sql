SELECT u.*
FROM (
    SELECT ARRAY_AGG(original ORDER BY article_name DESC LIMIT 1)[OFFSET(0)] AS u
    FROM all_articles AS original
    GROUP BY id
)

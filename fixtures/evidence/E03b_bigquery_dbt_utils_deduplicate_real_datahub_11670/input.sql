select unique.*
from (
     select
         array_agg (
                 original
                     order by article_name desc
            limit 1
         )[offset(0)] unique
     from all_articles original
     group by id
)

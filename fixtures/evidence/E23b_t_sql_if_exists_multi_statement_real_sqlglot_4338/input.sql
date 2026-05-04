IF  EXISTS (SELECT * FROM sys.views WHERE object_id = OBJECT_ID(N'[DBAPP].[YEARLY_TARGETS_ModelView]'))
DROP VIEW [DBAPP].[YEARLY_TARGETS_ModelView]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
-- This view aggregates yearly targets by division.
-- It includes target values and their attainment percentages for different years.
CREATE VIEW [DBAPP].[WFA_YEARLY_TARGETS_ModelView]
AS Select
DISTINCT case when T.WFA_Target_Division = 'NA Corporate Total' then 0 else D.[Prod_Hier:_Division_code] end as [Prod_Hier:_Division_code_FDR] ,
 T.[Target_Division]
      ,[Target_Division_Sort]
      ,[Target_0_Percent]
      ,[Target_50_Percent]
      ,[Target_100_Percent]
      ,[Target_100_Attainment_Percent]
      ,[Target_150_Percent]
      ,[Year]
 from db.YEARLY_TARGETS_FriendlyNames T
LEFT JOIN  db.YEARLY_TARGETS_DIVISION_FriendlyNames D
ON D.Target_Division=T.Target_Division;
GO

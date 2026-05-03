Create database dbName
go
use dbName
go
create schema schName
go
Create table schName.sourceTable
(
columnName int
)
go
Create table schName.targetTable
(
columnName int
)
go
insert into schName.sourceTable
(columnName)
Values (1),(2),(3)
go
create procedure schName.procName
as
BEGIN
drop table if exists #tempTable
create table #tempTable (columnName int)
insert into #tempTable (columnName)
Select columnName from schName.sourceTable
insert into schName.targetTable (columnName)
select columnName from #tempTable
END
go
execute schName.procName
execute schName.procName
execute schName.procName
execute schName.procName
execute schName.procName
execute schName.procName
execute schName.procName
execute schName.procName
execute schName.procName
execute schName.procName
execute schName.procName
execute schName.procName
execute schName.procName

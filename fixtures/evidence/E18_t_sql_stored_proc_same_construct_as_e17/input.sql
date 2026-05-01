create PROCEDURE myproc
AS
BEGIN
    insert into test2 select * from test1
END
GO

-- range function to support Date, DateTime, Date32 and DateTime64:
select range(toDate('2000-01-01'), toDate('2000-01-05'))
select range(toDate32('2000-01-01'), toDate32('2000-01-05'))
select range(toDateTime('2020-01-01 00:00:01'), toDateTime('2020-04-01 00:00:01'))
select range(toDateTime('2020-01-01 00:00:01'), toDateTime('2020-04-01 00:00:01'), interval 1 month)
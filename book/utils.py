from datetime import date, timedelta


def resolve_period(period:str):
    today = date.today()
    if period == 'this_month':
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year+1, month=1, day=1) - timedelta(days=1)
        else:
            end = start.replace(month=start.month+1, day=1) - timedelta(days=1)
        return start, end
    if period == 'last_month':
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        start = end.replace(day=1)
        return start, end
    if period == 'this_year':
        start = date(today.year,1,1)
        end = date(today.year,12,31)
        return start, end
    return None, None
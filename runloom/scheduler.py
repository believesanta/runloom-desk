"""Local-time schedules; missed slots are skipped, never replayed in a burst."""
from datetime import datetime, timedelta
import math
import re


def next_run(schedule, now):
    try: valid_now = type(now) in (int,float) and math.isfinite(now)
    except OverflowError: valid_now = False
    if not valid_now:
        raise ValueError('Current time must be a finite timestamp')
    if schedule is not None and not isinstance(schedule,dict):
        raise ValueError('Schedule must be an object')
    if schedule and 'enabled' in schedule and not isinstance(schedule['enabled'],bool):
        raise ValueError('Schedule enabled must be boolean')
    if not schedule or schedule.get('enabled') is False:
        return None
    kind = schedule.get('kind')
    if kind == 'interval':
        if isinstance(schedule.get('seconds'),bool): raise ValueError('Interval needs a numeric number of seconds')
        try: seconds = float(schedule['seconds'])
        except (KeyError,TypeError,ValueError,OverflowError): raise ValueError('Interval needs seconds') from None
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('Interval must be positive')
        result = now + seconds
        if not math.isfinite(result): raise ValueError('Interval produces an invalid timestamp')
        return result
    if kind == 'once':
        if isinstance(schedule.get('at'),bool): raise ValueError('One-time schedule needs a numeric timestamp')
        try: at = float(schedule['at'])
        except (KeyError,TypeError,ValueError,OverflowError): raise ValueError('One-time schedule needs a timestamp') from None
        if not math.isfinite(at): raise ValueError('Invalid timestamp')
        return at if at > now else None
    if kind == 'daily':
        value = schedule.get('time','')
        if not isinstance(value,str) or not re.fullmatch(r'\d{2}:\d{2}',value):
            raise ValueError('Daily time must be HH:MM')
        hour, minute = map(int,value.split(':'))
        if hour > 23 or minute > 59: raise ValueError('Invalid daily time')
        try:
            local = datetime.fromtimestamp(now)
            target = local.replace(hour=hour,minute=minute,second=0,microsecond=0)
            if target.timestamp() <= now: target += timedelta(days=1)
            return target.timestamp()
        except (ValueError,OverflowError,OSError):
            raise ValueError('Daily schedule timestamp is outside the supported range') from None
    raise ValueError('Unknown schedule kind')

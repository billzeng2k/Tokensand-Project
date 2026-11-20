"""Bounded, timezone-aware display expansion of Airbyte recurrence records."""
from datetime import datetime, timedelta, timezone
from itertools import islice
import re
from zoneinfo import ZoneInfo
from dateutil.rrule import rrulestr

HORIZON_DAYS = 365
MAX_OCCURRENCES = 1500


def stamp(value):
    if value.get('date'):
        return datetime.fromisoformat(value['date'])
    result = datetime.fromisoformat(value['dateTime'].replace('Z', '+00:00'))
    if value.get('timeZone'):
        zone = ZoneInfo(value['timeZone'])
        result = result.astimezone(zone) if result.tzinfo else result.replace(tzinfo=zone)
    return result


def occurrence_key(value):
    if value.get('date'):
        return value['date']
    result = stamp(value)
    return result.astimezone(timezone.utc).isoformat() if result.tzinfo else result.isoformat()


def event_kind(record):
    if record.get('eventType') == 'birthday':
        return 'birthday', 'Google birthday event'
    title = str(record.get('summary', ''))
    if re.search(r'\b(birthday|bday|b-day)\b', title, re.I):
        return 'birthday', 'Suggested from event title'
    if re.search(r'\b(christmas|thanksgiving|halloween|hanukkah|diwali|eid|easter|new year|holiday|kwanzaa|lunar new year|passover)\b', title, re.I):
        return 'holiday', 'Suggested from event title'
    return 'event', 'Calendar event'


def expand(records, today):
    """Preserve exceptions/cancellations; never synthesize outside the bounded view."""
    stop = today + timedelta(days=HORIZON_DAYS)
    result, warnings = [], []
    overrides = {}
    deleted_series={(r.get('calendar_id'),r.get('id')) for r in records if r.get('status')=='cancelled'}
    for record in records:
        if record.get('recurringEventId') and record.get('originalStartTime'):
            try:
                key = (record['calendar_id'], record['recurringEventId'], occurrence_key(record['originalStartTime']))
                overrides[key] = record
            except (ValueError, KeyError):
                warnings.append('Some recurrence exceptions could not be read.')
    for record in records:
        if record.get('recurringEventId') and (record.get('calendar_id'),record['recurringEventId']) in deleted_series:
            continue
        if not record.get('recurrence'):
            result.append(record)
            continue
        if record.get('status') == 'cancelled':
            continue
        try:
            lines = record['recurrence']
            if not isinstance(lines, list) or len(lines) > 100 or sum(len(s) for s in lines) > 16000:
                raise ValueError('Recurrence too large')
            text = '\n'.join(lines)
            # Sub-daily schedules are not shopping occasions and can expand unboundedly.
            if re.search(r'FREQ=(SECONDLY|MINUTELY|HOURLY)|BY(SECOND|MINUTE|HOUR)=', text, re.I):
                raise ValueError('Sub-daily recurrence unsupported')
            start = stamp(record['start'])
            end = stamp(record.get('end') or record['start'])
            duration = end-start
            if not record.get('end') and 'date' in record['start']:
                duration=timedelta(days=1)
            if duration < timedelta(0) or duration > timedelta(days=366):
                raise ValueError('Invalid event duration')
            rule = rrulestr(text, dtstart=start, forceset=True, tzids=ZoneInfo)
            count = 0
            index = -1
            for index, occurrence in enumerate(islice(rule, 100000)):
                if occurrence.date() > stop:
                    break
                if (occurrence+duration).date() < today:
                    continue
                all_day = 'date' in record['start']
                instance_start = {'date': occurrence.date().isoformat()} if all_day else {'dateTime': occurrence.isoformat(), **({'timeZone':record['start']['timeZone']} if record['start'].get('timeZone') else {})}
                key = (record['calendar_id'],record['id'],occurrence_key(instance_start))
                if key in overrides:
                    continue # Exception record is handled separately, even if moved outside this window.
                instance_end = {'date': (occurrence+duration).date().isoformat()} if all_day else {'dateTime': (occurrence+duration).isoformat()}
                result.append({**record, 'recurrence':None, 'recurringEventId':record['id'], 'originalStartTime':instance_start,
                               'start':instance_start, 'end':instance_end, 'expanded_occurrence':True})
                count += 1
                if count >= MAX_OCCURRENCES:
                    warnings.append('A repeating calendar series was truncated for this view.')
                    break
            else:
                if index == 99999:
                    warnings.append('A long-running recurrence could not be fully expanded.')
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            warnings.append('Some repeating events could not be expanded. Check Google Calendar for their dates.')
    return result, sorted(set(warnings))

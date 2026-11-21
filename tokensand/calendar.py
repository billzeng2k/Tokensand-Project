"""Airbyte Docker source -> atomic private snapshot. Google Calendar is read-only."""
import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from .config import LOCAL
from . import tenancy, auth
from .calendar_events import expand, occurrence_key, event_kind, HORIZON_DAYS

IMAGE = 'airbyte/source-google-calendar:1.1.0'
CONFIG = LOCAL / 'airbyte-calendar.json'
SNAPSHOT = LOCAL / 'calendar-events.json'
SYNC_LOCK = threading.Lock()


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def connector(command, files):
    with tempfile.TemporaryDirectory(dir=LOCAL) as directory:
        folder = Path(directory)
        args = ['docker', 'run', '--rm', '--platform', 'linux/amd64', '--user', '0:0',
                '-v', f'{folder}:/config:ro', IMAGE, command]
        for name, value in files.items():
            private_json(folder / f'{name}.json', value)
            args.extend([f'--{name}', f'/config/{name}.json'])
        # Never relay connector logs: upstream errors can contain credentials or event data.
        result = subprocess.run(args, capture_output=True, text=True, timeout=300)
        messages = []
        for line in result.stdout.splitlines():
            try: message = json.loads(line)
            except ValueError: continue
            if isinstance(message, dict): messages.append(message)
        if result.returncode or any(
            m.get('trace', {}).get('type') == 'ERROR' or
            m.get('log', {}).get('level') in ('ERROR', 'FATAL') or
            m.get('trace', {}).get('stream_status', {}).get('status') == 'INCOMPLETE'
            for m in messages
        ):
            raise RuntimeError('Calendar connector failed. Check Docker and reconnect Google; previous snapshot was preserved.')
        return messages


def snapshot_path():
    return tenancy.directory() / 'calendar-events.json' if tenancy.USER.get() else SNAPSHOT

def connected():
    return auth.connected(tenancy.USER.get()) if tenancy.USER.get() else CONFIG.exists()

def sync():
    with SYNC_LOCK:
        if not connected():
            raise RuntimeError('Connect Google first: run npm run calendar:connect. See docs/AIRBYTE.md.')
        config = auth.calendar_config(tenancy.USER.get()) if tenancy.USER.get() else json.loads(CONFIG.read_text())
        if not config.get('calendarid'): raise ValueError('Choose one calendarid; syncing all calendars is disabled.')
        discovered = connector('discover', {'config': config})
        streams = [s for m in discovered for s in m.get('catalog', {}).get('streams', []) if s['name'] == 'events']
        if len(streams) != 1: raise RuntimeError('Airbyte events stream not found.')
        catalog = {'streams': [{'stream': streams[0], 'sync_mode': 'full_refresh', 'destination_sync_mode': 'overwrite'}]}
        messages = connector('read', {'config': config, 'catalog': catalog})
        # Require an explicit successful stream completion, including for empty calendars.
        if not any(m.get('trace', {}).get('stream_status', {}).get('status') == 'COMPLETE' for m in messages):
            raise RuntimeError('Airbyte did not confirm a complete sync; previous snapshot was preserved.')
        records = {}
        for m in messages:
            record = m.get('record', {})
            if record.get('stream') != 'events': continue
            r = record['data']
            if not r.get('calendar_id') or not r.get('id'): raise RuntimeError('Missing calendar identity.')
            key = (r['calendar_id'], r['id'])
            if key not in records or r.get('updated', '') >= records[key].get('updated', ''): records[key] = r
        snapshot = {'synced_at': datetime.now(timezone.utc).isoformat(), 'connector': IMAGE, 'records': list(records.values())}
        private_json(snapshot_path(), snapshot)
        return view(snapshot)


def normalize(r, synced_at):
    start = r.get('start') or {}
    day = start.get('date') or (start.get('dateTime') or '')[:10]
    if not day or r.get('recurrence') or r.get('status') == 'cancelled': return None
    date.fromisoformat(day)
    identity_parts = [r['calendar_id'], r.get('recurringEventId') or r['id']]
    if r.get('recurringEventId') and r.get('originalStartTime'):
        identity_parts.append(occurrence_key(r['originalStartTime']))
    identity = json.dumps(identity_parts, separators=(',', ':'))
    kind, kind_source = event_kind(r)
    return {'id': hashlib.sha256(identity.encode()).hexdigest(), 'title': r.get('summary', '(Untitled event)'),
            'description': (r.get('description') or '')[:6000],
            'date': day, 'status': r.get('status', 'confirmed'), 'need': 'jacket',
            'source': 'airbyte-google-calendar', 'calendar_id': r['calendar_id'], 'google_event_id': r['id'],
            'updated': r.get('updated'), 'start': start, 'end': r.get('end'), 'synced_at': synced_at,
            'kind':kind, 'kind_source':kind_source, 'all_day':'date' in start,
            'recurring':bool(r.get('recurringEventId')), 'recurring_series_id':r.get('recurringEventId'),
            'recurrence_source':'expanded locally from Google rule' if r.get('expanded_occurrence') else None,
            'shopping_context': 'User-selected jacket demo; category is not inferred from calendar text.'}


def view(snapshot=None, today=None):
    if snapshot is None:
        snapshot = json.loads(snapshot_path().read_text()) if snapshot_path().exists() else {'records': [], 'synced_at': None}
    today = today or date.today()
    events = []
    records, warnings = expand(snapshot['records'], today)
    for r in records:
        e = normalize(r, snapshot['synced_at'])
        if e:
            end = (r.get('end') or {}).get('date') or ((r.get('end') or {}).get('dateTime') or '')[:10] or e['date']
            last_day = date.fromisoformat(end) - (timedelta(days=1) if (r.get('end') or {}).get('date') else timedelta())
            if last_day >= today and date.fromisoformat(e['date']) <= today + timedelta(days=HORIZON_DAYS):events.append(e)
    return {'connected': connected(), 'synced_at': snapshot['synced_at'], 'events': sorted(events, key=lambda e: (e['date'], e['id'])),
            'window_start':today.isoformat(), 'window_end':(today+timedelta(days=HORIZON_DAYS)).isoformat(), 'warnings':warnings,
            'note': 'Primary calendar only · next 365 days. Separate Google Birthdays and Holidays calendars are not connected. Event dates retain their source timezone; repeating events are expanded locally.'}


def selected_event(event_id):
    # Refresh before using calendar evidence. A missing/cancelled event cannot create a task.
    data = sync()
    return next((e for e in data['events'] if e['id'] == event_id),
                {'id': event_id, 'status': 'cancelled', 'source': 'airbyte-google-calendar', 'synced_at': data['synced_at']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=['sync', 'status']); args = parser.parse_args()
    try:
        result = sync() if args.command == 'sync' else view()
        print(json.dumps({'connected': result['connected'], 'synced_at': result['synced_at'], 'upcoming_events': len(result['events'])}))
    except Exception:
        raise SystemExit('Calendar unavailable. See docs/AIRBYTE.md; no credentials or calendar contents were printed.')

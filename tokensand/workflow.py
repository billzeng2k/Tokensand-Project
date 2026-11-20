"""Deterministic integration workflow; no purchase or payment operations."""
import argparse
import asyncio
from datetime import datetime, timezone, date
import hashlib
import json
import subprocess
import uuid
from .config import ROOT, LOCAL
from .storage import Store, MemoryStore
from .tools import FixtureTools, FiredrillTools, SCENARIOS


def reject(product, profile, event, memory):
    reasons = []
    if product['id'] in profile['owned_ids']: reasons.append('already_owned')
    if not product['in_stock']: reasons.append('out_of_stock')
    if profile['size'] not in product['sizes']: reasons.append('size_unavailable')
    # Conservative explicit preference rule for the synthetic demo persona.
    if product['material'] == 'wool' and 'itchy' in memory.lower(): reasons.append('remembered_wool_rejection')
    if product['price_cents'] > profile['budget_cents']: reasons.append('over_item_budget')
    delivery = product.get('delivery_date')
    if not delivery: reasons.append('delivery_unverified')
    elif date.fromisoformat(delivery) > date.fromisoformat(event['date']): reasons.append('arrives_after_event')
    return reasons


def run(tools, store, memory, profile, event_id='holiday-dinner-demo'):
    report = {'run_id': str(uuid.uuid4()), 'started_at': datetime.now(timezone.utc).isoformat(), 'mode': tools.mode, 'memory_evidence': memory, 'profile': profile, 'steps': [], 'status': 'started', 'task': None}
    def call(service, operation, arguments, key=None):
        step = {'operation': operation, 'arguments': arguments, 'idempotency_key': key}
        report['steps'].append(step)
        try:
            value = tools.invoke(service, operation, arguments, key)
            step['result'] = value
            return value
        except Exception as exc:
            step['error'] = type(exc).__name__
            raise
    try:
        event = call('calendar', 'events.get', {'event_id': event_id})
        if event['status'] == 'cancelled':
            report['status'] = 'event_cancelled'
        else:
            identity = f"{profile['user_id']}:{event['id']}:{event['need']}"
            if event.get('updated'): identity += f":{event['updated']}"
            task_key = hashlib.sha256(identity.encode()).hexdigest()
            existing = call('shopping', 'tasks.get', {'task_key': task_key})
            if existing:
                report.update(status='already_saved', task=existing)
            else:
                products = call('shopping', 'products.search', {'category': event['need']})
                decisions = [{'product': p, 'reasons': reject(p, profile, event, memory)} for p in products]
                report['decisions'] = decisions
                eligible = sorted([d['product'] for d in decisions if not d['reasons']], key=lambda p: (p['price_cents'], p['id']))
                report['status'] = 'no_eligible_product'
                for product in eligible:
                    fresh = call('shopping', 'products.get', {'product_id': product['id']})
                    reasons = reject(fresh, profile, event, memory)
                    report['steps'].append({'operation': 'revalidate', 'product_id': fresh['id'], 'reasons': reasons})
                    if reasons: continue
                    task = {'task_key': task_key, 'event_id': event['id'], 'user_id': profile['user_id'], 'product': fresh, 'state': 'needs_user_review', 'deadline': event['date'], 'price_scope': 'item only; tax and shipping unverified', 'order_placed': False}
                    try:
                        saved = call('shopping', 'tasks.create', task, task_key)
                    except Exception:
                        # Unknown write result: inspect state, never blindly repeat the write.
                        saved = call('shopping', 'tasks.get', {'task_key': task_key})
                        if not saved:
                            report['status'] = 'action_unconfirmed'
                            break
                    # Read after write before claiming success.
                    confirmed = call('shopping', 'tasks.get', {'task_key': task_key})
                    if not confirmed or confirmed.get('task_key') != task_key:
                        report['status'] = 'action_unconfirmed'
                    else:
                        report.update(status='task_saved', task=confirmed)
                    break
    except Exception as exc:
        report.update(status='tool_error', error=type(exc).__name__)
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    store.save_audit(report)
    return report


def telemetry(report):
    node = ROOT / 'node_modules/node/bin/node'
    if not node.exists(): raise RuntimeError('Run npm ci first')
    result = subprocess.run([str(node), 'scripts/telemetry.mjs'], cwd=ROOT, input=json.dumps({'event_type': 'Shopping Workflow Completed', 'user_id': 'demo-user', 'event_properties': {'status': report['status'], 'mode': report['mode'], 'run_id': report['run_id']}}), text=True, capture_output=True, timeout=30)
    if result.returncode: raise RuntimeError(result.stderr[-500:])
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', choices=SCENARIOS, default='happy')
    parser.add_argument('--memory', choices=['cognee', 'fixture'], default='cognee')
    parser.add_argument('--storage', choices=['singlestore', 'memory'], default='singlestore')
    parser.add_argument('--tools', choices=['fixture', 'firedrill'], default='fixture')
    args = parser.parse_args()
    fixture = json.loads((ROOT / 'fixtures/shopping.json').read_text())
    if args.memory == 'cognee':
        from .memory import recall
        memory = asyncio.run(recall())
    else: memory = fixture['memory']
    store = Store() if args.storage == 'singlestore' else MemoryStore()
    try:
        tools = FixtureTools(args.scenario, store) if args.tools == 'fixture' else FiredrillTools()
        report = run(tools, store, memory, fixture['profile'])
        report['memory_backend'] = args.memory
        report['storage_backend'] = args.storage
        report['telemetry'] = telemetry(report)
        path = LOCAL / f"run-{report['run_id']}.json"
        path.write_text(json.dumps(report, indent=2))
        print(json.dumps({'status': report['status'], 'report': str(path), 'task': report['task'], 'telemetry': report['telemetry']}, indent=2))
    finally: store.close()

if __name__ == '__main__': main()

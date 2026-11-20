import json
import os
import re
from . import config
import pymysql

class Store:
    def __init__(self):
        database = os.getenv('SINGLESTORE_DATABASE', 'tokensand')
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*', database):
            raise ValueError('Invalid database name')
        self.conn = pymysql.connect(host=os.getenv('SINGLESTORE_HOST', '127.0.0.1'), port=int(os.getenv('SINGLESTORE_PORT', '3307')), user='root', password=os.environ['SINGLESTORE_ROOT_PASSWORD'], autocommit=True, connect_timeout=10)
        with self.conn.cursor() as c:
            c.execute(f'CREATE DATABASE IF NOT EXISTS `{database}`')
            c.execute(f'USE `{database}`')
            c.execute('CREATE ROWSTORE TABLE IF NOT EXISTS shopping_tasks (task_key VARCHAR(64) PRIMARY KEY, payload LONGTEXT NOT NULL)')
            c.execute('CREATE ROWSTORE TABLE IF NOT EXISTS audit_runs (run_id VARCHAR(64) PRIMARY KEY, payload LONGTEXT NOT NULL)')
    def save_task(self, key, task):
        with self.conn.cursor() as c:
            c.execute('INSERT IGNORE INTO shopping_tasks VALUES (%s,%s)', (key, json.dumps(task)))
        return self.get_task(key)
    def get_task(self, key):
        with self.conn.cursor() as c:
            c.execute('SELECT payload FROM shopping_tasks WHERE task_key=%s', (key,))
            row = c.fetchone()
        return json.loads(row[0]) if row else None
    def save_audit(self, report):
        with self.conn.cursor() as c:
            c.execute('INSERT INTO audit_runs VALUES (%s,%s)', (report['run_id'], json.dumps(report)))
    def close(self):
        self.conn.close()

class MemoryStore:
    """Explicit process-only store for isolated policy tests and Firedrill drills."""
    def __init__(self):
        self.tasks = {}
        self.audits = []
    def save_task(self, key, task):
        return self.tasks.setdefault(key, task)
    def get_task(self, key):
        return self.tasks.get(key)
    def save_audit(self, report):
        self.audits.append(report)
    def close(self):
        pass

if __name__ == '__main__':
    store = Store()
    with store.conn.cursor() as c:
        c.execute('SELECT VERSION()')
        print('SingleStore connected:', c.fetchone()[0])
        c.execute('SELECT COUNT(*) FROM shopping_tasks')
        print('Saved tasks:', c.fetchone()[0])
    store.close()

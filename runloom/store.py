"""Serialized SQLite access shared by the desktop and process workers."""
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path),check_same_thread=False,timeout=15)
        self._db.execute('PRAGMA journal_mode=WAL')
        self._db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self._db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL)')
        self._db.commit()
        # This app uses a single instance. Unfinished rows mean a previous exit.
        for run in self.list_runs():
            if run.get('status') in ('queued','running'):
                self.update_run(run['id'],status='interrupted',finished_at=time.time(),error='Application exited before the run finished.')

    def list_tasks(self):
        with self._lock:
            return [json.loads(row[0]) for row in self._db.execute('SELECT data FROM tasks ORDER BY id')]

    def save_task(self, task):
        from .manifest import validate_manifest
        task = validate_manifest(task)
        for parameter in task['parameters']:
            if parameter.get('secret'):
                parameter.pop('default',None)
                for values in (task.get('values'),task.get('last_values'),task.get('schedule',{}).get('values')):
                    if isinstance(values,dict): values.pop(parameter['id'],None)
        with self._lock, self._db:
            self._db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?)',(task['id'],json.dumps(task,ensure_ascii=False)))

    def delete_task(self, task_id):
        with self._lock, self._db:
            self._db.execute('DELETE FROM tasks WHERE id=?',(task_id,))

    def list_runs(self):
        with self._lock:
            return [json.loads(row[0]) for row in self._db.execute('SELECT data FROM runs ORDER BY created DESC')]

    def get_run(self, run_id):
        with self._lock:
            row = self._db.execute('SELECT data FROM runs WHERE id=?',(run_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def create_run(self, record):
        record = dict(record)
        record.setdefault('id',uuid.uuid4().hex)
        record.setdefault('created_at',time.time())
        with self._lock, self._db:
            self._db.execute('INSERT INTO runs VALUES (?,?,?)',(record['id'],record['created_at'],json.dumps(record,ensure_ascii=False)))
        return record['id']

    def update_run(self, run_id, **changes):
        with self._lock, self._db:
            record = self.get_run(run_id)
            if record is None: raise KeyError(run_id)
            record.update(changes)
            self._db.execute('UPDATE runs SET data=? WHERE id=?',(json.dumps(record,ensure_ascii=False),run_id))
            return record

    def close(self):
        with self._lock:
            self._db.close()

"""Desktop regressions using real Tk widgets, SQLite and subprocess runs."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from runloom.app import App
from runloom.instance import WorkspaceLock

ROOT = Path(__file__).resolve().parents[1]


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class UIRegressions(unittest.TestCase):
    def setUp(self):
        work = ROOT / 'work'
        work.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = App(self.root, self.temp.name)
        self.a = self.task('a-review', 'Review A')
        self.b = self.task('b-review', 'Review B')
        self.app.store.save_task(self.a)
        self.app.store.save_task(self.b)
        self.select(self.a['id'])

    def tearDown(self):
        self.app.runner.shutdown()
        for callback in self.root.tk.call('after', 'info'):
            self.root.after_cancel(callback)
        self.app.close()
        self.temp.cleanup()

    def task(self, task_id, name):
        return {'schema_version': 1, 'id': task_id, 'name': name,
                'executable': '{python}', 'args': ['-c', 'import sys; print(sys.argv[1])', '{message}'],
                'cwd': str(ROOT), 'parameters': [{'id': 'message', 'type': 'string', 'default': name}],
                'timeout': 10, 'allow_parallel': False, 'preview': False}

    def select(self, task_id):
        self.app.show_library()
        index = next(i for i, task in enumerate(self.app.tasks) if task['id'] == task_id)
        self.app.library.selection_clear(0, 'end')
        self.app.library.selection_set(index)
        self.app.select_library()

    def dialog(self, title):
        return next(w for w in self.root.winfo_children()
                    if isinstance(w, tk.Toplevel) and w.title() == title)

    def button(self, dialog, text):
        return next(w for w in descendants(dialog)
                    if isinstance(w, ttk.Button) and w.cget('text') == text)

    def finish_runs(self):
        deadline = time.monotonic() + 10
        while self.app.runner.active and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertFalse(self.app.runner.active, 'Run did not finish')

    def test_schedule_keeps_original_task_when_selection_changes(self):
        self.app.fields['message'].set('From A form')
        self.app.schedule_dialog()
        window = self.dialog('Schedule automation')
        self.select(self.b['id'])
        changed = copy.deepcopy(self.a)
        changed['name'] = 'A edited while dialog is open'
        self.app.store.save_task(changed)
        self.button(window, 'Save schedule').invoke()
        tasks = {task['id']: task for task in self.app.store.list_tasks()}
        self.assertIn('schedule', tasks[self.a['id']])
        self.assertNotIn('schedule', tasks[self.b['id']])
        self.assertEqual(tasks[self.a['id']]['schedule']['values'], {'message': 'From A form'})
        self.assertEqual(tasks[self.a['id']]['name'], 'A edited while dialog is open')

    def test_empty_search_cannot_launch_hidden_task(self):
        self.app.search_var.set('a query with zero matching tasks')
        self.app.start()
        self.assertEqual(self.app.store.list_runs(), [])
        self.assertEqual(self.app.page, 'Library')

    def test_create_and_import_editor_cannot_replace_an_existing_id(self):
        original = next(task for task in self.app.store.list_tasks() if task['id'] == self.a['id'])
        for imported in (None, self.task('new-import', 'Imported task')):
            with self.subTest(imported=imported is not None):
                self.app.editor(imported=imported)
                window = self.dialog('Automation manifest')
                text = next(w for w in descendants(window) if isinstance(w, tk.Text))
                replacement = dict(original, name='Accidental overwrite')
                text.delete('1.0', 'end')
                text.insert('1.0', json.dumps(replacement))
                # Suppress only the native error dialog; verify the persisted result.
                with patch('runloom.app.messagebox.showerror'):
                    self.button(window, 'Save automation').invoke()
                saved = next(task for task in self.app.store.list_tasks() if task['id'] == self.a['id'])
                self.assertEqual(saved, original)
                self.assertTrue(window.winfo_exists())
                window.destroy()

    def test_due_schedule_coalesces_missed_slots_and_disabled_does_not_run(self):
        now = time.time()
        active = copy.deepcopy(self.a)
        active['schedule'] = {'kind': 'interval', 'seconds': 60, 'next_at': now - 3600,
                              'values': {'message': 'Scheduled value'}}
        disabled = copy.deepcopy(self.b)
        disabled['schedule'] = {'kind': 'interval', 'seconds': 60, 'next_at': now - 3600,
                                'enabled': False, 'values': {}}
        self.app.store.save_task(active)
        self.app.store.save_task(disabled)
        self.app.tick_schedules()
        self.finish_runs()
        self.app.tick_schedules()
        runs = self.app.store.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['task_id'], active['id'])
        self.assertEqual(runs[0]['status'], 'succeeded', runs[0])
        self.assertIn('Scheduled value', runs[0]['logs'])
        tasks = {task['id']: task for task in self.app.store.list_tasks()}
        self.assertGreater(tasks[active['id']]['schedule']['next_at'], now)
        self.assertEqual(tasks[disabled['id']]['schedule']['next_at'], now - 3600)

    def test_saving_open_editor_does_not_restore_already_consumed_schedule(self):
        active = copy.deepcopy(self.a)
        active['schedule'] = {'kind': 'interval', 'seconds': 60, 'next_at': time.time() - 3600,
                              'values': {'message': 'One scheduled run'}}
        self.app.store.save_task(active)
        self.app.editor(task=active)
        window = self.dialog('Automation manifest')
        text = next(w for w in descendants(window) if isinstance(w, tk.Text))
        edited = json.loads(text.get('1.0', 'end'))
        edited['name'] = 'Edited name'
        text.delete('1.0', 'end')
        text.insert('1.0', json.dumps(edited))
        self.app.tick_schedules()
        self.finish_runs()
        self.button(window, 'Save automation').invoke()
        self.app.tick_schedules()
        self.finish_runs()
        runs = self.app.store.list_runs()
        self.assertEqual(len(runs), 1, 'Saving the editor must not replay an already consumed due slot')
        saved = next(task for task in self.app.store.list_tasks() if task['id'] == active['id'])
        self.assertEqual(saved['name'], 'Edited name')


class WorkspaceLockRegressions(unittest.TestCase):
    def test_second_process_denied_then_admitted_after_release(self):
        work = ROOT / 'work'
        work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as folder:
            code = ('from pathlib import Path; import sys; from runloom.instance import WorkspaceLock\n'
                    'try: lock = WorkspaceLock(Path(sys.argv[1]))\n'
                    'except RuntimeError: sys.exit(7)\n'
                    'lock.close()\n')
            lock = WorkspaceLock(Path(folder))
            try:
                denied = subprocess.run([sys.executable, '-c', code, folder], cwd=ROOT, capture_output=True, timeout=10)
                self.assertEqual(denied.returncode, 7, denied.stderr)
            finally:
                lock.close()
            admitted = subprocess.run([sys.executable, '-c', code, folder], cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(admitted.returncode, 0, admitted.stderr)


if __name__ == '__main__':
    unittest.main()

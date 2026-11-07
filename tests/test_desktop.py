import unittest
import os
from pathlib import Path
import tempfile
import time


class DesktopHelpers(unittest.TestCase):
    def test_export_removes_secrets_and_schedule_values(self):
        from runloom.app import export_task
        task = {'id': 'demo', 'parameters': [{'id': 'token', 'secret': True, 'default': 'private'}],
                'schedule': {'values': {'token': 'private'}}}
        result = export_task(task)
        self.assertNotIn('private', str(result))
        self.assertEqual(task['parameters'][0]['default'], 'private')

    def test_duration_is_real_elapsed_time(self):
        from runloom.app import duration
        self.assertEqual(duration({'started_at': 10, 'finished_at': 75}), '1m 05s')

    def test_real_desktop_form_run_history_and_replay(self):
        import tkinter as tk
        from runloom.app import App
        base = Path(__file__).resolve().parents[1] / 'work'
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            root = tk.Tk()
            root.withdraw()
            app = App(root, folder)
            try:
                task = next(t for t in app.store.list_tasks() if t['id'] == 'builtin-organizer')
                app.task = task
                app.show_library()
                app.start()
                self.assertEqual(app.page, 'Run details')
                rid = app.run_id
                deadline = time.monotonic() + 15
                while app.runner.active and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.02)
                record = app.store.get_run(rid)
                self.assertEqual(record['status'], 'succeeded', record)
                self.assertTrue(record['artifacts'])
                self.assertTrue(all(Path(a).exists() for a in record['artifacts']))
                app.refresh_run()
                app.show_history()
                app.replay(rid)
                self.assertEqual(app.page, 'Library')
                self.assertEqual(app.fields['source'].get(), task['parameters'][0]['default'])
                app.show_settings()
                app.show_schedules()
            finally:
                app.close()


if __name__ == '__main__':
    unittest.main()

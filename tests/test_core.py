import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


class CoreTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[3] / 'work'
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='runloom тест ', dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        try:
            self.manifest = importlib.import_module('runloom.manifest')
            self.storemod = importlib.import_module('runloom.store')
            self.runnermod = importlib.import_module('runloom.runner')
            self.schedulemod = importlib.import_module('runloom.scheduler')
        except ModuleNotFoundError as exc:
            self.fail(f'Core module is not implemented: {exc}')
        self.store = self.storemod.Store(self.root / 'state.sqlite')
        self.addCleanup(self.store.close)
        self.runner = self.runnermod.Runner(self.store)
        self.addCleanup(self.runner.shutdown)

    def task(self, code='print("hello")', **kwargs):
        path = self.root / 'worker тест.py'
        path.write_text(code, encoding='utf-8')
        return dict(schema_version=1, id='test', name='Test', executable='{python}',
                    args=[str(path)], cwd=str(self.root), parameters=[], **kwargs)

    def finish(self, rid, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.store.get_run(rid)
            if run['status'] not in ('queued', 'running'):
                return run
            time.sleep(.02)
        self.fail('run did not finish within deadline')

    def test_validates_and_binds_without_shell_or_recursive_substitution(self):
        task = self.task(parameters_override=True)
        task.pop('parameters_override')
        task['parameters'] = [{'id':'name','type':'string','required':True}]
        task['args'] = ['--name={name}', '{app}']
        self.assertEqual(self.manifest.bind_command(task, {'name':'a b & {app}'})[1], '--name=a b & {app}')
        self.assertEqual(self.manifest.bind_command(task, {'name':'x'})[0], sys.executable)
        with self.assertRaises(ValueError):
            self.manifest.validate_values(task, {})
        task['args'] = ['{missing}']
        with self.assertRaises(ValueError):
            self.manifest.validate_manifest(task)

    def test_rejects_invalid_parameters_and_nonfinite_numbers(self):
        task = self.task()
        task['parameters'] = [{'id':'n','type':'number','min':1,'max':4}]
        for value in ['nan', 'inf', 'no', 0, 5, True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.manifest.validate_values(task, {'n':value})
        self.assertEqual(self.manifest.validate_values(task, {'n':'2'})['n'], 2)
        task['parameters'] = [{'id':'x','type':'boolean'}]
        self.assertFalse(self.manifest.validate_values(task, {'x':'false'})['x'])
        with self.assertRaises(ValueError):
            self.manifest.validate_values(task, {'x':'yes please'})

    def test_unicode_argument_and_protocol_and_stderr_are_retained(self):
        task = self.task('import sys,json\nprint(sys.argv[1])\nprint(json.dumps({"runloom":1,"type":"progress","value":42}))\nprint(json.dumps({"runloom":1,"type":"artifact","path":"résultat.txt"}))\nprint("oops",file=sys.stderr)')
        task['args'].append('привет with spaces & shell')
        run = self.finish(self.runner.start(task, {}))
        self.assertEqual(run['status'], 'succeeded')
        self.assertIn('привет with spaces & shell', run['logs'])
        self.assertIn('oops', run['logs'])
        self.assertEqual(run['progress'], 42)
        self.assertEqual(run['artifacts'], [str(self.root / 'résultat.txt')])

    def test_nonzero_and_launch_errors_are_terminal_history(self):
        run = self.finish(self.runner.start(self.task('raise SystemExit(7)'), {}))
        self.assertEqual((run['status'],run['exit_code']), ('failed',7))
        task = self.task()
        task['executable'] = str(self.root / 'nonexistent.exe')
        run = self.finish(self.runner.start(task, {}))
        self.assertEqual(run['status'], 'failed')
        self.assertTrue(run['error'])
        task = self.task()
        task['cwd'] = str(self.root / 'missing-folder')
        self.assertEqual(self.finish(self.runner.start(task, {}))['status'], 'failed')

    def test_cancel_timeout_and_atomic_no_overlap(self):
        task = self.task('import time\nprint("ready",flush=True)\ntime.sleep(60)')
        rid = self.runner.start(task, {})
        with self.assertRaises(ValueError):
            self.runner.start(task, {})
        deadline = time.monotonic()+5
        while 'ready' not in self.store.get_run(rid)['logs'] and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertIn('ready',self.store.get_run(rid)['logs'])
        self.runner.cancel(rid)
        self.assertEqual(self.finish(rid)['status'], 'cancelled')
        task['timeout'] = .15
        self.assertEqual(self.finish(self.runner.start(task, {}))['status'], 'timed_out')

    def test_cancellation_terminates_descendant_process(self):
        child = self.root / 'child.py'
        child.write_text('import time\nfrom pathlib import Path\nPath("child-ready").touch()\ntime.sleep(1.5)\nPath("escaped").touch()\ntime.sleep(60)',encoding='utf-8')
        task = self.task('import subprocess,sys,time\nsubprocess.Popen([sys.executable,"child.py"])\ntime.sleep(60)')
        rid = self.runner.start(task,{})
        deadline = time.monotonic()+5
        while not (self.root/'child-ready').exists() and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertTrue((self.root/'child-ready').exists())
        self.runner.cancel(rid)
        self.assertEqual(self.finish(rid)['status'],'cancelled')
        time.sleep(1.6)
        self.assertFalse((self.root/'escaped').exists())

    def test_concurrent_starts_enforce_no_overlap_atomically(self):
        task = self.task('import time\ntime.sleep(60)')
        accepted, rejected = [],[]
        barrier = threading.Barrier(8)
        def start():
            barrier.wait()
            try: accepted.append(self.runner.start(task,{}))
            except ValueError: rejected.append(True)
        threads = [threading.Thread(target=start) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(accepted),1)
        self.assertEqual(len(rejected),7)
        self.runner.cancel(accepted[0])
        self.finish(accepted[0])

    def test_terminal_snapshot_is_independent_of_later_task_edits(self):
        task = self.task()
        self.store.save_task(task)
        rid = self.runner.start(task,{})
        self.finish(rid)
        task['name'] = 'Changed later'
        self.store.save_task(task)
        self.assertEqual(self.store.get_run(rid)['task_name'],'Test')

    def test_plain_output_keeps_progress_indeterminate(self):
        run = self.finish(self.runner.start(self.task(),{}))
        self.assertIsNone(run['progress'])

    def test_twenty_fast_processes_are_not_misclassified_as_launch_failures(self):
        task = self.task('print("fast")')
        for _ in range(20):
            run = self.finish(self.runner.start(task,{}))
            self.assertEqual(run['status'],'succeeded',run['error'])

    def test_secret_defaults_and_schedule_values_are_not_persisted(self):
        task = self.task()
        task['parameters'] = [{'id':'token','type':'string','secret':True,'default':'never-save-this'}]
        task['schedule'] = {'kind':'interval','seconds':60,'values':{'token':'also-secret'}}
        with self.assertRaises(ValueError): self.store.save_task(task)
        task['schedule']['enabled'] = False
        self.store.save_task(task)
        saved = json.dumps(self.store.list_tasks())
        self.assertNotIn('never-save-this',saved)
        self.assertNotIn('also-secret',saved)

    def test_invalid_schedule_cannot_enter_library(self):
        for schedule in ['oops',{'kind':'daily','time':'30:99'}, {'kind':'interval','seconds':-1}, {'kind':'interval','seconds':60,'values':[]}, {'kind':'interval','seconds':60,'next_at':'never'}]:
            task = self.task()
            task['schedule'] = schedule
            with self.subTest(schedule=schedule), self.assertRaises(ValueError):
                self.manifest.validate_manifest(task)

    def test_frozen_python_token_never_relaunches_gui_executable(self):
        task = self.task()
        fake_gui = str(self.root/'RunloomDesk.exe')
        with patch.object(sys,'frozen',True,create=True), patch.object(sys,'executable',fake_gui):
            command = self.manifest.bind_command(task,{})
        self.assertNotEqual(command[0],fake_gui)

    def test_frozen_builtins_use_sibling_worker_without_module_switch(self):
        from runloom.examples import builtins
        fake_gui = str(self.root/'RunloomDesk.exe')
        with patch.object(sys,'frozen',True,create=True), patch.object(sys,'executable',fake_gui):
            tasks = builtins(self.root,self.root/'data')
        self.assertEqual(len(tasks),3)
        for task in tasks:
            self.assertEqual(task['executable'],str(self.root/'RunloomWorker.exe'))
            self.assertNotIn('-m',task['args'])

    def test_output_without_newlines_is_bounded_and_does_not_hang(self):
        task = self.task('import sys\nsys.stdout.write("x"*2000000)\nsys.stdout.flush()')
        run = self.finish(self.runner.start(task, {}))
        self.assertEqual(run['status'], 'succeeded')
        self.assertLessEqual(len(run['logs']), 270000)
        self.assertLessEqual(self.runner.events.qsize(), 1024)

    def test_preview_flag_and_secrets_redacted(self):
        task = self.task('import sys\nprint("preview="+str("--preview" in sys.argv))\nprint(sys.argv[1])', preview=True)
        task['parameters'] = [{'id':'token','type':'string','secret':True}]
        task['args'].append('{token}')
        run = self.finish(self.runner.start(task, {'token':'super-secret'}, preview=True))
        self.assertIn('preview=True', run['logs'])
        self.assertNotIn('super-secret', json.dumps(run))
        self.assertTrue(run['preview'])
        task['preview'] = False
        with self.assertRaises(ValueError):
            self.runner.start(task, {'token':'secret'}, preview=True)

    def test_persistence_and_recovery_and_task_crud(self):
        task = self.task()
        self.store.save_task(task)
        self.assertEqual(self.store.list_tasks()[0]['id'], 'test')
        self.store.delete_task('test')
        self.assertEqual(self.store.list_tasks(), [])
        rid = self.store.create_run({'task_id':'test','status':'running'})
        second = self.storemod.Store(self.root / 'state.sqlite')
        second.close()
        self.assertEqual(self.store.get_run(rid)['status'], 'interrupted')

    def test_threaded_history_updates_do_not_lose_records(self):
        threads = [threading.Thread(target=lambda i=i:self.store.create_run({'task_id':str(i),'status':'succeeded'})) for i in range(30)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(self.store.list_runs()), 30)

    def test_interval_once_and_daily_schedule(self):
        from datetime import datetime
        next_run = self.schedulemod.next_run
        self.assertEqual(next_run({'kind':'interval','seconds':60}, 1000), 1060)
        self.assertEqual(next_run({'kind':'once','at':1200}, 1000), 1200)
        self.assertIsNone(next_run({'kind':'once','at':900}, 1000))
        now = datetime(2026, 2, 10, 10, 0).timestamp()
        self.assertEqual(next_run({'kind':'daily','time':'09:00'}, now),datetime(2026,2,11,9,0).timestamp())
        for schedule in [{'kind':'interval','seconds':0},{'kind':'daily','time':'25:00'},{'kind':'wrong'}]:
            with self.assertRaises(ValueError): next_run(schedule, now)


if __name__ == '__main__':
    unittest.main()

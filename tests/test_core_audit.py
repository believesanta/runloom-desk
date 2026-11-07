"""Regression cases found during the 0.1.1 process and manifest audit."""
import json
from pathlib import Path
import tempfile
import time
import unittest

from runloom.manifest import validate_manifest, validate_values
from runloom.runner import Runner
from runloom.scheduler import next_run
from runloom.store import Store


class CoreAudit(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / 'work' / 'test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='core-audit ', dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'state.db')
        self.addCleanup(self.store.close)
        self.runner = Runner(self.store)
        self.addCleanup(self.runner.shutdown)

    def task(self, code='print("ok")', **fields):
        script = self.root / 'script.py'
        script.write_text(code, encoding='utf-8')
        return dict(schema_version=1, id='audit', name='Audit', executable='{python}',
                    args=[str(script)], cwd=str(self.root), parameters=[], **fields)

    def finish(self, rid):
        until = time.monotonic() + 20
        while time.monotonic() < until:
            run = self.store.get_run(rid)
            if run['status'] not in ('queued', 'running'): return run
            time.sleep(.02)
        self.fail('Run did not finish')

    def events(self):
        result = []
        while not self.runner.events.empty(): result.append(self.runner.events.get_nowait())
        return result

    def test_json_message_decoding_cannot_reveal_escaped_secret(self):
        task = self.task('import json,sys\nprint(json.dumps({"runloom":1,"type":"message","message":sys.argv[1]}))')
        task['parameters'] = [{'id':'token', 'type':'string', 'secret':True}]
        task['args'].append('{token}')
        token = 'секрет"\\token'
        run = self.finish(self.runner.start(task, {'token':token}))
        self.assertEqual(run['status'], 'succeeded')
        self.assertNotIn(token, run['logs'])
        self.assertNotIn(token, json.dumps(self.events(), ensure_ascii=False))
        self.assertIn('••••', run['logs'])

    def test_artifact_resolution_cannot_reveal_cwd_secret(self):
        task = self.task('import json\nprint(json.dumps({"runloom":1,"type":"artifact","path":"result.txt"}))')
        token = 'private-folder'
        (self.root / token).mkdir()
        task['cwd'] = str(self.root / '{token}')
        task['parameters'] = [{'id':'token', 'type':'string', 'secret':True}]
        run = self.finish(self.runner.start(task, {'token':token}))
        self.assertNotIn(token, json.dumps(run,ensure_ascii=False))
        self.assertNotIn(token, json.dumps(self.events(),ensure_ascii=False))

    def test_plain_multiline_secret_is_redacted_across_output_lines(self):
        task = self.task('import sys\nprint(sys.argv[1])')
        task['parameters'] = [{'id':'token', 'type':'string', 'secret':True}]
        task['args'].append('{token}')
        token = 'first-secret-part\nsecond-secret-part'
        run = self.finish(self.runner.start(task, {'token':token}))
        self.assertNotIn('first-secret-part',run['logs'])
        self.assertNotIn('second-secret-part',run['logs'])

    def slow_log_delivery(self):
        original = self.runner._event
        def deliver(rid, kind, **fields):
            if kind == 'log': time.sleep(.00025)
            original(rid, kind, **fields)
        self.runner._event = deliver

    def test_completed_process_is_not_timed_out_while_draining_output(self):
        self.slow_log_delivery()
        task = self.task('print("x\\n"*5000); print("LAST-LINE")',timeout=.4)
        run = self.finish(self.runner.start(task, {}))
        self.assertEqual(run['status'],'succeeded',run.get('error'))
        self.assertIn('LAST-LINE',run['logs'])

    def test_completed_process_drains_all_queued_output_before_terminal_state(self):
        self.slow_log_delivery()
        task = self.task('print("x\\n"*14000); print("LAST-LINE")',timeout=20)
        run = self.finish(self.runner.start(task, {}))
        self.assertEqual(run['status'],'succeeded')
        self.assertIn('LAST-LINE',run['logs'])

    def test_malformed_metadata_is_rejected_as_value_error(self):
        bad = [({'schema_version':True},None), ({'cwd':''},None),
               ({}, {'id':'p','type':[]}), ({},{'id':'p','type':'string','label':None}),
               ({}, {'id':'p','type':'string','default':[]}),
               ({}, {'id':'p','type':'boolean','default':'false'}),
               ({}, {'id':'p','type':'number','default':'nan'})]
        for fields, parameter in bad:
            task = self.task()
            task.update(fields)
            if parameter: task['parameters'] = [parameter]
            with self.subTest(fields=fields,parameter=parameter), self.assertRaises(ValueError):
                validate_manifest(task)

    def test_scheduler_rejects_nonfinite_and_boolean_inputs(self):
        for schedule,now in [('bad',100), ({'kind':'interval','seconds':True},100),
                             ({'kind':'once','at':True},0), ({'kind':'interval','seconds':1},float('nan'))]:
            with self.subTest(schedule=schedule,now=now), self.assertRaises(ValueError):
                next_run(schedule,now)

    def test_boolean_protocol_values_do_not_claim_numeric_progress(self):
        task = self.task('print(\'{"runloom":1,"type":"progress","value":true}\')')
        run = self.finish(self.runner.start(task,{}))
        self.assertIsNone(run['progress'])

    def test_cancel_after_process_exit_preserves_success(self):
        original = self.runner._event
        cancelled = []
        def deliver(rid,kind,**fields):
            if kind == 'log' and not cancelled:
                process = self.runner.active[rid]['process']
                process.wait(timeout=5)
                self.runner.cancel(rid)
                cancelled.append(rid)
            original(rid,kind,**fields)
        self.runner._event = deliver
        run = self.finish(self.runner.start(self.task('print("x\\n"*2500)'),{}))
        self.assertTrue(cancelled)
        self.assertEqual(run['status'],'succeeded')

    def test_scheduled_values_are_validated_before_persistence(self):
        task = self.task()
        task['parameters'] = [{'id':'n','type':'number','min':1,'required':True}]
        task['schedule'] = {'kind':'interval','seconds':60,'values':{'n':-3}}
        with self.assertRaises(ValueError): self.store.save_task(task)

    def test_bound_empty_working_directory_never_falls_back_to_app_directory(self):
        task = self.task()
        task['parameters'] = [{'id':'directory','type':'folder'}]
        task['cwd'] = '{directory}'
        run = self.finish(self.runner.start(task,{'directory':''}))
        self.assertEqual(run['status'],'failed')
        self.assertIn('directory',run['error'].lower())

    def test_numeric_overflow_and_invalid_schedule_enabled_raise_value_error(self):
        task = self.task()
        task['parameters'] = [{'id':'number','type':'number'}]
        with self.assertRaises(ValueError): validate_values(task,{'number':10**1000})
        with self.assertRaises(ValueError): next_run({'kind':'daily','time':'09:00'},1e100)
        with self.assertRaises(ValueError): next_run({'kind':'interval','seconds':60,'enabled':'yes'},1)

    def test_json_surrogate_output_cannot_strand_running_record(self):
        payload = json.dumps({'runloom':1,'type':'message','message':chr(0xD800)})
        task = self.task(f'print({payload!r})')
        rid = self.runner.start(task,{})
        deadline = time.monotonic()+3
        while time.monotonic()<deadline and self.store.get_run(rid)['status'] in ('running','queued'):
            time.sleep(.02)
        run = self.store.get_run(rid)
        self.assertEqual(run['status'],'succeeded')
        self.assertNotIn(rid,self.runner.active)

    def test_lone_surrogates_in_manifest_or_values_are_rejected(self):
        task = self.task()
        task['name'] = chr(0xD800)
        with self.assertRaises(ValueError): validate_manifest(task)
        task['name'] = 'valid'
        task['parameters'] = [{'id':'text','type':'string'}]
        with self.assertRaises(ValueError): validate_values(task,{'text':chr(0xD800)})


if __name__ == '__main__': unittest.main()

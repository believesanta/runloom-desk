"""Regressions for data loss and stale state found during the desktop audit."""
import copy
import json
import tkinter as tk
import unittest
from unittest.mock import patch, MagicMock

import test_ui_regressions as helpers
from runloom.app import main


class UIAudit(unittest.TestCase):
    setUp = helpers.UIRegressions.setUp
    tearDown = helpers.UIRegressions.tearDown
    task = helpers.UIRegressions.task
    select = helpers.UIRegressions.select
    dialog = helpers.UIRegressions.dialog
    button = helpers.UIRegressions.button

    def test_disable_schedule_preserves_later_task_edit(self):
        stale = copy.deepcopy(self.a)
        stale['schedule'] = {'kind': 'interval', 'seconds': 60}
        self.app.store.save_task(stale)
        edited = copy.deepcopy(stale)
        edited['name'] = 'Updated name'
        edited['args'] = ['-c', 'print("Updated script")']
        self.app.store.save_task(edited)
        self.app.disable_schedule(stale)
        saved = next(t for t in self.app.store.list_tasks() if t['id'] == stale['id'])
        self.assertEqual(saved['name'], edited['name'])
        self.assertEqual(saved['args'], edited['args'])
        self.assertNotIn('schedule', saved)

    def test_edit_parameter_definition_discards_incompatible_draft(self):
        self.app.fields['message'].set('Old text draft')
        self.app.editor(task=self.a)
        window = self.dialog('Automation manifest')
        box = next(w for w in helpers.descendants(window) if isinstance(w, tk.Text))
        edited = json.loads(box.get('1.0', 'end'))
        edited['parameters'][0].update(type='number', default=42)
        box.delete('1.0', 'end')
        box.insert('1.0', json.dumps(edited))
        self.button(window, 'Save automation').invoke()
        self.assertEqual(self.app.fields['message'].get(), '42')
        self.assertEqual(self.app.values()['message'], 42)

    def test_replay_preserves_other_tasks_draft_and_restores_run_values(self):
        run_id = self.app.store.create_run({'task_id': self.b['id'], 'status': 'succeeded',
                                           'values': {'message': 'Saved run value'}})
        self.app.fields['message'].set('Unfinished A draft')
        self.app.replay(run_id)
        self.assertEqual(self.app.task['id'], self.b['id'])
        self.assertEqual(self.app.fields['message'].get(), 'Saved run value')
        self.select(self.a['id'])
        self.assertEqual(self.app.fields['message'].get(), 'Unfinished A draft')


class StartupAudit(unittest.TestCase):
    def test_unwritable_workspace_reports_error_and_closes_window(self):
        root = MagicMock()
        with patch('sys.argv', ['runloom']), patch('runloom.app.tk.Tk', return_value=root), \
             patch('runloom.instance.WorkspaceLock', side_effect=PermissionError('Access denied')), \
             patch('runloom.app.messagebox.showerror') as error:
            main()
        error.assert_called_once()
        root.destroy.assert_called_once()

    def test_startup_failure_reports_error_and_releases_lock(self):
        root, lock = MagicMock(), MagicMock()
        with patch('sys.argv', ['runloom']), patch('runloom.app.tk.Tk', return_value=root), \
             patch('runloom.instance.WorkspaceLock', return_value=lock), \
             patch('runloom.app.App', side_effect=RuntimeError('Invalid database')), \
             patch('runloom.app.messagebox.showerror') as error:
            main()
        error.assert_called_once()
        root.destroy.assert_called_once()
        lock.close.assert_called_once()

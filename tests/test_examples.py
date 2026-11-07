"""Real subprocess tests for the bundled, non-destructive automations."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class ExampleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source folder"
        self.source.mkdir()
        self.dest = self.base / "output folder"

    def run_example(self, action, *args, success=True):
        result = subprocess.run(
            [sys.executable, "-m", "runloom.examples", action,
             "--source", str(self.source), "--destination", str(self.dest), *args],
            cwd=ROOT, capture_output=True, text=True, timeout=20,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def events(self, result):
        return [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]

    def test_organizer_copies_without_overwrite_and_reports_artifacts(self):
        (self.source / "note.txt").write_text("original", encoding="utf-8")
        self.run_example("organizer", "--group", "type")
        result = self.run_example("organizer", "--group", "type")
        self.assertEqual((self.source / "note.txt").read_text(), "original")
        copies = list((self.dest / "documents").glob("note*.txt"))
        self.assertEqual(len(copies), 2)
        self.assertTrue(all(p.read_text() == "original" for p in copies))
        events = self.events(result)
        self.assertIn(100, [e['value'] for e in events if e['type'] == 'progress'])
        self.assertTrue(any(Path(e['path']).is_file() for e in events if e['type'] == 'artifact'))

    def test_all_previews_leave_destination_absent(self):
        (self.source / "note.txt").write_text("keep")
        Image.new("RGB", (50, 25), "red").save(self.source / "photo.png")
        for action in ("organizer", "images", "snapshot"):
            with self.subTest(action=action):
                self.run_example(action, "--preview")
                self.assertFalse(self.dest.exists())

    def test_organizer_month_uses_file_modified_time(self):
        source = self.source / "note.txt"
        source.write_text("keep")
        from datetime import datetime
        stamp = datetime(2024, 2, 12, 12).timestamp()
        os.utime(source, (stamp, stamp))
        self.run_example("organizer", "--group", "month")
        self.assertEqual((self.dest / "2024-02" / "note.txt").read_text(), "keep")

    def test_images_resize_convert_preserve_original_and_skip_bad_files(self):
        original = self.source / "photo.png"
        Image.new("RGBA", (200, 100), (255, 0, 0, 100)).save(original)
        content = original.read_bytes()
        (self.source / "bad.jpg").write_text("not an image")
        (self.source / "notes.txt").write_text("not an image")
        result = self.run_example("images", "--width", "80", "--height", "80", "--format", "jpeg")
        with Image.open(self.dest / "photo.jpg") as image:
            self.assertEqual(image.size, (80, 40))
            self.assertEqual(image.format, "JPEG")
        self.assertEqual(original.read_bytes(), content)
        self.assertIn("Skipped", result.stdout)
        self.assertFalse((self.dest / "bad.jpg").exists())

    def test_truncated_images_are_reported_and_other_files_continue(self):
        Image.new("RGB", (200, 100), "blue").save(self.source / "valid.jpg")
        content = (self.source / "valid.jpg").read_bytes()
        (self.source / "broken.jpg").write_bytes(content[:len(content) - 50])
        result = self.run_example("images")
        self.assertTrue((self.dest / "valid.png").exists())
        self.assertIn("Skipped broken.jpg", result.stdout)

    def test_snapshot_excludes_patterns_and_can_restore_one_file(self):
        (self.source / "nested").mkdir()
        (self.source / "nested" / "keep.txt").write_text("restore me", encoding="utf-8")
        (self.source / "ignored.tmp").write_text("ignore")
        (self.source / "cache").mkdir()
        (self.source / "cache" / "ignored.txt").write_text("ignore")
        result = self.run_example("snapshot", "--exclude", "*.tmp,cache")
        reports = [Path(e['path']) for e in self.events(result) if e['type'] == 'artifact' and e['path'].endswith('.json')]
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        snapshot = reports[0].parent
        self.assertEqual(report['copied'], 1)
        self.assertFalse((snapshot / "files" / "ignored.tmp").exists())
        self.assertFalse((snapshot / "files" / "cache").exists())
        restore = self.base / "restored.txt"
        shutil.copy2(snapshot / "files" / "nested" / "keep.txt", restore)
        self.assertEqual(restore.read_text(), "restore me")
        self.run_example("snapshot", "--exclude", "*.tmp,cache")
        self.assertEqual(len(list(self.dest.iterdir())), 2)

    def test_rejects_overlapping_source_and_destination_before_writing(self):
        (self.source / "note.txt").write_text("keep")
        for dest in (self.source, self.source / "nested", self.base):
            self.dest = dest
            for action in ("organizer", "images", "snapshot"):
                with self.subTest(action=action, destination=dest):
                    self.run_example(action, success=False)
        self.assertEqual(list(self.source.iterdir()), [self.source / "note.txt"])

    @unittest.skipUnless(os.name == 'nt', 'Windows junction behavior')
    def test_snapshot_skips_junctions_and_rejects_linked_output(self):
        external = self.base / "external"
        external.mkdir()
        (external / "outside.txt").write_text("do not traverse")
        junction = self.source / "junction"
        create = subprocess.run(
            ['cmd', '/c', 'mklink', '/J', str(junction), str(external)],
            capture_output=True, text=True,
        )
        if create.returncode != 0:
            self.skipTest('Junction creation not permitted by this environment: ' + create.stderr.strip())
        result = self.run_example("snapshot")
        report_path = next(Path(e['path']) for e in self.events(result)
                           if e['type'] == 'artifact' and e['path'].endswith('.json'))
        report = json.loads(report_path.read_text())
        self.assertEqual(report['copied'], 0)
        self.assertIn('junction', report['skipped'])
        self.dest = junction
        self.run_example("snapshot", success=False)
        self.assertEqual([p.name for p in external.iterdir()], ['outside.txt'])

    def test_manifest_defaults_are_runnable_and_sample_edits_survive_reload(self):
        from runloom.examples import builtins
        manifests = builtins(ROOT, self.base / "data")
        self.assertEqual(len(manifests), 3)
        for manifest in manifests:
            params = {p['id']: str(p['default']) for p in manifest['parameters']}
            args = [a.format(**params) for a in manifest['args']]
            result = subprocess.run([sys.executable, *args, '--preview'], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        demo = self.base / "data" / "demo-input" / "notes.txt"
        demo.write_text("user changed this")
        builtins(ROOT, self.base / "data")
        self.assertEqual(demo.read_text(), "user changed this")


if __name__ == '__main__':
    unittest.main()

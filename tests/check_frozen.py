"""Check a built Windows folder: python tests/check_frozen.py --bundle PATH."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runloom.examples import seed_demo
from PIL import Image


def check(bundle):
    bundle = Path(bundle).resolve()
    worker = bundle / 'RunloomWorker.exe'
    report = {'checks': [], 'python_on_path': False}
    env = dict(os.environ)
    env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    env.pop('PYTHONPATH', None)
    # Deliberately adversarial: the worker must enforce its UTF-8 wire protocol.
    env['PYTHONIOENCODING'] = 'cp1251'
    scratch_root = ROOT / 'work'
    scratch_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='frozen test тест ', dir=scratch_root) as folder:
        scratch = Path(folder)
        source = seed_demo(bundle / '_internal', scratch)
        cases = [('organizer', ['--group', 'type']),
                 ('images', ['--width', '160', '--height', '100', '--format', 'jpeg']),
                 ('snapshot', ['--exclude', '*.tmp,__pycache__,.git'])]
        for action, extra in cases:
            destination = scratch / 'results' / action
            args = [str(worker), action, '--source', str(source), '--destination', str(destination), *extra]
            for preview in (True, False):
                result = subprocess.run(args + (['--preview'] if preview else []), cwd=scratch, env=env,
                                        capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
                # Strict decode makes a localized-console encoding regression fail.
                stdout, stderr = result.stdout.decode('utf-8'), result.stderr.decode('utf-8')
                assert result.returncode == 0, (action, stdout, stderr)
                if preview:
                    assert not destination.exists()
                    assert 'Would ' in stdout
                else:
                    assert any(p.is_file() for p in destination.rglob('*'))
                    assert '"type": "artifact"' in stdout
                    if action == 'images':
                        with Image.open(next(destination.glob('*.jpg'))) as picture:
                            assert picture.width <= 160 and picture.height <= 100
                    elif action == 'snapshot':
                        assert next(destination.rglob('sample-landscape.png')).read_bytes() == (source / 'sample-landscape.png').read_bytes()
                report['checks'].append({'action': action, 'preview': preview, 'exit_code': result.returncode})
        assert (source / 'sample-landscape.png').exists()
    report['status'] = 'passed'
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT.parent / 'runloom-windows' / 'RunloomDesk')
    args = parser.parse_args()
    print(json.dumps(check(args.bundle), indent=2))

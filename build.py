"""Create a deterministic source distribution; no runtime or signing claims."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
EXCLUDE = {'.git', '__pycache__', '.runloom-data', '.venv', 'dist', 'work'}


def build():
    target = ROOT / 'dist' / 'runloom-desk-0.1.2-source.zip'
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(ROOT.rglob('*')):
            relative = path.relative_to(ROOT)
            if not path.is_file() or EXCLUDE.intersection(relative.parts) or path.suffix in {'.pyc', '.db'}:
                continue
            info = zipfile.ZipInfo('runloom-desk/' + relative.as_posix(), date_time=(2026, 11, 5, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    print(target)
    return target


if __name__ == '__main__':
    build()

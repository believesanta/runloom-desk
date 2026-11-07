# Run on Windows using Python 3.12. Both executables share the runtime files.
from pathlib import Path
import importlib.metadata
import sys

root = Path(SPECPATH)
datas = [(str(root / 'docs'), 'docs'),
         (str(root / 'examples' / 'fixtures'), 'examples/fixtures'),
         (str(root / 'examples' / 'README.md'), 'examples'),
         (str(root / 'LICENSE'), 'licenses/Runloom'),
         (str(root / 'THIRD_PARTY.md'), 'licenses')]
for document in root.glob('*.md'):
    datas.append((str(document), '.'))
datas.append((str(root / 'LICENSE'), '.'))
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.is_file():
    datas.append((str(python_license), 'licenses/CPython'))
for license_path in (Path(sys.base_prefix) / 'tcl').glob('*/license.terms'):
    datas.append((str(license_path), 'licenses/' + license_path.parent.name))
for distribution in ('Pillow', 'PyInstaller'):
    metadata = importlib.metadata.distribution(distribution)
    for file in metadata.files or []:
        if '/licenses/' in str(file).replace('\\', '/'):
            datas.append((str(metadata.locate_file(file)), 'licenses/' + distribution))

excludes = ['numpy', 'matplotlib', 'pandas', 'pytest', 'IPython']
gui = Analysis([str(root / 'desktop_entry.py')], pathex=[str(root)],
               datas=datas, binaries=[], hiddenimports=[], excludes=excludes)
worker = Analysis([str(root / 'worker_entry.py')], pathex=[str(root)],
                  datas=[], binaries=[], hiddenimports=[], excludes=excludes + ['tkinter'])
gui_pyz = PYZ(gui.pure)
worker_pyz = PYZ(worker.pure)
gui_exe = EXE(gui_pyz, gui.scripts, [], exclude_binaries=True,
              name='RunloomDesk', console=False, debug=False, strip=False, upx=False)
worker_exe = EXE(worker_pyz, worker.scripts, [], exclude_binaries=True,
                 name='RunloomWorker', console=True, debug=False, strip=False, upx=False)
bundle = COLLECT(gui_exe, worker_exe, gui.binaries, gui.datas,
                 worker.binaries, worker.datas, name='RunloomDesk', strip=False, upx=False)

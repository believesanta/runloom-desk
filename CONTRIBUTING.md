# Contributing

Runloom Desk is a small Windows desktop application for trusted local scripts. Keep changes understandable and preserve the source-only, local-first launch path.

## Development

Use Python 3.12 with Tk installed. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m runloom
```

The core uses the Python standard library. Pillow supports the resize example, demo image generation and their tests. Install it for the bundled desktop experience. Do not add a mandatory runtime dependency just to simplify a small helper.

Before submitting a change, run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q runloom examples
python build.py
```

Test from the same interpreter that has the example dependency installed. Use temporary directories and generated fixtures. Never point tests at a contributor's personal documents, photographs or backup folders.

## Changes worth testing

Preserve argument boundaries, Unicode paths, schema validation and terminal history for failed launches. Exercise cancellation, timeout, large output and overlap control with real subprocesses. Schedule tests should use fixed timestamps rather than waiting minutes. File-operation tests should prove originals remain intact and collisions do not overwrite unrelated files.

Tk widgets belong to the UI thread. Worker threads must communicate through the runner's event queue. Preserve backwards compatibility for stored manifests or explicitly version the schema and document a migration.

For a UI change, inspect the real window at normal and scaled DPI, check keyboard focus, and attach an actual screenshot. Explain what you verified and any environment limitations. For a behavior change, update the relevant documentation and the changelog.

For packaging changes, run `build-windows.ps1` on Windows and test the resulting `RunloomDesk.exe` and `RunloomWorker.exe` in their complete folder. Source tests do not exercise the frozen import graph or resource paths. Check the bundled license notices as well as runtime behavior. Keep the source ZIP builder independent of PyInstaller.

## Contributions and licensing

Submit code you have the right to share under the project's MIT license. List new dependencies and their licenses in `THIRD_PARTY.md`. Use the issue and pull request templates when the project is hosted. There is no live repository URL or release feed in this source bundle; none is implied by the included templates.

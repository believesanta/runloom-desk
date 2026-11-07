# Runloom implementation plan

Goal: a Windows desktop library of trusted local scripts with generated forms, observable runs and schedules.

Architecture: Python 3.12+, Tk/ttk desktop, SQLite history and configuration, subprocess runner; Pillow for the image example only. All worker/UI communication crosses a queue. No server or account.

The user supplied the complete specification and authorized autonomous reversible choices. Windows is the only target for verification. Work takes place in this standalone output directory, not an existing repository.

1. Core: manifest validation and argument binding; SQLite store; cancellable process runner; daily/interval schedule calculations. Write unittest behavioral tests first, exercise real subprocesses.
2. Examples: copy organizer with preview, Pillow resize, versioned folder snapshot and restoration instructions. Test collisions and file preservation on temporary fixtures.
3. Desktop: library, typed forms, streamed logs, artifacts, history, schedules, manifest editor/import/export and settings. Verify end-to-end against core and real examples.
4. Documentation: competitor research, architecture ADR, manifest/protocol guide, trust model, README, contribution and issue templates, CI, license and reproducible packaging.
5. Review: independent core/UI review; run all tests, compile, launch from clean distribution directory, inspect actual UI and capture screenshots. Record exact evidence and environment limitations.

Acceptance: real examples and process lifecycle work, history persists, scheduling semantics are explicit, source package launches, no invented verification or claims of sandboxing.

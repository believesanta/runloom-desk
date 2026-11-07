# Changelog

## 0.1.2 — 2026-11-07

- Fixed secret redaction after JSON decoding, multiline output and artifact path resolution.
- Prevented malformed Unicode output from leaving a completed run stuck in the running state.
- Drained queued output after process exit without discarding the final tail or marking an already completed process as timed out.
- Rejected malformed manifest metadata, defaults and schedule inputs before saving or launching.
- Rejected empty bound working directories instead of silently running from the application directory.
- Kept current task edits when disabling a schedule; refreshed incompatible form drafts after parameter changes.
- Preserved other task drafts when restoring parameters from a previous run.
- Added visible startup errors for inaccessible workspaces and initialization failures.
- Corrected documentation links in the Windows folder distribution.
- Added regression tests covering the reproduced failures.


## 0.1.1 — 2026-11-07

- Added the Mist dark palette inspired by a foggy conifer forest.
- Simplified navigation, headings and branding; added visible active navigation.
- Applied consistent dark inputs, selection states, scrollbars, logs and dialogs.
- Enabled the Windows dark title bar when available.


## 0.1.0 — 2026-11-06

Initial distribution of Runloom Desk.

### Added

- Windows Tk/ttk desktop with a searchable task library, generated parameter forms, command inspection and JSON manifest editing/import/export.
- Subprocess execution with live output, script-reported progress and artifacts, cancellation, timeouts and per-task overlap control.
- SQLite run history with parameter reuse and interrupted-run recovery; one window per workspace through an OS-owned lock.
- In-app interval and daily schedules, with one attempt for overdue work and explicit local-time behavior.
- File organizer, batch image resizer and versioned folder snapshot examples with preview support and preserved originals.
- Manifest validation, literal secret redaction, removal of saved secret defaults, and refusal to enable schedules for tasks with secret fields.
- Research, architecture, manifest/protocol, security and contribution documentation; MIT license, third-party attribution, issue/PR templates and Windows test workflow.
- Source launcher and deterministic source ZIP builder.
- Windows PyInstaller build with a GUI executable, example-worker executable and shared runtime folder.

### Scope

The source launch requires Python and the example dependency to be installed separately. The Windows folder build bundles those runtimes for the app and examples; custom scripts need their own runtimes. There is no background scheduling service, updater, script sandbox or credential vault. Scheduling requires the desktop to remain running; logs retain a bounded tail. No public release or remote CI execution is implied by this changelog.

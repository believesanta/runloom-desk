# Verification record

## 0.1.2 bug audit

The 7 November 2026 audit added 19 regression tests. Reproduced failures included escaped and multiline secrets reaching logs, secrets reappearing in resolved artifact paths, queued output being discarded after process exit, false timeout/cancellation during drainage, and malformed Unicode stranding a run in `running`. Manifest, schedule and working-directory validation were tightened. Desktop tests reproduced stale schedule actions overwriting task edits, incompatible form drafts after manifest edits, replay losing another task's draft, and missing startup error dialogs. All are covered by passing regressions in this release.

The complete source suite discovered **56 tests: 55 passed, one skipped**. Compilation passed. The skipped Windows junction test is described below. A passing suite is evidence for these scenarios, not a guarantee that every possible defect has been found.

## 0.1.1 visual update

The Mist theme was inspected in the running source desktop on 7 November 2026. Navigation, controls, selection, logs and output lists use the dark palette; a real image-processing run completed successfully. Existing behavior tests were rerun after the visual changes. The wallpaper was used only as a visual reference and is not included in the repository or distribution.

Verified locally on Windows x64, Python 3.12.10; final packaging checked 7 November 2026. This records executed checks, not remote CI results.

## Automated checks

`python -m unittest discover -s tests -v` discovered 56 tests: **55 passed, one skipped**. The skipped junction test requires creating a Windows junction, which this execution sandbox denies. The source also compiled with `python -m compileall -q runloom tests`.

Coverage includes shell-free Unicode argument binding, invalid manifests, nonzero exits, missing executables and directories, no-newline output flooding, literal secret redaction, cancellation of descendant processes, timeouts, overlapping launches, SQLite persistence/recovery, daily/interval calculations, real Tk form-to-process execution and parameter reuse. UI regressions exercise empty searches, duplicate IDs, schedule dialog task selection, stale editor state and cross-process workspace locking. Example tests verify non-overwriting copies, resize dimensions, exclusions and restoration of a snapshot file.

The source archive was built twice with identical contents and produced identical SHA-256 hashes. A fresh extraction passed the same 56-test suite and `python -m runloom --help`. Tests used an isolated writable temporary directory because the execution sandbox restricts its system temporary directory.

## Windows bundle

PyInstaller 6.20.0 successfully built the two-executable folder distribution. Run:

```powershell
python tests/check_frozen.py --bundle ..\runloom-windows-audit\RunloomDesk
```

All six checks passed: organizer, image resizer and snapshot, each in preview and real-run mode. The child environment's PATH contained only Windows System32 (no external Python), and PYTHONIOENCODING was deliberately set to cp1251. UTF-8 output with Cyrillic paths still decoded correctly. Previews created no destination files; real runs emitted artifacts. Image bounds and snapshot bytes were checked.

The compiled GUI was launched, inspected visually and used to run Batch image resizer through its actual Run button. The run reached `succeeded`; the image and JSON report appeared in its output list. The screenshots show the real application and bundled sample data. A source GUI flow was also verified.

## Boundaries

- Only this Windows host was exercised. No macOS/Linux support claim, remote CI execution or clean Windows virtual-machine test is made.
- The bundle is unsigned, has no installer and must be distributed as a complete folder.
- Scheduling is in-process; closing the application stops execution. DST transitions and clock/timezone changes are documented but were not exhaustively simulated.
- Junction creation was blocked in this sandbox. Existing link rejection has source coverage, but the skipped live junction case remains unverified here.
- No long-duration soak, independent penetration test, comprehensive screen-reader evaluation or performance benchmark was performed.
- History and schedule overview pages refresh when reopened; the current run detail view refreshes continuously.
- Task manifests may contain absolute paths. Review them when moving an existing workspace between installations.

The public GitHub repository and releases have not been created. See [publishing instructions](publishing.md).

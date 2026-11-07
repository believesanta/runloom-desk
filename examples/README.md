# Bundled examples

All three commands copy into a separate destination, preserve originals, and
support `--preview`. Never choose overlapping source and destination folders.
Symbolic links and Windows junctions are skipped. These tools are trusted local
programs, not a filesystem sandbox; do not run them against folders being
concurrently changed by an untrusted program.

```powershell
python -m runloom.examples organizer --source C:\Input --destination C:\Sorted --group type --preview
python -m runloom.examples images --source C:\Pictures --destination C:\Resized --width 1200 --height 800 --format jpeg
python -m runloom.examples snapshot --source C:\Notes --destination C:\Backups --exclude "*.tmp,__pycache__,.git"
```

Organizer recursively copies files into `documents`, `images`, `audio`, `video`,
`archives`, or `other`; month grouping uses each file's local modified date.
Same-name files get a numeric suffix. Existing files are never overwritten.

Image resizing preserves aspect ratio, does not upscale, applies EXIF orientation,
and converts PNG, JPEG, WebP, BMP and TIFF input. JPEG transparency becomes white.
Only the first frame is processed; metadata is not copied. Unsupported or invalid
images are reported as skipped. A report lists outputs and skipped paths.

Snapshots are timestamped directories containing a `files` tree and a JSON report.
Comma-separated exclusions match relative paths or individual file/directory names
with shell patterns. An excluded directory is not traversed. This is a normal file
copy, not an atomic or incremental backup: files changing during a run may represent
different moments, and permissions/alternate streams are not a full system backup.

## Restore a single file

1. Open the snapshot artifact from the completed run.
2. Find the file under `files`, preserving its original relative path.
3. Copy that file into a new restore folder and check it before replacing anything.

For example, use PowerShell (adjust paths to the actual snapshot):

```powershell
New-Item -ItemType Directory -Force C:\Restored
Copy-Item -LiteralPath 'C:\Backups\snapshot-20261105-120000-123456\files\notes.txt' -Destination 'C:\Restored\notes.txt'
```

The app seeds editable sample documents from `fixtures` and draws a sample image
with Pillow under its data directory's `demo-input` folder. Existing demo files
are preserved when the app starts again.

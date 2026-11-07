# Manifest and output protocol

A manifest is a UTF-8 JSON object describing one trusted command. Use **New automation** to edit JSON, or **Import** to review a file before saving it. Saving a manifest does not run the command. Imports require an unused task ID; editing an existing task preserves its ID.

## Complete example

This runs a Python script already present at `C:\MyScripts\report.py`. The script must accept the arguments shown; Runloom Desk does not create it for you.

```json
{
  "schema_version": 1,
  "id": "daily-report",
  "name": "Create a report",
  "description": "Read a folder and write a report to a separate destination.",
  "category": "Documents",
  "executable": "{python}",
  "args": [
    "C:\\MyScripts\\report.py",
    "--source", "{source}",
    "--destination", "{destination}",
    "--limit", "{limit}",
    "--format", "{format}",
    "--include-hidden", "{hidden}"
  ],
  "cwd": "C:\\MyScripts",
  "parameters": [
    {"id": "source", "label": "Source folder", "type": "folder", "required": true},
    {"id": "destination", "label": "Output folder", "type": "folder", "required": true},
    {"id": "limit", "label": "Maximum files", "type": "number", "default": 100, "min": 1, "max": 10000},
    {"id": "format", "label": "Report format", "type": "select", "default": "csv", "options": ["csv", "json"]},
    {"id": "hidden", "label": "Include hidden files", "type": "boolean", "default": false}
  ],
  "timeout": 120,
  "allow_parallel": false,
  "preview": true
}
```

## Task fields

| Field | Meaning |
| --- | --- |
| `schema_version` | Required integer `1`. |
| `id` | Stable identifier, beginning with a letter or underscore; remaining characters can include letters, digits, underscores and hyphens. |
| `name` | Required nonempty display name. |
| `description` | Searchable explanation; defaults to an empty string. |
| `category` | Label shown above the form; defaults to `General`. |
| `executable` | Required executable path or executable available on `PATH`. Use `{python}` for Python; see the source/frozen distinction below. |
| `args` | Array of argument strings; defaults to `[]`. Each element becomes exactly one argument after substitution. |
| `cwd` | Existing working directory; defaults to `{app}`. |
| `parameters` | Parameter definitions, default `[]`. |
| `timeout` | Positive finite seconds; defaults to `3600`. |
| `allow_parallel` | Boolean; defaults to `false`, preventing concurrent runs of this task ID in the app. |
| `preview` | Boolean; defaults to `false`. If true, the UI offers Preview and appends `--preview` when selected. |

Use a real interpreter executable for PowerShell or another language, with the script path as an argument. Direct `.bat` and `.cmd` executables are rejected on Windows. An explicitly invoked shell still has its own command parsing; take responsibility for safely handling inputs in that script.

For example, PowerShell arguments can be `["-NoProfile", "-File", "C:\\MyScripts\\report.ps1", "-Source", "{source}"]` with `powershell.exe` as the executable. The app does not bypass execution policy or install an interpreter.

## Parameters

Every parameter needs a unique `id` using the same identifier rules as tasks. `app` and `python` are reserved. `label` defaults to the ID; `type` defaults to `string`.

| Type | Form and accepted value |
| --- | --- |
| `string` | Text entry. |
| `number` | Text entry validated as a finite number; optional inclusive `min` and `max`. |
| `boolean` | Checkbox. Bound as lowercase `true` or `false`; this does not automatically add or omit a CLI flag. |
| `select` | Read-only dropdown with a nonempty array of string `options`. |
| `file` | Text entry with a file picker. |
| `folder` | Text entry with a folder picker. |

`default` supplies an initial value. `required: true` rejects an empty value. File and folder parameters are strings: the app does not guarantee path existence, readability or suitability for the underlying command. Validate those conditions in the script. Optional blank parameters remain blank argument values; arguments are not automatically omitted.

`secret: true` masks text fields and redacts literal values in saved run details. Use it with string parameters. It is not encrypted storage. Secret defaults must not be embedded in manifests. Export removes secret defaults and scheduled parameter values; runs with secrets require manual entry and should not be scheduled. See [Security](../SECURITY.md).

## Substitution and quoting

In a source launch, `{python}` expands to `sys.executable`. In a frozen Windows build it resolves an external `python` on PATH: the desktop executable is not a general-purpose Python interpreter. Your own Python scripts therefore still need an installed interpreter and their dependencies. The bundled examples use `RunloomWorker.exe` directly and do not depend on external Python.

`{app}` expands to the application's resource root: the extracted project root for source, or the bundled `_internal` directory in the frozen build. `{parameter_id}` expands to a validated form value. Placeholders work in executable, working directory and argument strings. Unknown recognized placeholders are rejected.

Substitution is one pass: braces inside a user's value are literal data. Spaces and Unicode remain inside the same argument. Do not add extra quote characters around an array element just because its value contains spaces. Shell operators such as `&`, `|` or `>` have no shell meaning in ordinary argument values because the runner uses `shell=False`.

## Output protocol, version 1

Existing scripts can print ordinary output; stdout and stderr are merged and shown in Run details. Input is not interactive: stdin is closed. For progress and output locations, print a complete JSON object on one line and flush stdout:

```python
import json

def emit(kind, **data):
    print(json.dumps({"runloom": 1, "type": kind, **data}), flush=True)

emit("message", message="Scanning input folder")
emit("progress", value=25)
emit("artifact", path="reports/summary.csv")
emit("progress", value=100)
```

| Type | Payload | Effect |
| --- | --- | --- |
| `message` | `message`: string | Adds readable text to the log. |
| `progress` | `value`: number from 0 to 100 | Updates progress. A successful exit does not invent 100% progress. |
| `artifact` | `path`: string | Adds an output location; relative paths resolve against the run's working directory. |

Unrecognized lines remain ordinary log text. Keep protocol lines below 16 KiB. Output is decoded as UTF-8 with replacement for invalid bytes. Python children receive UTF-8/unbuffered output environment settings. Other runtimes should explicitly write UTF-8.

The runner retains the last 262,144 characters of logs and up to 1,000 unique artifact paths per run. Write a report file and emit it as an artifact if complete long-term output is needed. Artifact files are not copied into the database, and a path can become unavailable if the file is moved or deleted.

## Schedules and sharing

The Schedule dialog stores current validated form values with either a minute interval or a daily local time. The `schedule` object is app-owned state, not needed in a portable manifest. Import and export remove it. Export includes the command definition, not the referenced script or its dependencies; share those separately and replace machine-specific paths.

Schedules execute only while the app is running. If a stored time becomes overdue, the next scheduler tick attempts one run and computes a future time; it does not replay every missed interval. An overlap rejection or launch failure is not automatically retried. Daily times use the computer's local timezone with no independent timezone or daylight-saving policy controls. The scheduler calculation module also supports a one-time timestamp for internal use; the current dialog exposes interval and daily schedules only.

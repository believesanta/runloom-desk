# Security and trust

Runloom Desk runs **trusted local programs with your Windows account's permissions**. It is not a sandbox. A manifest can point to a program that reads, writes or deletes files, starts other programs, accesses credentials or uses the network. Inspect the executable, arguments, working directory and referenced script before running an imported task or enabling its schedule.

Commands are passed to `subprocess` as an argument list with `shell=False`. That prevents the application from treating ordinary parameter text as shell syntax. It does not make an explicitly selected shell, an interpreter's `-c` argument, a batch file, or a script that evaluates its input safe.

## Data and secrets

Tasks, schedules and run history are stored locally in SQLite. Output files remain where the script writes them. The app has no hosted backend or account. A script is free to make its own network connections.

Secret fields hide input and the runner attempts to redact their literal values in saved run data and output. This is convenience masking, not a credential vault: values are sent to the child process, may be visible in process inspection, and scripts can transform, encode or write them elsewhere. Do not put real credentials in manifest defaults, shared exports, screenshots, issue reports or committed fixtures. Schedules should not be used for tasks requiring secret parameters.

Logs and metadata are not encrypted by the application. Anyone with access to the data directory can read them. Artifact paths reported by a script are trusted output; review them before opening a file. A script can report any path.

## Execution limits

Cancellation and timeouts stop the process on a best-effort basis. A script's external side effects cannot be rolled back, and detached or independently started processes may survive. Preview is a script-provided `--preview` convention; the app cannot prove that a preview is read-only. Only use preview with scripts you trust to honor it.

The application should be run as a normal user. Administrative privileges are not required for ordinary use. There is no automatic elevation, network service or automatic startup registration.

## Reporting a problem

This source distribution has no published repository or established private reporting address. Contact the person or organization that supplied your copy through a private channel, with a minimal redacted reproduction. If publishing a fork, configure a private security reporting route and replace this paragraph with the verified contact before distributing it. Do not post live credentials or private file contents in a public issue.

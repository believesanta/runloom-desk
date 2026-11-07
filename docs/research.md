# Research and product direction

Reviewed 5 November 2026. This is a focused desk review of six alternatives using their own documentation, not a hands-on benchmark. Features, packaging and commercial terms can change. “Fit” below is an assessment for one person running trusted scripts on a Windows computer.

## Comparison

| Tool | Documented workflow and parameters | Scheduling and observation | Windows installation / personal fit |
| --- | --- | --- | --- |
| **Script Kit** | Desktop script launcher with a JavaScript/TypeScript SDK, prompts and UI helpers. | The guide documents schedule metadata and log access. | The official site offers Windows downloads. A strong personal automation environment; adopting its SDK is a larger change than describing an existing CLI in JSON. [Site](https://www.scriptkit.com/), [guide](https://github.com/johnlindquist/kit/blob/main/GUIDE.md). |
| **Gooey** | Wraps Python `argparse` programs with a decorator; `GooeyParser` provides file pickers and other widgets. Displays program output and configurable progress. | The reviewed README focuses on individual GUI-wrapped commands; a central recurring scheduler and cross-script history are not established by that source. | Installed as a Python package, with wxPython underlying the GUI. Excellent when distributing one Python utility with a form. [Official README](https://github.com/chriskiehl/Gooey). |
| **script-server** | JSON-configured scripts become browser forms without modifying the scripts. Includes typed parameters, output files and a configuration UI. | Real-time output, execution history and separate process log files; releases document recurring schedules. | Python/Tornado server plus browser; Windows support is explicitly described as lightly tested. Closest functional analogue, but it brings a server and potentially multiple users. [README](https://github.com/bugy/script-server), [release notes](https://github.com/bugy/script-server/releases). |
| **Windmill** | Scripts become generated UIs, API endpoints and workflow steps; supports Python, TypeScript, PowerShell and other languages. | Cron schedules and a schedule builder; job runs are part of the platform. | Self-hosting uses a server, workers and PostgreSQL, commonly through Docker Compose; Windows workers are documented separately. Broad capability, with more deployment machinery than this personal desktop scope. [Scripts](https://www.windmill.dev/use-cases/scripts-content), [schedules](https://www.windmill.dev/docs/core_concepts/scheduling), [self-hosting](https://www.windmill.dev/docs/advanced/self_host). |
| **Rundeck** | Organizes reusable jobs and workflow steps with access policies. | Graphical/cron schedules, running-job views and step output. | Official Windows instructions install Java and run a WAR distribution. Suitable when jobs and permissions span a team or nodes; heavier setup for a small local script shelf. [Jobs](https://docs.rundeck.com/docs/manual/jobs/index.html), [scheduling](https://docs.rundeck.com/docs/manual/jobs/creating-jobs.html), [Windows install](https://docs.rundeck.com/docs/administration/install/windows.html). |
| **Windows Task Scheduler** | Native execution actions contain an executable, argument string and working directory. | Time, boot, logon, idle and event triggers. It is an operating-system scheduling facility. | Already a Windows component. A good choice for unattended OS-level triggers. The documented execution-action interface is not a generated per-script parameter form or artifact browser; scripts should manage their own output logging. [Overview](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page), [execution actions](https://learn.microsoft.com/en-us/windows/win32/taskschd/execaction). |

## Conclusions for Runloom Desk

The opportunity is a small local workbench that puts existing commands, their inputs, recent runs and output files in one desktop window. The product is not claiming a new category: script-server already covers much of the functional territory. The deliberate difference is the single-user desktop deployment and small runtime surface.

The first release therefore uses JSON manifests, generated parameter forms, searchable tasks, observable subprocess execution, SQLite history and simple schedules. Existing scripts can remain unchanged; a small optional JSON-lines protocol adds progress and artifact links. Only the image example needs an external Python library.

The tradeoff is explicit: the in-app scheduler requires the app to remain running. It does not replace Task Scheduler for execution after logout, while the app is closed, or after an unattended reboot. Multi-user access, remote execution, a plugin marketplace, embedded script editing, arbitrary cron syntax and distributed workflows are outside this release.

## Naming check

The working display name is **Runloom Desk**. Exact-phrase web searches on the review date did not reveal an exact product match; that is limited discovery evidence, not trademark or domain clearance.

The unqualified name **Runloom** is already in use: [robertsdotpm/runloom](https://github.com/robertsdotpm/runloom) is a Python coroutine project, [runloom/pier](https://github.com/runloom/pier) is a separate desktop project under the Runloom organization, and [TUC Now](https://www.tucnow.com/) lists a RunLoom workflow product. This project has no affiliation with those projects. Its internal `runloom` module is loaded from the extracted source directory; this release is not published to PyPI. Do not run `pip install runloom` to install this application.

Before a public product launch, choose and independently check the final repository, package and product names. The present source distribution deliberately makes no claim to an available account, domain or registered mark.

# Third-party software

Runloom Desk's own source is under the [MIT license](LICENSE). No competitor source or artwork is included. The following components retain their own terms:

| Component | Use | License / source |
| --- | --- | --- |
| CPython and standard library | Interpreter, Tk bindings, SQLite bindings and subprocess execution | [Python license](https://docs.python.org/3/license.html); separate source prerequisite or bundled Windows runtime |
| Tcl/Tk | Desktop widget toolkit provided with a suitable Python installation | [Tcl/Tk license terms](https://www.tcl-lang.org/software/tcltk/license.html) |
| SQLite | Embedded database used through Python's `sqlite3` module | [Public-domain dedication](https://www.sqlite.org/copyright.html) |
| Pillow 12.3.0 | Image resize example and generated demo image | [Pillow license](https://github.com/python-pillow/Pillow/blob/main/LICENSE); source dependency through `requirements.txt` or bundled Windows runtime |
| PyInstaller 6.20.0 | Windows build tool and executable bootloader | [Licensing and bundling exception](https://pyinstaller.org/en/stable/license.html); build dependency only |

The source ZIP does not bundle a Python interpreter or third-party wheels. The Windows folder build includes runtime components and collects license notices under `_internal/licenses`, including the installed Pillow distribution's notices for compiled libraries. Preserve that directory and any licenses distributed with Tcl/Tk runtime files when redistributing the complete folder. This table is attribution, not a substitute for the bundled license texts. Rebuilding against a different Python installation or wheel requires checking the resulting notice set again.

Product names in the research document belong to their respective owners. Their inclusion is comparative attribution, not endorsement or affiliation.

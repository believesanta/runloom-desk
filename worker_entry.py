"""Console entry point retained for observable bundled example processes."""
import sys

from runloom.examples import main

if __name__ == '__main__':
    # Frozen Python ignores PYTHONIOENCODING. The runner's wire protocol is UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())

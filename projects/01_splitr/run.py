import logging
import os
import sys

from splitr.app import create_app
from splitr.db import SchemaError

logging.basicConfig(level=logging.INFO)


def debug_enabled():
    """Debug mode (interactive debugger + auto-reload) is opt-in via SPLITR_DEBUG=1."""
    return os.environ.get("SPLITR_DEBUG", "").lower() in ("1", "true", "yes")


def main(argv):
    """Start the development server; returns the process exit code.

    ``argv[1]`` is an optional port (default 8080). A database the app cannot
    open (e.g. one from an older release) is reported as a one-line error and
    exit code 1 rather than a traceback.
    """
    port = int(argv[1]) if len(argv) > 1 else 8080
    try:
        app = create_app()
    except SchemaError as error:
        print("splitr: cannot start: %s" % error, file=sys.stderr)
        return 1
    app.run(host="127.0.0.1", port=port, debug=debug_enabled())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

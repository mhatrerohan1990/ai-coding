import logging
import os
import sys

from splitr.app import create_app

logging.basicConfig(level=logging.INFO)


def debug_enabled():
    """Debug mode (interactive debugger + auto-reload) is opt-in via SPLITR_DEBUG=1."""
    return os.environ.get("SPLITR_DEBUG", "").lower() in ("1", "true", "yes")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    create_app().run(host="127.0.0.1", port=port, debug=debug_enabled())

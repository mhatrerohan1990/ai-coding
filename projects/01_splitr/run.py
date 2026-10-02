import logging
import sys

from splitr.app import create_app

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    create_app().run(host="127.0.0.1", port=port, debug=True)

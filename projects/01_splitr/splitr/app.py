from flask import Flask

from . import controllers, db


def create_app(db_path="splitr.db"):
    """Application factory: build the Flask app and wire up the layers.

    Initialises the SQLite connection (see ``db.init``) pointing at ``db_path``,
    registers the controllers' blueprints and error handlers, and closes each
    thread's connection when its request ends.

    Args:
        db_path: Filesystem path of the SQLite database file.

    Returns:
        A configured ``Flask`` instance (used by ``run.py`` and the tests).
    """
    app = Flask(__name__)
    db.init(db_path)

    @app.teardown_appcontext
    def release_connection(exc):
        """Close this thread's database connection when the request ends."""
        db.close_conn()

    controllers.register(app)
    return app

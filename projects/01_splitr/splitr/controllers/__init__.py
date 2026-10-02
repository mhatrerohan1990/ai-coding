"""HTTP layer: Flask blueprints that parse requests, call services and shape JSON.

Controllers hold no business rules and no SQL.
"""

from . import expenses, groups, settlements, users
from .errors import register_error_handlers


def register(app):
    """Attach all blueprints and the error handlers to ``app``."""
    register_error_handlers(app)
    for module in (users, groups, expenses, settlements):
        app.register_blueprint(module.bp)

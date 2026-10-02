from flask import jsonify

from ..errors import Conflict, NotFound, ValidationError


def register_error_handlers(app):
    """Translate domain errors into JSON responses: 400 for invalid input, 404 for unknown ids, 409 for conflicts."""

    @app.errorhandler(ValidationError)
    def handle_validation_error(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(Conflict)
    def handle_conflict(e):
        return jsonify(error=str(e)), 409

    @app.errorhandler(NotFound)
    def handle_not_found(e):
        return jsonify(error=str(e)), 404

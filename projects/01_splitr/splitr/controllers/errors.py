from flask import jsonify

from ..errors import NotFound, ValidationError


def register_error_handlers(app):
    """Translate domain errors into JSON responses: 400 for invalid input, 404 for unknown ids."""

    @app.errorhandler(ValidationError)
    def handle_validation_error(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(NotFound)
    def handle_not_found(e):
        return jsonify(error=str(e)), 404

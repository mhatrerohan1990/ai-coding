import logging

from flask import jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

HTTP_ERROR_CODES = {
    400: "invalid_request",
    404: "not_found",
    405: "method_not_allowed",
}


class ApiError(Exception):
    status = 500
    code = "internal_error"

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class InvalidRequest(ApiError):
    status = 400
    code = "invalid_request"


class InvalidToken(ApiError):
    status = 401
    code = "invalid_token"


class Forbidden(ApiError):
    status = 403
    code = "forbidden"


class NotFound(ApiError):
    status = 404
    code = "not_found"


def error_response(code, message, status):
    return jsonify(error={"code": code, "message": message}), status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return error_response(err.code, err.message, err.status)

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        code = HTTP_ERROR_CODES.get(err.code, "http_error")
        return error_response(code, err.description, err.code)

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        logger.exception("unhandled error")
        return error_response("internal_error", "internal server error", 500)

from flask import Flask, jsonify


def create_app(db_path, jwt_secret, issuer):
    app = Flask(__name__)

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    return app

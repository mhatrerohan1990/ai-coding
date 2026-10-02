import logging
import os

from quota_gate.app import create_app

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    app = create_app(
        db_path=os.environ.get("QUOTA_GATE_DB", "./quota_gate.db"),
        jwt_secret=os.environ.get("QUOTA_GATE_JWT_SECRET", "dev-secret-change-me"),
        issuer=os.environ.get("QUOTA_GATE_ISSUER", "https://idp.example.test"),
    )
    port = int(os.environ.get("QUOTA_GATE_PORT", "8080"))
    app.run(host="127.0.0.1", port=port, threaded=True)

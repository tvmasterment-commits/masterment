import os
import secrets
from pathlib import Path
from flask import Flask
from dotenv import load_dotenv
from .db import init_db

BASE_DIR = Path(__file__).resolve().parent.parent

def create_app(test_config=None):
    load_dotenv(BASE_DIR / ".env")
    app = Flask(__name__, template_folder="templates", static_folder="static")
    production = os.getenv("APP_ENV", "development").lower() == "production"
    secret_key = os.getenv("FLASK_SECRET_KEY", "").strip()
    admin_username = os.getenv("ADMIN_USERNAME", "admin").strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "change-this-before-deploying")
    if production:
        if len(secret_key) < 32 or len(set(secret_key)) < 12 or secret_key == "replace-with-a-long-random-secret":
            raise RuntimeError("Production requires a FLASK_SECRET_KEY with at least 32 characters.")
        if not admin_username or admin_username.lower() == "admin" or admin_password == "change-this-before-deploying" or len(admin_password) < 16:
            raise RuntimeError("Production requires a unique ADMIN_USERNAME and ADMIN_PASSWORD of at least 16 characters.")
    app.config.update(
        SECRET_KEY=secret_key or secrets.token_urlsafe(48),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        MAX_CONTENT_LENGTH=16 * 1024,
        DATABASE_PATH=os.getenv("DATABASE_PATH", str(BASE_DIR / "instance" / "masterment.sqlite3")),
        KNOWLEDGE_PATH=str(BASE_DIR / "knowledge" / "business.json"),
        ADMIN_USERNAME=admin_username,
        ADMIN_PASSWORD=admin_password,
        CHAT_RATE_LIMIT=20,
        CHAT_RATE_WINDOW=60,
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    init_db(app.config["DATABASE_PATH"])
    from .routes import bp
    app.register_blueprint(bp)
    return app

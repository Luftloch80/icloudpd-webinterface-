import os

from flask import Flask

from app.auth_user import load_user
from app.config import Config
from app.extensions import db, login_manager


def create_app(config_class=Config) -> Flask:
    Config.ensure_dirs()

    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        secret_file = Config.CONFIG_DIR / "flask_secret.key"
        if secret_file.exists():
            app.config["SECRET_KEY"] = secret_file.read_text().strip()
        else:
            key = os.urandom(32).hex()
            secret_file.write_text(key)
            os.chmod(secret_file, 0o600)
            app.config["SECRET_KEY"] = key

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.user_loader(load_user)

    from app.routes import app_auth, apple_auth, dashboard, jobs, settings

    app.register_blueprint(app_auth.bp)
    app.register_blueprint(apple_auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(jobs.bp)

    with app.app_context():
        db.create_all()
        from app.db_migrate import sync_schema

        sync_schema(db)

    @app.context_processor
    def inject_admin_hint():
        from app.auth_user import _resolve_app_password

        show_hint = not Config.APP_PASSWORD and Config.APP_PASSWORD_FILE.exists()
        return {
            "admin_password_hint": _resolve_app_password() if show_hint else None,
            "admin_username": Config.APP_USERNAME,
        }

    return app

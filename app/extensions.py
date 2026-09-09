from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "app_auth.login"
login_manager.login_message = "Bitte melde dich an, um fortzufahren."
login_manager.login_message_category = "warning"

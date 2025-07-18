import random
import string
import os

from datetime import timedelta

class Config:
    """Base configuration class."""
    # Absolute path to the current directory
    basedir = os.path.abspath(os.path.dirname(__file__))

    # Upload folder paths
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    # Secret key for Flask (generated securely)
    SECRET_KEY = ''.join(random.choices(string.ascii_letters + string.digits, k=32))

    # MySQL Configuration
    MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.getenv('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
    MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'pos_beero')

    # Session timeout after 30 minutes of inactivity
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)

    @staticmethod
    def init_app(app):
        """Initialize the app with the configuration."""
        app.config.from_object(Config)
        # Ensure the upload folder exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

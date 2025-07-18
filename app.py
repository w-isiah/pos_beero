import os
from flask import Flask
from apps import create_app
from apps.config import Config

# Create the Flask app using the factory pattern
app = create_app(Config)

# Run the Flask application
if __name__ == "__main__":
    app.run(debug=app.config['DEBUG'])  # Use the debug flag from config

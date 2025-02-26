import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Debug print to verify DATABASE_URL
database_url = os.environ.get("DATABASE_URL")
if database_url:
    print(f"Database URL is configured: postgresql://<credentials>@{database_url.split('@')[-1]}")
else:
    print("Warning: DATABASE_URL is not set")

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

# configure the database, relative to the app instance folder
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable must be set")
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
# initialize the app with the extension, flask-sqlalchemy >= 3.0.x
db.init_app(app)

with app.app_context():
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401

    db.create_all()
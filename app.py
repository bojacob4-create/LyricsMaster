import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Database URL configuration with detailed error reporting
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    # Check for alternative PostgreSQL environment variables
    pg_vars = {
        'PGUSER': os.environ.get('PGUSER'),
        'PGPASSWORD': os.environ.get('PGPASSWORD'),
        'PGHOST': os.environ.get('PGHOST'),
        'PGPORT': os.environ.get('PGPORT'),
        'PGDATABASE': os.environ.get('PGDATABASE')
    }

    if all(pg_vars.values()):
        database_url = f"postgresql://{pg_vars['PGUSER']}:{pg_vars['PGPASSWORD']}@{pg_vars['PGHOST']}:{pg_vars['PGPORT']}/{pg_vars['PGDATABASE']}"
        print("Using constructed PostgreSQL URL from environment variables")
    else:
        error_msg = ("Database configuration is missing. Please ensure either DATABASE_URL "
                    "is set in your deployment environment variables/secrets.")
        print(error_msg)
        raise RuntimeError(error_msg)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

# configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
# initialize the app with the extension
db.init_app(app)

with app.app_context():
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401
    db.create_all()
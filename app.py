import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Database URL configuration with clear error handling
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    # Try constructing from individual credentials if available
    db_params = {
        'user': os.environ.get('PGUSER'),
        'password': os.environ.get('PGPASSWORD'),
        'host': os.environ.get('PGHOST'),
        'port': os.environ.get('PGPORT'),
        'database': os.environ.get('PGDATABASE')
    }

    if all(db_params.values()):
        database_url = f"postgresql://{db_params['user']}:{db_params['password']}@{db_params['host']}:{db_params['port']}/{db_params['database']}"
        print("Database URL constructed from individual credentials")
    else:
        missing_params = [k for k, v in db_params.items() if not v]
        raise RuntimeError(f"Database configuration missing. Either set DATABASE_URL or provide all of: {', '.join(missing_params)}")

print(f"Database URL configured: postgresql://<credentials>@{database_url.split('@')[-1] if '@' in database_url else '<error>'}")

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
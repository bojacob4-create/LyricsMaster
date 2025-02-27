import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

print("Starting database configuration...")

# First try to use individual PostgreSQL variables
pg_vars = {
    'PGUSER': os.environ.get('PGUSER'),
    'PGPASSWORD': os.environ.get('PGPASSWORD'),
    'PGHOST': os.environ.get('PGHOST'),
    'PGPORT': os.environ.get('PGPORT'),
    'PGDATABASE': os.environ.get('PGDATABASE')
}

print("Checking PostgreSQL environment variables...")
for key, value in pg_vars.items():
    if key != 'PGPASSWORD':  # Don't print the password
        print(f"{key}: {value}")
    else:
        print(f"{key}: {'*' * 8}")  # Print asterisks instead of actual password

if not all(pg_vars.values()):
    missing_params = [k for k, v in pg_vars.items() if not v]
    error_msg = (
        f"Missing required PostgreSQL variables: {', '.join(missing_params)}\n"
        "Please ensure all PostgreSQL variables are set in your deployment settings:\n"
        "- PGUSER: Your database username\n"
        "- PGPASSWORD: Your database password\n"
        "- PGHOST: Your database host\n"
        "- PGPORT: Your database port\n"
        "- PGDATABASE: Your database name"
    )
    print(error_msg)
    raise RuntimeError(error_msg)

# Construct database URL from individual variables
database_url = f"postgresql://{pg_vars['PGUSER']}:{pg_vars['PGPASSWORD']}@{pg_vars['PGHOST']}:{pg_vars['PGPORT']}/{pg_vars['PGDATABASE']}"
print("Successfully constructed database URL from environment variables")

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
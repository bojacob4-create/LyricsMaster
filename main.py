from app import app, db
from bot import main

if __name__ == "__main__":
    with app.app_context():
        # Import models here to ensure they're registered
        from models import Favorite
        db.create_all()
    main()
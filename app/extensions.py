from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()

# Configure CORS to accept requests from frontend
cors = CORS(
    resources={
        r"/*": {
            "origins": [
                "http://localhost:3000",  # Vite default dev server
                "http://localhost:5173",  # Vite alternative port
                "http://localhost:8005",  # Backend port (for testing)
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
                "https://uat-buv-flask-gwckc7brcbcndjf0.eastus-01.azurewebsites.net",  # UAT backend
                "https://www.host.com",  # Production frontend (update with actual URL)
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "Accept"],
            "supports_credentials": True,
            "max_age": 3600,  # Cache preflight requests for 1 hour
        }
    }
)
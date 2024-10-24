buv-prod-flask/
│
├── app/
│   ├── __init__.py             # Initializes the Flask app and connects to PostgreSQL
│   ├── routes.py               # Defines Flask API routes for chatbot interactions
│   ├── database.py             # PostgreSQL and PGVector setup (database handling)
│   ├── chatbot.py              # Chatbot logic, including interaction with Azure OpenAI and LangChain
│   ├── static/                 # Static files (CSS, JS, images)
│   ├── templates/              # HTML templates (for frontend rendering)
│   │   └── index.html          # Example frontend page
│   └── utils.py                # Utility functions (e.g., for formatting, error handling)
│
├── config.py                   # Configuration settings (PostgreSQL URI, Azure API keys, etc.)
├── manage.py                   # Main entry point for running the Flask app
├── requirements.txt            # List of Python dependencies to be installed via pip
├── .env                        # Environment variables (PostgreSQL URI, Azure API keys) – Not included in version control
├── .gitignore                  # Specifies files and directories to ignore in version control (e.g., .env, __pycache__)
├── README.md                   # Documentation for the project, including setup instructions

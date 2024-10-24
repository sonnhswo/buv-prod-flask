
## Setup Instructions

1. **Clone the repository:**
    ```sh
    git clone <repository-url>
    cd buv-prod-flask
    ```

2. **Create and activate a virtual environment:**
    ```sh
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. **Install dependencies:**
    ```sh
    pip install -r requirements.txt
    ```

4. **Set up environment variables:**
    - Create a `.env` file in the root directory with the necessary environment variables (e.g., PostgreSQL URI, Azure API keys).

5. **Run the application:**
    ```sh
    python manage.py run
    ```

## Project Components

- **`app/__init__.py`**: Initializes the Flask app and connects to PostgreSQL.
- **`app/routes.py`**: Defines Flask API routes for chatbot interactions.
- **`app/database.py`**: PostgreSQL and PGVector setup (database handling).
- **`app/chatbot.py`**: Chatbot logic, including interaction with Azure OpenAI and LangChain.
- **`app/static/`**: Static files (CSS, JS, images).
- **`app/templates/`**: HTML templates (for frontend rendering).
- **`app/utils.py`**: Utility functions (e.g., for formatting, error handling).
- **`config.py`**: Configuration settings (PostgreSQL URI, Azure API keys, etc.).
- **`manage.py`**: Main entry point for running the Flask app.
- **`requirements.txt`**: List of Python dependencies to be installed via pip.
- **`.env`**: Environment variables (PostgreSQL URI, Azure API keys) – Not included in version control.
- **`.gitignore`**: Specifies files and directories to ignore in version control (e.g., .env, __pycache__).
- **`README.md`**: Documentation for the project, including setup instructions.
- **`venv/`**: Virtual environment directory.

## License

This project is licensed under the MIT License.
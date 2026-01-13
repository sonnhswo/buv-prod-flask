from app import create_app
from flask_cors import CORS

app = create_app()
CORS(app, resources={r"*": {"origins": "*"}})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8005, debug=False)

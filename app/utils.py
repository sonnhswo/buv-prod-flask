def format_response(response):
    # Utility function to format chatbot responses (e.g., for pretty-printing)
    return response.strip()

def handle_error(error):
    # Utility function to handle errors
    return {"error": str(error)}

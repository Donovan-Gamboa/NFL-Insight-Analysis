import os
import requests
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import json
import time # Import the time module for handling delays and retries

# Load environment variables from a .env file for secure key management.
load_dotenv()

# Initialize the Flask application.
# `static_folder='public'` tells Flask to serve files from the 'public' directory
# when a static path is requested (e.g., /dashboard_data.json).
app = Flask(__name__, static_folder='public')

# Retrieve the Gemini API key from the server's environment variables.
# This is a critical security measure to avoid exposing the key on the client-side.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Helper function to find the next game ---
# Note: This function is defined but not currently used in this server script.
# It's kept for potential future server-side logic that might need to identify the next game.
def find_next_game(schedule):
    from datetime import datetime, timezone
    future_games = [g for g in schedule if g.get('date') and datetime.fromisoformat(g['date'].replace('Z', '+00:00')) > datetime.now(timezone.utc)]
    return sorted(future_games, key=lambda x: x['date'])[0] if future_games else None

# --- Flask Routes ---

@app.route('/')
def index():
    """
    Serves the main dashboard HTML file when a user visits the root URL.
    It looks for 'bills_dashboard.html' in the same directory as the server script.
    """
    return send_from_directory('.', 'bills_dashboard.html')

@app.route('/<path:path>')
def serve_static(path):
    """
    Serves static files requested by the client, such as dashboard_data.json.
    Flask automatically looks for these files in the `static_folder` defined above ('public').
    """
    return send_from_directory(app.static_folder, path)

@app.route('/generate-insights', methods=['POST'])
def generate_insights():
    """
    Acts as a secure proxy for the Gemini API.
    It receives the request from the front-end, adds the secret API key,
    forwards it to Google's API, and returns the response.
    This prevents the API key from ever being exposed in the browser.
    """
    if not GEMINI_API_KEY:
        # Fails gracefully if the server itself is missing the API key.
        return jsonify({"error": "Gemini API key not configured on the server."}), 500

    # Implements a robust retry mechanism with exponential backoff.
    # This automatically handles temporary issues like API rate limiting (HTTP 429).
    MAX_RETRIES = 4 # Total attempts: 1 initial + 3 retries
    for attempt in range(MAX_RETRIES):
        try:
            # The official Google Generative Language API endpoint.
            # Using a powerful model like gemini-2.5-pro for high-quality analysis.
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={GEMINI_API_KEY}"
            
            # The JSON payload (containing the prompt and data) from the original
            # front-end request is passed through directly to the Gemini API.
            payload = request.json

            # Make the POST request to the Gemini API.
            response = requests.post(api_url, json=payload, headers={'Content-Type': 'application/json'})

            # If the API responds with a 429 status code, it means we've been rate-limited.
            # We raise an exception to trigger the retry logic in the 'except' block.
            if response.status_code == 429:
                print(f"  > Rate limit hit. Attempt {attempt + 1} of {MAX_RETRIES}.")
                response.raise_for_status() # This converts the HTTP error into a Python exception.
            
            # If the response was successful (e.g., 200 OK) or had a different error,
            # we immediately return the result to the front-end without retrying.
            return response.json(), response.status_code

        except requests.exceptions.RequestException as e:
            # This block catches connection errors or the 429 status code from above.
            
            # If this isn't the last attempt, wait before retrying.
            if attempt < MAX_RETRIES - 1:
                # Exponential backoff: wait 1s, then 2s, then 4s, etc.
                delay = 2 ** attempt
                print(f"  > Waiting for {delay} second(s) before retrying...")
                time.sleep(delay)
            else:
                # If all retries have failed, log the error and return a 500 status to the client.
                print(f"Error calling Gemini API after {MAX_RETRIES} attempts: {e}")
                return jsonify({"error": f"Failed to call Gemini API: {e}"}), 500
    
    # This line should theoretically not be reached but acts as a final safeguard.
    return jsonify({"error": "An unexpected error occurred in the retry loop."}), 500

# This standard Python construct ensures that the Flask development server runs
# only when the script is executed directly (not when imported as a module).
if __name__ == '__main__':
    app.run(debug=True, port=5001)

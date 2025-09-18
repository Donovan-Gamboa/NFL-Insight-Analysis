import os
import requests
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import json
import time # Import the time module for handling delays

load_dotenv()

app = Flask(__name__, static_folder='public')
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Helper function to find the next game ---
def find_next_game(schedule):
    from datetime import datetime, timezone
    future_games = [g for g in schedule if g.get('date') and datetime.fromisoformat(g['date'].replace('Z', '+00:00')) > datetime.now(timezone.utc)]
    return sorted(future_games, key=lambda x: x['date'])[0] if future_games else None

@app.route('/')
def index():
    # Serve the main HTML file from the project's root directory ('.')
    return send_from_directory('.', 'bills_dashboard.html')

@app.route('/<path:path>')
def serve_static(path):
    # This route will still handle serving dashboard_data.json from the 'public' folder.
    return send_from_directory(app.static_folder, path)

@app.route('/generate-insights', methods=['POST'])
def generate_insights():
    if not GEMINI_API_KEY:
        return jsonify({"error": "Gemini API key not configured on the server."}), 500

    # Implement retry logic with exponential backoff
    MAX_RETRIES = 4 # e.g., wait 1, 2, 4, 8 seconds
    for attempt in range(MAX_RETRIES):
        try:
            # **FIX**: Swapped the model to gemini-2.5-pro for higher quality analysis.
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={GEMINI_API_KEY}"
            
            # The original request's JSON body is passed through
            payload = request.json

            response = requests.post(api_url, json=payload, headers={'Content-Type': 'application/json'})

            # If the request was rate-limited, raise an exception to trigger the retry
            if response.status_code == 429:
                print(f"  > Rate limit hit. Attempt {attempt + 1} of {MAX_RETRIES}.")
                response.raise_for_status() 
            
            # If the response was successful or a non-429 error, return it immediately
            return response.json(), response.status_code

        except requests.exceptions.RequestException as e:
            # Check if this is the last attempt
            if attempt < MAX_RETRIES - 1:
                delay = 2 ** attempt
                print(f"  > Waiting for {delay} second(s) before retrying...")
                time.sleep(delay)
            else:
                print(f"Error calling Gemini API after {MAX_RETRIES} attempts: {e}")
                return jsonify({"error": f"Failed to call Gemini API: {e}"}), 500
    
    return jsonify({"error": "An unexpected error occurred in the retry loop."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)


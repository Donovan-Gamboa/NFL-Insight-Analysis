Buffalo Bills AI Dashboard
This project provides a web-based dashboard for Buffalo Bills stats, odds, and AI-powered analysis using Google Gemini.

Features
Live Data Pipeline: Pulls season stats, schedules, injury reports, and live betting odds.

Player Prop Explorer: Interactively explore player stats and compare them against current betting lines.

Secure Backend Proxy: Protects your Gemini API key by handling API calls on the server-side.

Enhanced AI Analysis: A significantly improved prompting strategy provides Gemini with better context (stats, trends, odds) to generate high-quality game analysis.

Setup and Installation
Follow these steps to get your dashboard running locally.

1. Clone the Repository
If you're working with this project in a Git repository, clone it to your local machine.

2. Install Python Dependencies
Make sure you have Python 3 installed. It's recommended to use a virtual environment.

# Create and activate a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

# Install the required packages
pip install -r requirements.txt

3. Configure API Keys
Your API keys must be kept secret. This project uses a .env file to manage them securely.

Make a copy of the example file:

cp .env.example .env

Open the new .env file in a text editor.

Paste your API keys from The Odds API and Google AI Studio.

Save and close the file. The .gitignore file is already configured to prevent this file from ever being uploaded to GitHub.

4. Run the Data Pipeline
This script fetches all the necessary data and saves it to a local JSON file that the dashboard will use.

python data_pipeline.py

You should see output in your terminal indicating success. This will create a public/dashboard_data.json file. You only need to run this when you want to refresh the data.

5. Start the Web Server
The Flask web server will serve your dashboard and handle the secure calls to the Gemini API.

python server.py

Your terminal will show that the server is running, usually at http://127.0.0.1:5001.

6. View Your Dashboard
Open your web browser and navigate to the address from the previous step:

http://127.0.0.1:5001

You should now see your fully functional, secure, and enhanced Bills AI Dashboard!
# NFL Insight Dashboard (Buffalo Bills Edition) 🏈

A web-based dashboard that combines a **live data pipeline**, **interactive stats explorer**, and **Google Gemini analysis** to deliver smart, data-driven insights for the Buffalo Bills.

![NFL Insight Dashboard Screenshot](assets/dashboard_screenshot.png)


---

## 🚀 Key Features

-   **Automated Data Pipeline**: A Python script that fetches and processes data from multiple sources, including player stats, team rankings, schedules, injury reports, and live betting odds.
-   **Interactive Player Explorer**: A collapsible UI that lets you compare historical player performance (current and previous season) against live betting lines.
-   **Secure AI Analysis**: A Flask backend acts as a secure proxy, protecting your Google Gemini API key. It also features a robust retry mechanism with exponential backoff to handle API rate limits gracefully.
-   **Advanced AI Prompting**: The system sends a rich, structured data packet—including opponent weaknesses, key player matchups, and critical injury impacts—to Gemini for a truly expert-level game breakdown.
-   **Dynamic Frontend**: A vanilla JavaScript and Tailwind CSS interface that is lightweight, responsive, and easy to modify.

---

## ⚙️ How It Works

The project is split into three main components that work together:

1.  **Data Pipeline (`data_pipeline.py`)**: This script is the engine of the dashboard. It connects to multiple external APIs to gather all necessary information:
    * **nflverse**: For granular play-by-play data from the current and previous seasons.
    * **ESPN API**: For team schedules and detailed injury reports.
    * **The Odds API**: For live game lines and player prop betting odds.
    The script then cleans, normalizes, and aggregates this data into a single `public/dashboard_data.json` file.

2.  **Backend Server (`server.py`)**: A lightweight Flask server performs two critical functions:
    * It serves the main `bills_dashboard.html` and the static `dashboard_data.json` file to the user's browser.
    * It provides a secure `/generate-insights` endpoint that receives requests from the frontend, adds the secret `GEMINI_API_KEY` from the server environment, and forwards the request to the Google Gemini API. **This prevents your API key from ever being exposed publicly.**

3.  **Frontend (`bills_dashboard.html`)**: This single file contains the entire user interface. It uses:
    * **HTML** for the structure.
    * **Tailwind CSS** for modern, responsive styling.
    * **Vanilla JavaScript** to fetch the `dashboard_data.json`, dynamically render all the components (matchup card, player explorer, etc.), and handle user interactions like clicking the "Analyze" button.

---

## 🛠️ Tech Stack

-   **Backend**: Python, Flask
-   **Data Processing**: Pandas
-   **Frontend**: HTML, Tailwind CSS, Vanilla JavaScript
-   **AI**: Google Gemini API
-   **Data Sources**: nflverse, ESPN API, The Odds API

---

## 📋 Setup & Installation

Follow these steps to run the dashboard locally.

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/NFL-Insight-Analysis.git
cd NFL-Insight-Analysis
```

### 2. Install Python Dependencies
Make sure you have Python 3 installed. A virtual environment is recommended:
```bash
python -m venv venv
source venv/bin/activate   # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure API Keys
You'll need keys from The Odds API and Google AI Studio.

Copy the example environment file:
```bash
cp .env.example .env
```
Edit the new `.env` file and add your secret keys.

The `.gitignore` file is already configured to exclude `.env`, so your keys will remain private.

### 4. Run the Data Pipeline
This script fetches all the data and caches it in a local JSON file.
```bash
python data_pipeline.py
```
This creates `public/dashboard_data.json`. You only need to rerun this command when you want to refresh the data (e.g., for a new week's game).

### 5. Start the Web Server
This starts the Flask backend.
```bash
python server.py
```
The server will start, typically at http://127.0.0.1:5001.

### 6. Open the Dashboard
Visit the address shown in your terminal to explore your fully functional dashboard!

Tip: To deploy this project publicly, you can use a service like Render or Heroku. Configure the environment variables (`ODDS_API_KEY`, `GEMINI_API_KEY`) in your hosting provider's dashboard and set the startup command to run the Flask app.
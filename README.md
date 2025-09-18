# NFL-Insight-Analysis (Bills)

A web-based dashboard that combines **live stats**, **betting odds**, and **Google Gemini analysis** to deliver smart, up-to-date insights on the Buffalo Bills.

## 🚀 Features
- **Live Data Pipeline** – Pulls season stats, schedules, injury reports, and live betting odds.  
- **Player Prop Explorer** – Compare player stats to current betting lines with an interactive UI.  
- **Secure Backend Proxy** – Keeps your Gemini API key safe by routing calls through a Flask server.  
- **Enhanced AI Analysis** – Optimized prompting supplies Gemini with rich context (stats, trends, odds) for sharp game breakdowns.

## 🛠️ Setup & Installation
Follow these steps to run the dashboard locally.

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/NFL-Insight-Analysis.git
cd NFL-Insight-Analysis
```

### 2. Install Python Dependencies
Make sure you have **Python 3** installed. A virtual environment is recommended:
```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure API Keys
1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and add your keys for **The Odds API** and **Google AI Studio**.  
3. The `.gitignore` already excludes `.env` so your keys stay private.

### 4. Run the Data Pipeline
Fetch and cache all required data:
```bash
python data_pipeline.py
```
This creates `public/dashboard_data.json`. Rerun only when you need fresh data.

### 5. Start the Web Server
```bash
python server.py
```
The server typically starts at **http://127.0.0.1:5001**.

### 6. Open the Dashboard
Visit the address shown in your terminal to explore your fully functional **NFL-Insight-Analysis Dashboard**.

---

**Tip:** To deploy publicly, configure your hosting environment (e.g., Render, Heroku, or a VPS) with the same `.env` settings and run the Flask app as you would any production Python service.

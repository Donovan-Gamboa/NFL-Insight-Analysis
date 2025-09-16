import requests
import json
import pandas as pd
import gzip
import shutil
from datetime import datetime
import os

# --- Configuration ---
BILLS_TEAM_ID = "2"
BILLS_TEAM_ABBREVIATION = "BUF"

# --- Smarter nflfastR Data Fetcher ---
def get_current_nfl_season():
    """Determines the current NFL season year based on the current date."""
    now = datetime.now()
    return now.year if now.month >= 3 else now.year - 1

def fetch_and_process_nflfastr_data(team_abbr):
    """
    Intelligently fetches the most up-to-date nflfastR data by targeting
    the main "live" file for the current season.
    """
    current_season = get_current_nfl_season()
    pbp_df = None
    data_season_used = None

    # --- NEW, SIMPLIFIED LOGIC ---
    # 1. Try to get the main file for the CURRENT season.
    print(f"\n--> Attempting to fetch LIVE data for {current_season} season...")
    live_season_url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{current_season}.csv.gz"
    
    try:
        pbp_df = pd.read_csv(live_season_url, compression='gzip', low_memory=False)
        data_season_used = current_season
        print(f"[OK] Successfully loaded LIVE data for the {current_season} season.")
    except Exception:
        # 2. If it fails, fall back to the LAST completed season.
        last_season = current_season - 1
        print(f"\n[INFO] No live data found for {current_season}. Falling back to last completed season: {last_season}.")
        fallback_url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{last_season}.csv.gz"
        try:
            pbp_df = pd.read_csv(fallback_url, compression='gzip', low_memory=False)
            data_season_used = last_season
            print(f"[OK] Successfully loaded complete data for the {last_season} season.")
        except Exception as e:
            print(f"[ERROR] Could not download fallback data for {last_season}. Reason: {e}")
            return None
    
    # If we don't have a DataFrame by now, something went wrong.
    if pbp_df is None:
        return None

    # --- Process the DataFrame ---
    print(f"\n--> Processing {data_season_used} nflfastR data...")
    try:
        team_games_df = pbp_df[(pbp_df['home_team'] == team_abbr) | (pbp_df['away_team'] == team_abbr)]
        print(f"  > Found {team_games_df['game_id'].nunique()} games for {team_abbr}.")
        
        stat_configs = {
            'passer': {'yards': 'passing_yards', 'tds': 'pass_touchdown'},
            'rusher': {'yards': 'rushing_yards', 'tds': 'rush_touchdown'},
            'receiver': {'yards': 'receiving_yards', 'tds': 'pass_touchdown'}
        }
        
        game_logs = {}
        for role, stats in stat_configs.items():
            player_col = f'{role}_player_name'
            df_role = team_games_df[(team_games_df[player_col].notna()) & (team_games_df['posteam'] == team_abbr)]
            
            agg_stats = df_role.groupby(['week', player_col]).agg(
                **{f'{role}_yards': (stats['yards'], 'sum')},
                **{f'{role}_tds': (stats['tds'], 'sum')}
            ).reset_index()

            for _, row in agg_stats.iterrows():
                player_name, week = row[player_col], row['week']
                game_logs.setdefault(player_name, {}).setdefault(week, {'week': week})
                game_logs[player_name][week].update({k: int(v) for k, v in row.items() if k not in [player_col, 'week']})

        print("[OK] nflfastR data processed successfully.")
        return {"player_game_logs": game_logs, "data_season": int(data_season_used)}
    except Exception as e:
        print(f"[ERROR] An error occurred while processing the nflfastR data. Reason: {e}")
        return None

# --- ESPN Data Fetcher (Unchanged) ---
def fetch_espn_data(team_id):
    print("\n--> Fetching data from ESPN API...")
    schedule_url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/schedule"
    injuries_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/teams/{team_id}/injuries"
    espn_data = {"schedule": [], "injuries": []}
    try:
        schedule_response = requests.get(schedule_url); schedule_response.raise_for_status(); schedule_json = schedule_response.json()
        for event in schedule_json.get("events", []):
            week_data = event.get("week", {}); opponent = next((c.get("team") for c in event.get("competitions", [])[0].get("competitors", []) if c.get("id") != team_id), None)
            espn_data["schedule"].append({"week": week_data.get("number"), "date": event.get("date"), "opponent_name": opponent.get("displayName") if opponent else "TBD", "opponent_logo": opponent.get("logo") if opponent else ""})
        injury_response = requests.get(injuries_url); injury_response.raise_for_status(); injury_json = injury_response.json()
        for item in injury_json.get("items", []):
            player = item.get("athlete", {}); status = item.get("type", {})
            if player.get("displayName"): espn_data["injuries"].append({"player_name": player.get("displayName"), "position": player.get("position", {}).get("abbreviation"), "status": status.get("name"), "detail": status.get("detail")})
        print("[OK] ESPN data fetched successfully.")
        return espn_data
    except requests.exceptions.RequestException as e: print(f"[ERROR] Could not fetch data from ESPN API. Reason: {e}"); return None
    except json.JSONDecodeError: print("[ERROR] Could not parse the JSON response from ESPN."); return None

# --- Odds API Fetcher (Placeholder) ---
def fetch_odds_data():
    print("\n--> (Placeholder) Fetching data from The Odds API...")
    print("[OK] Odds data fetched.")
    return {"point_spread": -7, "total": 48.5}

# --- Main Execution ---
if __name__ == "__main__":
    print("--- Starting Bills AI Dashboard Data Pipeline ---")
    
    nfl_stats_data = fetch_and_process_nflfastr_data(BILLS_TEAM_ABBREVIATION)
    
    if not nfl_stats_data:
        print("\n--- [HALT] Pipeline stopped due to nflfastR data failure. ---")
    else:
        espn_data = fetch_espn_data(BILLS_TEAM_ID)
        odds_data = fetch_odds_data()
        
        if espn_data and odds_data:
            final_dashboard_data = {
                "last_updated": datetime.now().isoformat(),
                "espn_data": espn_data,
                "nfl_stats": nfl_stats_data,
                "odds": odds_data
            }
            
            output_filename = "dashboard_data.json"
            with open(output_filename, 'w') as f:
                json.dump(final_dashboard_data, f, indent=2)
                
            print(f"\n--- [SUCCESS] Pipeline complete. Combined data for season {nfl_stats_data['data_season']} saved to {output_filename} ---")
        else:
            print("\n--- [FAIL] Pipeline incomplete. ESPN or Odds data source failed. ---")


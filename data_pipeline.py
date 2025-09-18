import requests
import json
import pandas as pd
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
import time

# --- Configuration ---
load_dotenv() 

BILLS_TEAM_ID = "2"
BILLS_TEAM_ABBREVIATION = "BUF"
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
PIPELINE_SUCCESS = True

# --- Helper Functions ---
PLAYER_NAME_VARIANTS = {
    "jallen": "joshallen", "jaallen": "joshallen", "kcoleman": "keoncoleman",
    "jcook": "jamescook", "dkincaid": "daltonkincaid", "dknox": "dawsonknox",
    "kshakir": "khalilshakir", "rdavis": "raydavis", "jpalmer": "joshuapalmer"
}
# A list of market groups to query sequentially for robustness
MARKET_GROUPS = [
    # Standard team markets
    "h2h",
    "spreads",
    "totals",

    # Passing
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_attempts",
    "player_pass_completions",
    "player_pass_interceptions",
    "player_pass_longest_completion",

    # Rushing
    "player_rush_yds",
    "player_rush_attempts",
    "player_rush_longest",

    # Receiving
    "player_reception_yds",
    "player_receptions",
    "player_reception_longest",

    # Touchdowns / Scoring
    "player_1st_td",
    "player_anytime_td"
]

def get_nfl_season_years():
    now = datetime.now()
    # NFL season starts in September, but we consider the new season to start around March for data purposes
    current_season = now.year if now.month >= 3 else now.year - 1
    return current_season, current_season - 1

def normalize_player_name(name):
    lookup_name = name.replace(".", "").replace(" ", "").lower()
    return PLAYER_NAME_VARIANTS.get(lookup_name, lookup_name)

def get_detailed_injuries(injury_list_url):
    """
    Helper function to fetch detailed injury data by following API references,
    as the initial endpoint only provides links to the actual data.
    """
    detailed_injuries = []
    try:
        injury_list_response = requests.get(injury_list_url).json()
        for item_ref in injury_list_response.get("items", []):
            time.sleep(0.1) # Small delay to be respectful to the API
            try:
                # 1. Fetch the specific injury details from its reference URL
                injury_detail_response = requests.get(item_ref['$ref']).json()
                
                # 2. Fetch the athlete details from its own separate reference URL
                athlete_ref_url = injury_detail_response.get("athlete", {}).get("$ref")
                if not athlete_ref_url:
                    continue
                
                time.sleep(0.1)
                athlete_detail_response = requests.get(athlete_ref_url).json()

                # 3. Extract all the required data points
                player_name = athlete_detail_response.get("displayName")
                position = athlete_detail_response.get("position", {}).get("abbreviation")
                status = injury_detail_response.get("status")
                detail = injury_detail_response.get("shortComment")

                if player_name:
                    detailed_injuries.append({
                        "player_name": player_name,
                        "position": position,
                        "status": status,
                        "detail": detail
                    })
            except Exception as e_inner:
                print(f"  > [WARN] Could not process individual injury ref {item_ref.get('$ref')}: {e_inner}")
        return detailed_injuries
    except Exception as e_outer:
        print(f"  > [ERROR] Could not fetch initial injury list from {injury_list_url}: {e_outer}")
        return [] # Return an empty list on outer failure

# --- Expert-Level Data Calculation ---
def calculate_team_rankings(season_df, season_year):
    """Calculates offensive and defensive yardage rankings for all teams from a full season pbp dataframe."""
    print(f"\n--> Calculating league-wide team rankings for {season_year}...")
    if season_df is None or season_df.empty:
        print(f"[WARN] Cannot calculate team rankings for {season_year} without season data.")
        return {}
    
    # Calculate offensive stats per game
    off_stats = season_df.groupby(['game_id', 'posteam']).agg(
        off_yards=('yards_gained', 'sum'),
        pass_yards=('passing_yards', 'sum'),
        rush_yards=('rushing_yards', 'sum')
    ).reset_index()
    
    # Calculate average offensive stats per team
    team_off_avg = off_stats.groupby('posteam').agg(
        avg_off_yards=('off_yards', 'mean'),
        avg_pass_yards=('pass_yards', 'mean'),
        avg_rush_yards=('rush_yards', 'mean')
    ).reset_index()

    # Calculate defensive stats per game
    def_stats = season_df.groupby(['game_id', 'defteam']).agg(
        def_yards=('yards_gained', 'sum'),
        def_pass_yards=('passing_yards', 'sum'),
        def_rush_yards=('rushing_yards', 'sum')
    ).reset_index()

    # Calculate average defensive stats per team
    team_def_avg = def_stats.groupby('defteam').agg(
        avg_def_yards=('def_yards', 'mean'),
        avg_def_pass_yards=('def_pass_yards', 'mean'),
        avg_def_rush_yards=('def_rush_yards', 'mean')
    ).reset_index()

    # Merge offensive and defensive stats
    team_stats = pd.merge(team_off_avg, team_def_avg, left_on='posteam', right_on='defteam', how='outer')
    team_stats = team_stats.drop(columns=['defteam'])
    team_stats.rename(columns={'posteam': 'team'}, inplace=True)
    team_stats = team_stats.fillna(0)
    
    # Calculate ranks (ascending=False means higher is better, ascending=True means lower is better)
    team_stats['rank_offense_yards'] = team_stats['avg_off_yards'].rank(method='min', ascending=False).astype(int)
    team_stats['rank_pass_offense_yards'] = team_stats['avg_pass_yards'].rank(method='min', ascending=False).astype(int)
    team_stats['rank_rush_offense_yards'] = team_stats['avg_rush_yards'].rank(method='min', ascending=False).astype(int)
    team_stats['rank_defense_yards'] = team_stats['avg_def_yards'].rank(method='min', ascending=True).astype(int)
    team_stats['rank_pass_defense_yards'] = team_stats['avg_def_pass_yards'].rank(method='min', ascending=True).astype(int)
    team_stats['rank_rush_defense_yards'] = team_stats['avg_def_rush_yards'].rank(method='min', ascending=True).astype(int)
    
    rankings = team_stats.set_index('team').to_dict('index')
    print(f"[OK] Team rankings for {season_year} calculated successfully.")
    return rankings

# --- Core Data Fetching Logic (Updated) ---
def fetch_and_process_season_data(season, team_abbr, for_rankings=False):
    global PIPELINE_SUCCESS
    print_identifier = "Entire League" if for_rankings else team_abbr
    print(f"\n--> Fetching nflfastR data for {print_identifier} ({season} season)...")
    try:
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz"
        pbp_df = pd.read_csv(url, compression='gzip', low_memory=False)
        print(f"[OK] Loaded data for {season}.")
        
        if for_rankings:
            return pbp_df

        team_games_df = pbp_df[(pbp_df['home_team'] == team_abbr) | (pbp_df['away_team'] == team_abbr)]
        if team_games_df.empty:
            print(f"  > No games found for {team_abbr} in {season}.")
            return {"season": season, "player_game_logs": {}}
        print(f"  > Found {team_games_df['game_id'].nunique()} games for {team_abbr}.")
        
        stat_configs = {
            'passer': {'yards': 'passing_yards', 'tds': 'pass_touchdown', 'attempts': 'pass_attempt', 'completions': 'complete_pass'},
            'rusher': {'yards': 'rushing_yards', 'tds': 'rush_touchdown', 'attempts': 'rush_attempt'},
            'receiver': {'yards': 'receiving_yards', 'tds': 'pass_touchdown', 'receptions': 'complete_pass'}
        }
        game_logs = {}
        for role, stats in stat_configs.items():
            player_col, df_role = f'{role}_player_name', team_games_df[(team_games_df[f'{role}_player_name'].notna()) & (team_games_df['posteam'] == team_abbr)]
            agg_dict = {f'{role}_{stat}': (col, 'sum') for stat, col in stats.items()}
            agg_stats = df_role.groupby(['week', player_col]).agg(**agg_dict).reset_index()
            for _, row in agg_stats.iterrows():
                player_name, week, norm_name = row[player_col], row['week'], normalize_player_name(row[player_col])
                game_logs.setdefault(norm_name, {}).setdefault(week, {'week': week, 'display_name': player_name})
                game_logs[norm_name][week].update({k: int(v) for k, v in row.items() if k not in [player_col, 'week']})
                if role in ['rusher', 'receiver'] and row.get(f'{role}_tds', 0) > 0:
                    game_logs[norm_name][week][f'{role}_anytime_td'] = 1
        print(f"[OK] nflfastR data for {team_abbr} ({season}) processed successfully.")
        return {"season": season, "player_game_logs": game_logs}
    except Exception as e:
        print(f"[ERROR] processing nflfastR data for {season} ({team_abbr}): {e}")
        PIPELINE_SUCCESS = False
        return None

def fetch_espn_data(team_id):
    global PIPELINE_SUCCESS
    print("\n--> Fetching ESPN data...")
    try:
        teams_url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
        teams_json = requests.get(teams_url).json()
        team_info_map = {
            team['team']['id']: {
                'logo': team['team']['logos'][0]['href'],
                'abbr': team['team']['abbreviation']
            } for league in teams_json['sports'][0]['leagues'] for team in league['teams']
        }

        schedule_url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/schedule"
        schedule_json = requests.get(schedule_url).json()
        espn_data = {"schedule": [], "injuries": [], "opponent_injuries": []}

        for event in schedule_json.get("events", []):
            comp = event["competitions"][0]
            opponent = next((c for c in comp["competitors"] if c["id"] != team_id), {})
            opp_id = opponent.get('id')
            espn_data["schedule"].append({
                "week": event["week"]["number"], 
                "date": event["date"], 
                "opponent_name": opponent.get('team',{}).get("displayName", "TBD"), 
                "opponent_logo": team_info_map.get(opp_id, {}).get('logo'),
                "opponent_id": opp_id,
                "opponent_abbr": team_info_map.get(opp_id, {}).get('abbr')
            })
        
        # --- MODIFICATION: Use the new helper to get detailed injury data ---
        print("  > Fetching Bills injuries...")
        bills_injuries_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/teams/{team_id}/injuries"
        espn_data["injuries"] = get_detailed_injuries(bills_injuries_url)
        # --- END MODIFICATION ---

        future_games = [g for g in espn_data['schedule'] if g.get('date') and datetime.fromisoformat(g['date'].replace('Z', '+00:00')) > datetime.now(timezone.utc)]
        next_game = sorted(future_games, key=lambda x: x['date'])[0] if future_games else None

        if next_game and next_game.get('opponent_id'):
            # --- MODIFICATION: Use the new helper for opponent injuries too ---
            print(f"  > Next opponent is {next_game['opponent_name']}. Fetching their injuries...")
            opp_injuries_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/teams/{next_game['opponent_id']}/injuries"
            espn_data["opponent_injuries"] = get_detailed_injuries(opp_injuries_url)
            # --- END MODIFICATION ---
        
        print("[OK] ESPN data fetched.")
        return espn_data
    except Exception as e:
        print(f"[ERROR] fetching ESPN data: {e}")
        PIPELINE_SUCCESS = False
        return None

def fetch_all_odds_data(api_key, next_game):
    """Fetches odds by looping through market groups for robustness."""
    global PIPELINE_SUCCESS
    print("\n--> Fetching LIVE odds from The Odds API...")
    if not api_key:
        print("[WARN] Odds API key not found. Skipping odds fetch.")
        return {"game_odds": {}, "player_props": {}}
    if not next_game:
        print("[WARN] No next game found. Skipping odds fetch.")
        return {"game_odds": {}, "player_props": {}}

    SPORT = 'americanfootball_nfl'
    try:
        events_url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events?apiKey={api_key}"
        events_response = requests.get(events_url).json()

        if not isinstance(events_response, list):
            print(f"[ERROR] Odds API returned an unexpected response: {events_response}")
            PIPELINE_SUCCESS = False; return {}

        home_team, away_team = "Buffalo Bills", next_game["opponent_name"]
        event_id = next((e['id'] for e in events_response if home_team in e['home_team'] and away_team in e['away_team']), None)
        
        if not event_id:
            print(f"[WARN] Could not find Event ID for the next game against {away_team}."); return {}
        print(f"  > Found Event ID for next game: {event_id}")

        game_odds, player_props = {}, {}
        
        for markets in MARKET_GROUPS:
            print(f"  > Fetching markets: {markets}...")
            time.sleep(1) # Be respectful of API rate limits
            
            odds_url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds?apiKey={api_key}&regions=us&markets={markets}"
            odds_response = requests.get(odds_url).json()
            bookmakers = odds_response.get('bookmakers', [])

            if not bookmakers: # Fallback to all regions if US bookmakers are not found
                print("    - No US bookmakers found, trying all regions...")
                odds_url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds?apiKey={api_key}&markets={markets}"
                odds_response = requests.get(odds_url).json()
                bookmakers = odds_response.get('bookmakers', [])

            best_bookmaker = next((b for b in bookmakers if b.get('markets')), None)
            if not best_bookmaker:
                print(f"    - No odds found for this market group.")
                continue

            for market in best_bookmaker.get('markets', []):
                market_key = market['key']
                if market_key in ['h2h', 'spreads', 'totals']:
                    if market_key not in game_odds: # Prioritize the first bookmaker for game odds
                        game_odds[market_key] = market['outcomes']
                elif 'player' in market_key:
                    for outcome in market.get('outcomes', []):
                        player_name, norm_name = outcome['description'], normalize_player_name(outcome['description'])
                        player_props.setdefault(norm_name, {"display_name": player_name, "markets": {}})
                        # This ensures we don't overwrite existing markets for a player from different queries
                        if market_key not in player_props[norm_name]['markets']:
                            player_props[norm_name]['markets'][market_key] = market.get('outcomes', [])
        
        print(f"[OK] Live odds fetched. Found props for {len(player_props)} players.")
        return {"game_odds": game_odds, "player_props": player_props}

    except Exception as e:
        print(f"[ERROR] fetching odds data: {e}"); 
        PIPELINE_SUCCESS = False
        return {}

# --- Main Execution ---
if __name__ == "__main__":
    if not ODDS_API_KEY:
        print("\n--- [FATAL] ODDS_API_KEY not found. Please create a .env file. ---")
    else:
        print("--- Starting Bills AI Dashboard Data Pipeline ---")
        current_season, previous_season = get_nfl_season_years()

        # Fetch Bills stats
        current_season_stats = fetch_and_process_season_data(current_season, BILLS_TEAM_ABBREVIATION)
        previous_season_stats = fetch_and_process_season_data(previous_season, BILLS_TEAM_ABBREVIATION)
        
        # --- MODIFICATION: Fetch league-wide data for BOTH seasons to calculate rankings ---
        previous_season_full_df = fetch_and_process_season_data(previous_season, None, for_rankings=True)
        previous_team_rankings = calculate_team_rankings(previous_season_full_df, previous_season)
        
        current_season_full_df = fetch_and_process_season_data(current_season, None, for_rankings=True)
        current_team_rankings = calculate_team_rankings(current_season_full_df, current_season)
        # --- END MODIFICATION ---

        # Fetch schedule and injury data
        espn_data = fetch_espn_data(BILLS_TEAM_ID)

        # Find the next game to determine opponent
        next_game = None
        if espn_data and espn_data.get('schedule'):
            future_games = [g for g in espn_data['schedule'] if g.get('date') and datetime.fromisoformat(g['date'].replace('Z', '+00:00')) > datetime.now(timezone.utc)]
            if future_games: next_game = sorted(future_games, key=lambda x: x['date'])[0]
        
        # Fetch stats for the upcoming opponent
        opponent_current_season_stats = None
        opponent_previous_season_stats = None
        if next_game and next_game.get('opponent_abbr'):
            opponent_abbr = next_game['opponent_abbr']
            print(f"\n--- Opponent data fetch for {opponent_abbr} ---")
            opponent_current_season_stats = fetch_and_process_season_data(current_season, opponent_abbr)
            opponent_previous_season_stats = fetch_and_process_season_data(previous_season, opponent_abbr)
        else:
            print("\n[INFO] No upcoming opponent found, skipping opponent stat fetch.")

        odds_data = fetch_all_odds_data(ODDS_API_KEY, next_game)
        
        os.makedirs('public', exist_ok=True)
        with open("public/dashboard_data.json", 'w') as f:
            json.dump({ 
                "last_updated": datetime.now().isoformat(), 
                "espn_data": espn_data, 
                "nfl_stats": { "current_season": current_season_stats, "previous_season": previous_season_stats },
                "opponent_nfl_stats": {
                    "current_season": opponent_current_season_stats,
                    "previous_season": opponent_previous_season_stats
                },
                "odds": odds_data,
                # --- MODIFICATION: Add both sets of rankings to the final JSON ---
                "team_rankings": previous_team_rankings,
                "current_team_rankings": current_team_rankings
                # --- END MODIFICATION ---
            }, f, indent=2)

        if PIPELINE_SUCCESS:
            print("\n--- [SUCCESS] Pipeline complete. Data saved to public/dashboard_data.json ---")
        else:
            print("\n--- [FAIL] Pipeline finished, but one or more data sources failed. Check logs above. ---")


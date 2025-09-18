import requests
import json
import pandas as pd
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
import time

# --- Configuration ---

# Load environment variables from the .env file (ODDS_API_KEY, GEMINI_API_KEY)
# This allows for secure handling of API keys without hardcoding them in the script.
load_dotenv() 

# Static identifiers for the Buffalo Bills used across different APIs.
BILLS_TEAM_ID = "2"  # ESPN's team ID
BILLS_TEAM_ABBREVIATION = "BUF" # NFLfastR and team ranking abbreviation

# Retrieve the API key for The Odds API from environment variables.
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

# A global flag to track the success of the pipeline. If any step fails, it's set to False.
PIPELINE_SUCCESS = True

# --- Helper Functions and Constants ---

# A dictionary to map common player name variations to a single, normalized name.
# This is crucial for consistently merging data from different sources (ESPN, nflfastR, Odds API).
PLAYER_NAME_VARIANTS = {
    "jallen": "joshallen", "jaallen": "joshallen", "kcoleman": "keoncoleman",
    "jcook": "jamescook", "dkincaid": "daltonkincaid", "dknox": "dawsonknox",
    "kshakir": "khalilshakir", "rdavis": "raydavis", "jpalmer": "joshuapalmer"
}

# A list of betting market groups to query from The Odds API.
# Querying in smaller, focused groups is more robust than a single large request
# and helps ensure some data is returned even if one market is unavailable.
MARKET_GROUPS = [
    # Standard team markets
    "h2h",
    "spreads",
    "totals",

    # Passing props
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_attempts",
    "player_pass_completions",
    "player_pass_interceptions",
    "player_pass_longest_completion",

    # Rushing props
    "player_rush_yds",
    "player_rush_attempts",
    "player_rush_longest",

    # Receiving props
    "player_reception_yds",
    "player_receptions",
    "player_reception_longest",

    # Touchdowns / Scoring props
    "player_1st_td",
    "player_anytime_td"
]

def get_nfl_season_years():
    """
    Determines the current and previous NFL season years based on the current date.
    The NFL "new year" is considered to start in March for data purposes.
    """
    now = datetime.now()
    current_season = now.year if now.month >= 3 else now.year - 1
    return current_season, current_season - 1

def normalize_player_name(name):
    """
    Standardizes a player's name by making it lowercase, removing spaces/periods,
    and checking against the PLAYER_NAME_VARIANTS map for known aliases.
    """
    lookup_name = name.replace(".", "").replace(" ", "").lower()
    return PLAYER_NAME_VARIANTS.get(lookup_name, lookup_name)

def get_detailed_injuries(injury_list_url):
    """
    Fetches detailed injury data from ESPN's API. The initial endpoint only provides
    links ('$ref') to the actual data, so this function performs nested API calls
    to retrieve full details for each injury and the associated player.
    """
    detailed_injuries = []
    try:
        injury_list_response = requests.get(injury_list_url).json()
        # Iterate through each injury reference provided by the initial API call.
        for item_ref in injury_list_response.get("items", []):
            time.sleep(0.1) # Small delay to be respectful to the API's rate limits.
            try:
                # 1. Fetch the specific injury details from its reference URL.
                injury_detail_response = requests.get(item_ref['$ref']).json()
                
                # 2. Fetch the athlete's details from its own separate reference URL within the injury data.
                athlete_ref_url = injury_detail_response.get("athlete", {}).get("$ref")
                if not athlete_ref_url:
                    continue
                
                time.sleep(0.1)
                athlete_detail_response = requests.get(athlete_ref_url).json()

                # 3. Extract all the required data points from the nested responses.
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
        return [] # Return an empty list on outer failure to prevent pipeline crash.

# --- Expert-Level Data Calculation ---
def calculate_team_rankings(season_df, season_year):
    """
    Calculates offensive and defensive yardage rankings for all teams using a full season's
    play-by-play DataFrame from nflfastR.
    """
    print(f"\n--> Calculating league-wide team rankings for {season_year}...")
    if season_df is None or season_df.empty:
        print(f"[WARN] Cannot calculate team rankings for {season_year} without season data.")
        return {}
    
    # Calculate offensive stats: Group by game and offensive team (posteam).
    off_stats = season_df.groupby(['game_id', 'posteam']).agg(
        off_yards=('yards_gained', 'sum'),
        pass_yards=('passing_yards', 'sum'),
        rush_yards=('rushing_yards', 'sum')
    ).reset_index()
    
    # Calculate the average offensive yards per game for each team.
    team_off_avg = off_stats.groupby('posteam').agg(
        avg_off_yards=('off_yards', 'mean'),
        avg_pass_yards=('pass_yards', 'mean'),
        avg_rush_yards=('rush_yards', 'mean')
    ).reset_index()

    # Calculate defensive stats: Group by game and defensive team (defteam).
    def_stats = season_df.groupby(['game_id', 'defteam']).agg(
        def_yards=('yards_gained', 'sum'),
        def_pass_yards=('passing_yards', 'sum'),
        def_rush_yards=('rushing_yards', 'sum')
    ).reset_index()

    # Calculate the average defensive yards allowed per game for each team.
    team_def_avg = def_stats.groupby('defteam').agg(
        avg_def_yards=('def_yards', 'mean'),
        avg_def_pass_yards=('def_pass_yards', 'mean'),
        avg_def_rush_yards=('def_rush_yards', 'mean')
    ).reset_index()

    # Merge the offensive and defensive stats into a single DataFrame.
    team_stats = pd.merge(team_off_avg, team_def_avg, left_on='posteam', right_on='defteam', how='outer')
    team_stats = team_stats.drop(columns=['defteam'])
    team_stats.rename(columns={'posteam': 'team'}, inplace=True)
    team_stats = team_stats.fillna(0)
    
    # Calculate ranks. For offense, higher is better (ascending=False). For defense, lower is better (ascending=True).
    team_stats['rank_offense_yards'] = team_stats['avg_off_yards'].rank(method='min', ascending=False).astype(int)
    team_stats['rank_pass_offense_yards'] = team_stats['avg_pass_yards'].rank(method='min', ascending=False).astype(int)
    team_stats['rank_rush_offense_yards'] = team_stats['avg_rush_yards'].rank(method='min', ascending=False).astype(int)
    team_stats['rank_defense_yards'] = team_stats['avg_def_yards'].rank(method='min', ascending=True).astype(int)
    team_stats['rank_pass_defense_yards'] = team_stats['avg_def_pass_yards'].rank(method='min', ascending=True).astype(int)
    team_stats['rank_rush_defense_yards'] = team_stats['avg_def_rush_yards'].rank(method='min', ascending=True).astype(int)
    
    # Convert the final DataFrame to a dictionary for easy JSON serialization.
    rankings = team_stats.set_index('team').to_dict('index')
    print(f"[OK] Team rankings for {season_year} calculated successfully.")
    return rankings

# --- Core Data Fetching Logic ---
def fetch_and_process_season_data(season, team_abbr, for_rankings=False):
    """
    Fetches and processes play-by-play data for a given season from the nflverse repository.
    Can operate in two modes:
    1. for_rankings=True: Returns the entire season's DataFrame for all teams.
    2. for_rankings=False: Filters for a specific team and aggregates player stats into game logs.
    """
    global PIPELINE_SUCCESS
    print_identifier = "Entire League" if for_rankings else team_abbr
    print(f"\n--> Fetching nflfastR data for {print_identifier} ({season} season)...")
    try:
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz"
        pbp_df = pd.read_csv(url, compression='gzip', low_memory=False)
        print(f"[OK] Loaded data for {season}.")
        
        if for_rankings:
            return pbp_df

        # Filter the massive DataFrame to only include games involving the specified team.
        team_games_df = pbp_df[(pbp_df['home_team'] == team_abbr) | (pbp_df['away_team'] == team_abbr)]
        if team_games_df.empty:
            print(f"  > No games found for {team_abbr} in {season}.")
            return {"season": season, "player_game_logs": {}}
        print(f"  > Found {team_games_df['game_id'].nunique()} games for {team_abbr}.")
        
        # Define stat columns to aggregate for each player role (passer, rusher, receiver).
        stat_configs = {
            'passer': {'yards': 'passing_yards', 'tds': 'pass_touchdown', 'attempts': 'pass_attempt', 'completions': 'complete_pass'},
            'rusher': {'yards': 'rushing_yards', 'tds': 'rush_touchdown', 'attempts': 'rush_attempt'},
            'receiver': {'yards': 'receiving_yards', 'tds': 'pass_touchdown', 'receptions': 'complete_pass'}
        }
        game_logs = {}
        # Loop through each role, filter the data, and aggregate the stats by player and week.
        for role, stats in stat_configs.items():
            player_col, df_role = f'{role}_player_name', team_games_df[(team_games_df[f'{role}_player_name'].notna()) & (team_games_df['posteam'] == team_abbr)]
            agg_dict = {f'{role}_{stat}': (col, 'sum') for stat, col in stats.items()}
            agg_stats = df_role.groupby(['week', player_col]).agg(**agg_dict).reset_index()
            
            # Restructure the aggregated data into a nested dictionary format: {player: {week: {stats}}}.
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
    """Fetches schedule and detailed injury data from ESPN's public APIs."""
    global PIPELINE_SUCCESS
    print("\n--> Fetching ESPN data...")
    try:
        # First, get a map of all team IDs to their logos and abbreviations for easy lookup.
        teams_url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
        teams_json = requests.get(teams_url).json()
        team_info_map = {
            team['team']['id']: {
                'logo': team['team']['logos'][0]['href'],
                'abbr': team['team']['abbreviation']
            } for league in teams_json['sports'][0]['leagues'] for team in league['teams']
        }

        # Fetch the full schedule for the specified team.
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
        
        # Use the helper function to get detailed injury data for the Bills.
        print("  > Fetching Bills injuries...")
        bills_injuries_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/teams/{team_id}/injuries"
        espn_data["injuries"] = get_detailed_injuries(bills_injuries_url)

        # Identify the next game to fetch opponent's injury data.
        future_games = [g for g in espn_data['schedule'] if g.get('date') and datetime.fromisoformat(g['date'].replace('Z', '+00:00')) > datetime.now(timezone.utc)]
        next_game = sorted(future_games, key=lambda x: x['date'])[0] if future_games else None

        if next_game and next_game.get('opponent_id'):
            # Use the helper function again for the opponent.
            print(f"  > Next opponent is {next_game['opponent_name']}. Fetching their injuries...")
            opp_injuries_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/teams/{next_game['opponent_id']}/injuries"
            espn_data["opponent_injuries"] = get_detailed_injuries(opp_injuries_url)
        
        print("[OK] ESPN data fetched.")
        return espn_data
    except Exception as e:
        print(f"[ERROR] fetching ESPN data: {e}")
        PIPELINE_SUCCESS = False
        return None

def fetch_all_odds_data(api_key, next_game):
    """
    Fetches all available odds for the next game by finding the correct event ID
    and then iterating through the MARKET_GROUPS list.
    """
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
        # 1. Find the specific event ID for the upcoming game.
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
        
        # 2. Loop through the market groups and fetch odds for each.
        for markets in MARKET_GROUPS:
            print(f"  > Fetching markets: {markets}...")
            time.sleep(1) # Be respectful of API rate limits by waiting between calls.
            
            odds_url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds?apiKey={api_key}&regions=us&markets={markets}"
            odds_response = requests.get(odds_url).json()
            bookmakers = odds_response.get('bookmakers', [])

            if not bookmakers: # Fallback to all regions if US bookmakers are not found for a specific market.
                print("    - No US bookmakers found, trying all regions...")
                odds_url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds?apiKey={api_key}&markets={markets}"
                odds_response = requests.get(odds_url).json()
                bookmakers = odds_response.get('bookmakers', [])

            # Use the first bookmaker that returns valid odds for this market group.
            best_bookmaker = next((b for b in bookmakers if b.get('markets')), None)
            if not best_bookmaker:
                print(f"    - No odds found for this market group.")
                continue

            # 3. Parse the response and add the odds to the appropriate dictionary.
            for market in best_bookmaker.get('markets', []):
                market_key = market['key']
                if market_key in ['h2h', 'spreads', 'totals']:
                    if market_key not in game_odds: # Prioritize the first bookmaker for main game odds.
                        game_odds[market_key] = market['outcomes']
                elif 'player' in market_key:
                    for outcome in market.get('outcomes', []):
                        player_name, norm_name = outcome['description'], normalize_player_name(outcome['description'])
                        player_props.setdefault(norm_name, {"display_name": player_name, "markets": {}})
                        # This ensures we don't overwrite existing player markets from different API calls.
                        if market_key not in player_props[norm_name]['markets']:
                            player_props[norm_name]['markets'][market_key] = market.get('outcomes', [])
        
        print(f"[OK] Live odds fetched. Found props for {len(player_props)} players.")
        return {"game_odds": game_odds, "player_props": player_props}

    except Exception as e:
        print(f"[ERROR] fetching odds data: {e}"); 
        PIPELINE_SUCCESS = False
        return {}

# --- Main Execution Block ---
if __name__ == "__main__":
    if not ODDS_API_KEY:
        print("\n--- [FATAL] ODDS_API_KEY not found. Please create a .env file. ---")
    else:
        print("--- Starting Bills AI Dashboard Data Pipeline ---")
        current_season, previous_season = get_nfl_season_years()

        # Step 1: Fetch Bills player stats for the current and previous seasons.
        current_season_stats = fetch_and_process_season_data(current_season, BILLS_TEAM_ABBREVIATION)
        previous_season_stats = fetch_and_process_season_data(previous_season, BILLS_TEAM_ABBREVIATION)
        
        # Step 2: Fetch league-wide data for both seasons to calculate team rankings.
        previous_season_full_df = fetch_and_process_season_data(previous_season, None, for_rankings=True)
        previous_team_rankings = calculate_team_rankings(previous_season_full_df, previous_season)
        
        current_season_full_df = fetch_and_process_season_data(current_season, None, for_rankings=True)
        current_team_rankings = calculate_team_rankings(current_season_full_df, current_season)

        # Step 3: Fetch schedule and injury data from ESPN.
        espn_data = fetch_espn_data(BILLS_TEAM_ID)

        # Step 4: Identify the next game to determine the upcoming opponent.
        next_game = None
        if espn_data and espn_data.get('schedule'):
            future_games = [g for g in espn_data['schedule'] if g.get('date') and datetime.fromisoformat(g['date'].replace('Z', '+00:00')) > datetime.now(timezone.utc)]
            if future_games: next_game = sorted(future_games, key=lambda x: x['date'])[0]
        
        # Step 5: Fetch player stats for the upcoming opponent for both seasons.
        opponent_current_season_stats = None
        opponent_previous_season_stats = None
        if next_game and next_game.get('opponent_abbr'):
            opponent_abbr = next_game['opponent_abbr']
            print(f"\n--- Opponent data fetch for {opponent_abbr} ---")
            opponent_current_season_stats = fetch_and_process_season_data(current_season, opponent_abbr)
            opponent_previous_season_stats = fetch_and_process_season_data(previous_season, opponent_abbr)
        else:
            print("\n[INFO] No upcoming opponent found, skipping opponent stat fetch.")

        # Step 6: Fetch live odds for the next game.
        odds_data = fetch_all_odds_data(ODDS_API_KEY, next_game)
        
        # Step 7: Combine all fetched and processed data into a single JSON file.
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
                "team_rankings": previous_team_rankings,
                "current_team_rankings": current_team_rankings
            }, f, indent=2)

        # Step 8: Print a final status message based on the global success flag.
        if PIPELINE_SUCCESS:
            print("\n--- [SUCCESS] Pipeline complete. Data saved to public/dashboard_data.json ---")
        else:
            print("\n--- [FAIL] Pipeline finished, but one or more data sources failed. Check logs above. ---")

import requests
import time
import random
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

STEAM_API_KEY = '############'
STEAM_ROOT = '76561199199514290'  # Arbitrary Steam ID to start with if the players file is empty
MAX_RETRIES = 3
RETRY_DELAY = 2
PLAYERFILE = "players.json"

#============HELPER FUNC [SOF]=============#

def batch(lst, batch_size):
    for i in range(0, len(lst), batch_size):
        yield lst[i:i + batch_size]

def request(url: str, retries: int = MAX_RETRIES):
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data in [None, {}, {'response': {}}]:
                    return None
                return data
            elif resp.status_code == 401:
                return 401
            elif resp.status_code == 404:
                return 404
            elif resp.status_code == 503:
                print("503, waiting before retry")
                time.sleep(10)
            elif resp.status_code == 429:
                print("hit rate limit, continuing after wait")
                handle_rate_limit()
                return 429
            else:
                print(f"HTTP {resp.status_code} for {url} (Attempt {attempt})")
        except requests.RequestException as e:
            print(f"Attempt {attempt} failed for {url}: {e}")
        if attempt < retries:
            time.sleep(RETRY_DELAY)
    print(f"All retries exhausted for {url} (last status {resp.status_code})")
    return resp.status_code

def handle_rate_limit():
    now = datetime.utcnow()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    sleep_seconds = (tomorrow - now).total_seconds()
    print(f"Rate limit hit. Sleeping for {sleep_seconds/3600:.1f} hours...")
    time.sleep(sleep_seconds)

#============JSON HANDLING FUNCTIONS [SOF]=============#

def load_players() -> Dict[str, Dict]:
    """Load players data from JSON file"""
    if not os.path.exists(PLAYERFILE):
        return {}
    
    try:
        with open(PLAYERFILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading players file: {e}")
        return {}

def save_players(players_data: Dict[str, Dict]):
    """Save players data to JSON file"""
    try:
        with open(PLAYERFILE, 'w', encoding='utf-8') as f:
            json.dump(players_data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(players_data)} players to {PLAYERFILE}")
    except IOError as e:
        print(f"Error saving players file: {e}")

def format_player_data(steam_user: Dict, owns_440: bool = False) -> Dict:
    """Format player data according to the desired structure"""
    return {
        "visibility": steam_user.get('communityvisibilitystate', 0),
        "440": owns_440,
        "last_updated": datetime.utcnow().isoformat(),
        "last_processed": "NIL" 
    }

def update_player_data(existing_players: Dict[str, Dict], steam_id: str, formatted_data: Dict) -> bool:
    """
    Update player data if new data is more recent or player doesn't exist
    Returns True if data was updated, False otherwise
    """
    if not steam_id:
        return False
    
    current_time = datetime.utcnow().isoformat()
    formatted_data['last_updated'] = current_time
    
    # Preserve last_processed if player already exists
    if steam_id in existing_players:
        formatted_data['last_processed'] = existing_players[steam_id].get('last_processed', 'NIL')
    
    # If player doesn't exist, add them
    if steam_id not in existing_players:
        existing_players[steam_id] = formatted_data
        return True
    
    # If player exists, check if new data is more recent
    existing_player = existing_players[steam_id]
    existing_time = existing_player.get('last_updated', '1970-01-01T00:00:00')
    
    # Simple timestamp comparison - update if new data is newer
    # Or if we have new information about TF2 ownership or visibility
    if current_time > existing_time:
        existing_players[steam_id] = formatted_data
        return True
    
    return False

#============HELPER FUNC [EOF]=============#

def get_next_player_to_process() -> str:
    """Get the next Steam ID to process from players.json"""
    players = load_players()
    
    # If no players or empty, use root
    if not players:
        return STEAM_ROOT
    
    # Find players that haven't been processed recently
    current_time = datetime.utcnow()
    twenty_four_hours_ago = current_time - timedelta(hours=24)
    
    unprocessed_players = []
    for steam_id, data in players.items():
        last_processed_str = data.get('last_processed', 'NIL')
        
        # If never processed (NIL) or processed more than 24 hours ago
        if last_processed_str == 'NIL':
            unprocessed_players.append((steam_id, datetime.min))
        else:
            try:
                last_processed = datetime.fromisoformat(last_processed_str)
                if last_processed.replace(tzinfo=None) < twenty_four_hours_ago:
                    unprocessed_players.append((steam_id, last_processed))
            except ValueError:
                # If date parsing fails, consider it unprocessed
                unprocessed_players.append((steam_id, datetime.min))
    
    # Sort by last_processed (oldest first) and return the oldest
    if unprocessed_players:
        unprocessed_players.sort(key=lambda x: x[1])
        return unprocessed_players[0][0]
    
    # If all players were processed recently, return a random one
    return random.choice(list(players.keys()))

def mark_player_processed(steam_id: str):
    """Mark a player as processed by updating their last_processed timestamp"""
    players = load_players()
    if steam_id in players:
        players[steam_id]['last_processed'] = datetime.utcnow().isoformat()
        save_players(players)

def get_status(steam_ids):
    """Get player status and update JSON file"""
    existing_players = load_players()
    updated_count = 0
    
    for batches in batch(steam_ids, 100):
        status_batch = request(f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={','.join(batches)}")
        
        if status_batch and 'response' in status_batch and 'players' in status_batch['response']:
            for steam_user in status_batch['response']['players']:
                steam_id = steam_user['steamid']
                visibility = steam_user.get('communityvisibilitystate', 0)
                owns_440 = False
                
                # Only check game ownership for public profiles (visibility == 3)
                if visibility == 3:
                    games_data = request(f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAM_API_KEY}&steamid={steam_id}&include_played_free_games=true")
                    
                    # Check if games data is valid and contains games
                    if games_data and 'response' in games_data and 'games' in games_data['response']:
                        for game in games_data['response']['games']:
                            if game.get('appid') == 440:
                                owns_440 = True
                                break
                    elif games_data == 429:  # Rate limited
                        print("Rate limit hit while checking games, skipping...")
                        time.sleep(10)
                
                # Format the player data
                formatted_data = format_player_data(steam_user, owns_440)
                
                # Update player data
                if update_player_data(existing_players, steam_id, formatted_data):
                    updated_count += 1
                
                print(f"{steam_id} tf2:{owns_440}")
    
    # Save only if there were updates
    if updated_count > 0:
        save_players(existing_players)
        print(f"Updated {updated_count} players in database")
    else:
        print("No new updates to save")

def process(steam_id):
    """Process a steam ID and its friends"""
    data = request(f"https://api.steampowered.com/ISteamUser/GetFriendList/v1/?key={STEAM_API_KEY}&steamid={steam_id}&relationship=friend")
    print(data)
    if not data or 'friendslist' not in data or data == 401:
        print("account status mismatch, refreshing...")
        status = request(f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id}")
        if status and 'response' in status and 'players' in status['response']:
            print(status['response']['players'][0])
            if status['response']['players'][0].get('communityvisibilitystate', 0) == 3:
                print("user freindslist empty or private, skipping")
        return
    
    friends = [friend["steamid"] for friend in data["friendslist"]["friends"]]
    get_status(friends)

if __name__ == "__main__":
    print("Starting TFDecal player scraper...")
    
    # Initialize empty players file if it doesn't exist
    if not os.path.exists(PLAYERFILE):
        print(f"Creating new players file: {PLAYERFILE}")
        save_players({})
    
    # Continuous processing loop
    while True:
        try:
            # Get the next player to process
            next_player = get_next_player_to_process()
            print(f"Processing player: {next_player}")
            
            # Process the player (get their friends and update data)
            process(next_player)
            
            # Mark as processed (only updates last_processed, not last_updated)
            mark_player_processed(next_player)
            print(f"Completed processing player: {next_player}")
            
            # Wait before processing next player to avoid rate limiting
            print("Waiting 10 seconds before next player...")
            time.sleep(10)
            
        except KeyboardInterrupt:
            print("\nScraper stopped by user")
            break
        except Exception as e:
            print(f"Error processing player: {e}")
            print("Waiting 30 seconds before retry...")
            time.sleep(30)

import requests
import json
import time
import os
import threading

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
QUICKSAVE_INTERVAL = 600  # 10 minutes in seconds

# Paths to the output files
STEAM_API_KEY = '##############################'
TF2_PLAYERS_FILE = "tf2_public_players.txt"
ERROR_PLAYERS_FILE = "error_players.txt"
VIEWED_PLAYERS_FILE = "viewed_players.txt"
QUICKSAVE_FILE = "quicksave.txt"

def save_to_file(file_path, steam_id):
    """Append a Steam ID to the specified file."""
    with open(file_path, "a") as file:
        file.write(f"{steam_id}\n")

def load_visited_players():
    """Load visited players from the viewed players file."""
    if not os.path.exists(VIEWED_PLAYERS_FILE):
        return set()  # If the file doesn't exist, return an empty set
    
    with open(VIEWED_PLAYERS_FILE, "r") as file:
        return set(line.strip() for line in file.readlines())

def make_request_with_retry(url):
    """Make a GET request with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Request failed with status {response.status_code}. Retrying ({attempt + 1}/{MAX_RETRIES})...")
        except requests.exceptions.RequestException as e:
            print(f"Request exception: {e}. Retrying ({attempt + 1}/{MAX_RETRIES})...")
        time.sleep(RETRY_DELAY)
    print("Max retries exceeded. Failed to fetch data.")
    return None

def fetch_player_data(steam_id):
    """Fetches basic user data, privacy settings, and owned games."""
    # Fetch Player Summary (privacy, etc.)
    player_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamid={steam_id}"
    player_data = make_request_with_retry(player_url)
    
    privacy = None
    if player_data and 'response' in player_data and 'players' in player_data['response']:
        player = player_data['response']['players'][0]
        privacy = player.get('communityvisibilitystate', None)  # 3 = Public, 1 = Private
    
    # Fetch Owned Games (TF2 check)
    owned_games_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAM_API_KEY}&steamid={steam_id}&include_appinfo=true"
    owned_games_data = make_request_with_retry(owned_games_url)
    
    TF2 = False
    if owned_games_data and 'response' in owned_games_data and 'games' in owned_games_data['response']:
        games = owned_games_data['response']['games']
        TF2 = any(game['appid'] == 440 for game in games)  # Check if TF2 (appid 440) is in owned games
    
    return privacy, TF2

def fetch_friends_and_process(steam_id, visited_players):
    """Fetch the user's friends and process them (check privacy and TF2 ownership)."""
    if steam_id in visited_players:
        return  # Skip if we've already visited this player

    friends_url = f"https://api.steampowered.com/ISteamUser/GetFriendList/v1/?key={STEAM_API_KEY}&steamid={steam_id}&relationship=friend"
    friends_data = make_request_with_retry(friends_url)

    if friends_data and 'friendslist' in friends_data and 'friends' in friends_data['friendslist']:
        friend_ids = [friend['steamid'] for friend in friends_data['friendslist']['friends']]
        print(f"Found {len(friend_ids)} friends.")

        for friend_id in friend_ids:
            if friend_id not in visited_players:
                print(f"Checking {friend_id} for public profile and TF2 ownership...")
                try:
                    privacy, owns_tf2 = fetch_player_data(friend_id)
                    if privacy == 3 and owns_tf2:
                        save_to_file(TF2_PLAYERS_FILE, friend_id)  # Save if public and owns TF2
                        print(f"Player {friend_id} has a public profile and owns TF2. Saved to {TF2_PLAYERS_FILE}.")
                    else:
                        print(f"Ignoring {friend_id}: private profile or doesn't own TF2.")
                except Exception as e:
                    print(f"Error processing {friend_id}: {e}")
                    save_to_file(ERROR_PLAYERS_FILE, friend_id)  # Save error to file
                    print(f"Saved {friend_id} to {ERROR_PLAYERS_FILE} due to error.")

                visited_players.add(friend_id)
                save_to_file(VIEWED_PLAYERS_FILE, friend_id)  # Save to viewed players file
    else:
        print(f"Failed to fetch friends list for {steam_id}.")
        save_to_file(ERROR_PLAYERS_FILE, steam_id)

def quicksave(steam_id):
    """Clear quicksave.txt and save the current steam_id every 10 minutes."""
    while True:
        with open(QUICKSAVE_FILE, "w") as file:
            file.write(f"{steam_id}\n")  # Clear the file and save the current steam_id
        print(f"Quicksave: Saved current steam_id {steam_id} to {QUICKSAVE_FILE}.")
        time.sleep(QUICKSAVE_INTERVAL)  # Wait for 10 minutes

def main(seed_steamid):
    """Main function to start processing players from the seed Steam ID."""
    visited_players = load_visited_players()  # Load visited players from file
    fetch_friends_and_process(seed_steamid, visited_players)

    # Start the quicksave thread
    quicksave_thread = threading.Thread(target=quicksave, args=(seed_steamid,))
    quicksave_thread.daemon = True  # Daemon thread will exit when the main program exits
    quicksave_thread.start()

if __name__ == "__main__":
    seed_steamid = "76561198373996593"  # Replace with a valid seed Steam ID
    main(seed_steamid)

import requests
import json
import time
import os

STEAM_API_KEY = '##################'
ROOT_STEAM_ID = '382962393904447492'  # Default Steam ID to start with if the TF2 players file is empty
MAX_RETRIES = 10
RETRY_DELAY = 2
TF2_PLAYERS_FILE = "tf2_public_players.txt"
ERROR_PLAYERS_FILE = "error_players.txt"
VIEWED_PLAYERS_FILE = "viewed_players.txt"
CHECKED_USERS_FILE = "checked_users.txt"  # New file to track fully processed users

def make_request_with_retry(url):
    """Make a GET request with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return 404
            else:
                print(f"Request failed with status {response.status_code}. Retrying ({attempt + 1}/{MAX_RETRIES})...")
        except requests.exceptions.RequestException as e:
            print(f"Request exception: {e}. Retrying ({attempt + 1}/{MAX_RETRIES})...")
        time.sleep(RETRY_DELAY)
    print("Max retries exceeded. Failed to fetch data.")
    return None

def get_decalid(steamid):
    """ Fetch the inventory for TF2 and process the item with defindex 474. """
    inventory = make_request_with_retry(f"https://api.steampowered.com/IEconItems_440/GetPlayerItems/v1/?key={STEAM_API_KEY}&steamid={steamid}")
    
    if inventory and 'result' in inventory and 'items' in inventory['result']:
        for item in inventory['result']['items']:
            if item.get('defindex') == 474:
                print("Decal item found!")
                lo, hi = None, None
                for attribute in item.get('attributes', []):
                    if attribute.get('defindex') == 152:
                        hi = int(attribute.get('value'))
                    elif attribute.get('defindex') == 227:
                        lo = int(attribute.get('value'))
                if lo is not None and hi is not None:
                    seed = (lo << 32) + hi
                    print(f"Reconstructed seed: {seed}")
                    save_url(seed, steamid)
                else:
                    print("Either lo (152) or hi (227) value is missing.")
    else:
        print(f"Failed to fetch inventory for {steamid}.")

def save_url(decalid, steamid):
    ugc_data = make_request_with_retry(f"https://api.steampowered.com/ISteamRemoteStorage/GetUGCFileDetails/v1/?key={STEAM_API_KEY}&steamid={steamid}&ugcid={decalid}&appid=440")
    
    if ugc_data is None:
        print(f"Failed to fetch UGC details for {steamid}. Skipping to the next item.")
        return  # Skip if request failed

    # Check if 404 status
    if ugc_data == 404:
        print(f"UGC details for {steamid} not found (404 error). Skipping to the next item.")
        return  # Skip if 404 error is received

    if 'data' in ugc_data:
        url = ugc_data['data'].get('url', None)
        if url:
            try:
                with open('ugc_url.txt', 'r') as f:
                    existing_urls = f.readlines()
            except FileNotFoundError:
                existing_urls = []

            if url + '\n' not in existing_urls:
                with open('ugc_url.txt', 'a') as f:
                    f.write(url + '\n')
                print(f"UGC URL saved to 'ugc_url.txt' for {steamid}: {url}")
            else:
                print(f"UGC URL already exists. Skipping save for {steamid}.")
        else:
            print(f"UGC file URL not found for {steamid}.")
    else:
        print(f"Failed to fetch UGC details for {steamid}.")

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

def load_checked_users():
    """Load checked users from the checked users file."""
    if not os.path.exists(CHECKED_USERS_FILE):
        return set()  # If the file doesn't exist, return an empty set
    with open(CHECKED_USERS_FILE, "r") as file:
        return set(line.strip() for line in file.readlines())

def fetch_player_data(steam_id):
    """Fetches basic user data, privacy settings, and owned games."""
    # Fetch Player Summary (privacy, etc.)
    player_data = make_request_with_retry(f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id}")
    
    privacy = None
    if player_data and 'response' in player_data and 'players' in player_data['response']:
        player = player_data['response']['players'][0]
        privacy = player.get('communityvisibilitystate', None)  # 3 = Public, 1 = Private
    
    # Fetch Owned Games (TF2 check)
    owned_games_data = make_request_with_retry(f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAM_API_KEY}&steamid={steam_id}&include_played_free_games=true")
    
    TF2 = False
    if owned_games_data and 'response' in owned_games_data and 'games' in owned_games_data['response']:
        games = owned_games_data['response']['games']
        TF2 = any(game['appid'] == 440 for game in games)  # Check if TF2 (appid 440) is in owned games
    return privacy, TF2

def fetch_friends_and_process(steam_id, visited_players, checked_users):
    """Fetch the user's friends and process them (check privacy and TF2 ownership)."""
    if steam_id in checked_users:
        return  # Skip if we've already visited or fully processed this player

    friends_data = make_request_with_retry(f"https://api.steampowered.com/ISteamUser/GetFriendList/v1/?key={STEAM_API_KEY}&steamid={steam_id}&relationship=friend")

    if friends_data and 'friendslist' in friends_data and 'friends' in friends_data['friendslist']:
        friend_ids = [friend['steamid'] for friend in friends_data['friendslist']['friends']]
        print(f"Found {len(friend_ids)} friends for player {steam_id}.")

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

    # After processing friends, mark this player as fully processed
    save_to_file(CHECKED_USERS_FILE, steam_id)
    print(f"Player {steam_id} fully processed and saved to {CHECKED_USERS_FILE}.")

def process_tf2_players():
    """Process players from the TF2 players file or default to the root Steam ID."""
    if os.path.exists(TF2_PLAYERS_FILE):
        with open(TF2_PLAYERS_FILE, "r") as file:
            player_ids = [line.strip() for line in file.readlines()]
    else:
        player_ids = [ROOT_STEAM_ID]

    if not player_ids:
        player_ids = [ROOT_STEAM_ID]  # Default to the root Steam ID if no players are found

    visited_players = load_visited_players()
    checked_users = load_checked_users()
    print(player_ids)
    for steam_id in player_ids:
        if steam_id not in checked_users:
            get_decalid(steam_id)
            fetch_friends_and_process(steam_id, visited_players, checked_users)
            save_to_file(CHECKED_USERS_FILE, steam_id)
            return 
if __name__ == "__main__":
    while True:
        process_tf2_players()
    

import requests
import json
import time

STEAM_API_KEY = '####################'  # Your Steam API key
ROOT_STEAM_ID = '76561199199514290'  # The Steam ID to default to on first startup
CHECKPOINT_STEAM_ID = 0 # the last processed id in case of a premature exit
MAX_RETRIES = 10  # Maximum number of retries
RETRY_DELAY = 2  # Delay between retries in seconds

def Make_request_with_retry(url):
    """ Make a GET request with retry logic. """
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Request failed with status {response.status_code}. Retrying ({attempt+1}/{MAX_RETRIES})...")
        except requests.exceptions.RequestException as e:
            print(f"Request exception: {e}. Retrying ({attempt+1}/{MAX_RETRIES})...")
        time.sleep(RETRY_DELAY)

    print("Max retries exceeded. Failed to fetch data.")
    return None

def Get_decalid(steamid):
    """ Fetch the inventory for TF2 and process the item with defindex 474. """
    inventory = Make_request_with_retry(f"https://api.steampowered.com/IEconItems_440/GetPlayerItems/v1/?key={STEAM_API_KEY}&steamid={steamid}")

    if inventory and 'result' in inventory and 'items' in inventory['result']:
        for item in inventory['result']['items']:
            if item.get('defindex') == 474:
                print("decal item found!")
                lo, hi = None, None
                for attribute in item.get('attributes', []):
                    if attribute.get('defindex') == 152:
                        hi = int(attribute.get('value'))
                    elif attribute.get('defindex') == 227:
                        lo = int(attribute.get('value'))
                if lo is not None and hi is not None:
                    seed = (lo << 32) + hi
                    print(f"Reconstructed seed: {seed}")
                    Saveurl(seed, steamid)
                else:
                    print("Either lo (152) or hi (227) value is missing.")
    else:
        print(f"Failed to fetch inventory for {steamid}.")
        saveusers(steamid, 2)
def Saveurl(decalid, steamid):
    ugc_data = Make_request_with_retry(f"https://api.steampowered.com/ISteamRemoteStorage/GetUGCFileDetails/v1/?key={STEAM_API_KEY}&steamid={steamid}&ugcid={decalid}&appid=440")
    if ugc_data and 'data' in ugc_data:
        url = ugc_data['data'].get('url', None)
        if url:
            try:
                with open('url.txt', 'r') as f:
                    existing_urls = f.readlines()
            except FileNotFoundError:
                existing_urls = []

            if url + '\n' not in existing_urls:
                with open('ugc_url.txt', 'a') as f:
                    f.write(url + '\n')
                print(f"UGC URL saved to 'url.txt' for {steamid}: {url}")
            else:
                print(f"UGC URL already exists. Skipping save for {steamid}.")
        else:
            print(f"UGC file URL not found for {steamid}.")
    else:
        print(f"Failed to fetch UGC details for {steamid}.")

def SortFreinds(steamid):
    Make_request_with_retry(f"https://api.steampowered.com/ISteamUser/GetFriendList/v1/?key={STEAM_API_KEY}&steamid={steamid}")
    
    Make_request_with_retry(f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAM_API_KEY}&steamid={steamid}&include_played_free_games=true")

def saveusers(user, Error):
     0
Get_decalid(76561199498684878)

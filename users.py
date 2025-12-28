import requests
import time
import json
import os
import sys
from typing import Dict, List, Iterable

# ================== CONFIG ==================

STEAM_API_KEY = "#################"
SEED_STEAM_ID = "76561199199514290"
PLAYERFILE = "players.json"

BATCH_SIZE = 100
REQUEST_DELAY = 1.2
MAX_RETRIES = 3
SAFETY_SAVE_INTERVAL = 60 # in seconds

APPID_TF2 = 440

# ================== HTTP ==================

def steam_get(url: str):
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                print("[RATE LIMIT] sleeping 60s")
                time.sleep(60)
            elif r.status_code in (401, 403, 404):
                return None
            else:
                print(f"[HTTP {r.status_code}] retrying")
        except requests.RequestException as e:
            print(f"[ERROR] {e}")
        time.sleep(2)
    return None

# ================== JSON ==================

def load_players() -> Dict[str, Dict]:
    if not os.path.exists(PLAYERFILE):
        return {}
    with open(PLAYERFILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_players(players: Dict[str, Dict]):
    tmp = PLAYERFILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(players, f, indent=2)
    os.replace(tmp, PLAYERFILE)
    print(f"[SAVE] {len(players)} players")

# ================== UTIL ==================

def batch(iterable: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]

def ensure_player(players, steamid):
    if steamid not in players:
        players[steamid] = {
            "crawled": False,
            "vis": 0,
            "440": False
        }

# ================== CORE ==================

def update_visibility(players, steamids):
    for chunk in batch(steamids, BATCH_SIZE):
        data = steam_get(
            "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
            f"?key={STEAM_API_KEY}&steamids={','.join(chunk)}"
        )
        if not data:
            continue
        for p in data["response"]["players"]:
            ensure_player(players, p["steamid"])
            players[p["steamid"]]["vis"] = p.get("communityvisibilitystate", 0)
        time.sleep(REQUEST_DELAY)

def check_tf2(players, steamids):
    for sid in steamids:
        if players[sid]["440"] or players[sid]["vis"] != 3:
            continue
        data = steam_get(
            "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
            f"?key={STEAM_API_KEY}&steamid={sid}&include_played_free_games=true"
        )
        if data:
            for g in data.get("response", {}).get("games", []):
                if g.get("appid") == APPID_TF2:
                    players[sid]["440"] = True
                    break
        time.sleep(REQUEST_DELAY)

def crawl_friends(players, steamid):
    data = steam_get(
        "https://api.steampowered.com/ISteamUser/GetFriendList/v1/"
        f"?key={STEAM_API_KEY}&steamid={steamid}&relationship=friend"
    )
    if not data:
        return []
    friends = [f["steamid"] for f in data["friendslist"]["friends"]]
    for f in friends:
        ensure_player(players, f)
    return friends

def get_next_uncrawled(players):
    for sid, p in players.items():
        if not p["crawled"] and p["vis"] == 3:
            return sid
    return None

# ================== MAIN ==================

def main():
    players = load_players()
    ensure_player(players, SEED_STEAM_ID)

    last_save = time.time()

    try:
        while True:
            # visibility update
            pending_vis = [sid for sid, p in players.items() if p["vis"] == 0]
            if pending_vis:
                update_visibility(players, pending_vis)

            target = get_next_uncrawled(players)
            if not target:
                print("[DONE] no uncrawled public players")
                break

            print(f"[CRAWL] {target}")
            friends = crawl_friends(players, target)
            update_visibility(players, friends)
            check_tf2(players, friends)
            players[target]["crawled"] = True

            # periodic save
            if time.time() - last_save > SAFETY_SAVE_INTERVAL:
                save_players(players)
                last_save = time.time()

            time.sleep(REQUEST_DELAY)

    except KeyboardInterrupt:
        print("\n[EXIT] Ctrl+C detected")

    except Exception as e:
        print(f"\n[CRASH] {e}")

    finally:
        print("[FINAL SAVE]")
        save_players(players)
        sys.exit(0)

if __name__ == "__main__":
    main()

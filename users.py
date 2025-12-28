import requests
import time
import json
import os
import sys
from typing import Dict, List, Iterable
import threading

def stats_loop(players):
    while True:
        print_stats(players)
        time.sleep(STATS_INTERVAL)
        
# ================== CONFIG ==================
STEAM_API_KEY = "#################"
SEED_STEAM_ID = "76561199199514290"
PLAYERFILE = "players.json"

BATCH_SIZE = 100
REQUEST_DELAY = 0.1  # delay between requests
MAX_RETRIES = 3
SAFETY_SAVE_INTERVAL = 60
STATS_INTERVAL = 2.0

APPID_TF2 = 440

# ================== STATS ==================
stats = {
    "requests": 0,
    "start": time.time(),
    "last_print": 0,
}

# ================== HTTP ==================
def steam_get(url: str):
    for _ in range(MAX_RETRIES):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                stats["requests"] += 1
                return r.json()
            if r.status_code == 429:
                print("\n[RATE LIMIT] sleeping 60s")
                time.sleep(60)
            elif r.status_code in (401, 403, 404):
                return None
        except requests.RequestException:
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

# ================== UTIL ==================
def batch(lst: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

def ensure_player(players, steamid):
    if steamid not in players:
        players[steamid] = {
            "crawled": False,
            "vis": 0,
            "440": None  # None means unknown
        }

# ================== API LOGIC ==================
def update_visibility(players, steamids):
    for chunk in batch(steamids, BATCH_SIZE):
        data = steam_get(
            f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
            f"?key={STEAM_API_KEY}&steamids={','.join(chunk)}"
        )
        if not data:
            continue
        for p in data["response"]["players"]:
            sid = p["steamid"]
            ensure_player(players, sid)
            players[sid]["vis"] = p.get("communityvisibilitystate", 0)
        time.sleep(REQUEST_DELAY)

def check_tf2(players, steamids):
    for sid in steamids:
        if players[sid]["440"] is not None:  # skip if known
            continue
        if players[sid]["vis"] != 3:  # must be public
            continue

        data = steam_get(
            f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
            f"?key={STEAM_API_KEY}&steamid={sid}&include_played_free_games=true"
        )
        owns_tf2 = False
        if data:
            for g in data.get("response", {}).get("games", []):
                if g.get("appid") == APPID_TF2:
                    owns_tf2 = True
                    break
        players[sid]["440"] = owns_tf2
        time.sleep(REQUEST_DELAY)

def crawl_friends(players, steamid):
    data = steam_get(
        f"https://api.steampowered.com/ISteamUser/GetFriendList/v1/"
        f"?key={STEAM_API_KEY}&steamid={steamid}&relationship=friend"
    )
    if not data or "friendslist" not in data:
        return []
    friends = [f["steamid"] for f in data["friendslist"]["friends"]]
    for f in friends:
        ensure_player(players, f)
    return friends

# ================== SELECTION ==================
def get_next_uncrawled(players):
    for sid, p in players.items():
        if not p["crawled"] and p["vis"] == 3:
            return sid
    return None

# ================== STATS OUTPUT ==================
def print_stats(players):
    now = time.time()
    if now - stats["last_print"] < STATS_INTERVAL:
        return

    total = len(players)
    public = sum(1 for p in players.values() if p["vis"] == 3)
    tf2 = sum(1 for p in players.values() if p["440"] is True)
    unknown_tf2 = sum(1 for p in players.values() if p["440"] is None)
    crawled = sum(1 for p in players.values() if p["crawled"])
    queue = sum(1 for p in players.values() if not p["crawled"] and p["vis"] == 3)

    rps = stats["requests"] / max(now - stats["start"], 1)

    print(
        f"\r[RUN] total={total:,} | public={public:,} | "
        f"tf2={tf2:,} | unknown_tf2={unknown_tf2:,} | "
        f"crawled={crawled:,} | queue={queue:,} | rps={rps:.2f}",
        end="",
        flush=True
    )
    stats["last_print"] = now

# ================== MAIN ==================
def main():
    players = load_players()
    ensure_player(players, SEED_STEAM_ID)

    last_save = time.time()

    # Start stats thread
    stats_thread = threading.Thread(target=stats_loop, args=(players,), daemon=True)
    stats_thread.start()

    try:
        while True:
            # Resolve unknown visibility (batched)
            pending_vis = [sid for sid, p in players.items() if p["vis"] == 0]
            if pending_vis:
                update_visibility(players, pending_vis)

            target = get_next_uncrawled(players)
            if not target:
                print("\n[DONE] crawl exhausted")
                break

            friends = crawl_friends(players, target)

            # Only check visibility for unknown friends
            new_ids = [f for f in friends if players[f]["vis"] == 0]
            if new_ids:
                update_visibility(players, new_ids)

            # TF2 check for public users with unknown ownership
            check_tf2(players, friends)

            players[target]["crawled"] = True

            # Periodic safety save
            if time.time() - last_save > SAFETY_SAVE_INTERVAL:
                save_players(players)
                last_save = time.time()

    except KeyboardInterrupt:
        print("\n[EXIT] Ctrl+C")

    except Exception as e:
        print(f"\n[CRASH] {e}")

    finally:
        print("\n[FINAL SAVE]")
        save_players(players)
        sys.exit(0)


if __name__ == "__main__":
    main()

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

STEAM_API_KEY = '23C838AA4B6470A7841F3DED59A10AB0'
STEAM_ROOT = '76561199199514290'  # Arbatrairy Steam ID to start with if the players file is empty
MAX_RETRIES = 3
RETRY_DELAY = 2
PLAYERFILE = "players.json"
DATAFILE = "data.json"

#============HELPER FUNC [SOF]=============#

def batch(lst, batch_size):
    for i in range(0, len(lst), batch_size):
        yield lst[i:i + batch_size]

def request(url: str, retries: int = MAX_RETRIES):
	for attempt in range(1, retries + 1):
		try:
			resp = requests.get(url, timeout=15)
			if resp.status_code == 200:
				return resp.json()
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

#============HELPER FUNC [EOF]=============#

def get_decalid(steam_id):
	inventory = request(f"https://api.steampowered.com/IEconItems_440/GetPlayerItems/v1/?key={STEAM_API_KEY}&steamid={steam_id}")
	if inventory and 'result' in inventory and 'items' in inventory['result']:
	        for item in inventory['result']['items']:
	            if item.get('defindex') in [474, 619, 623, 625]:
	                print("Decal item found!")
	                lo, hi = None, None
	                for attribute in item.get('attributes', []):
	                    if attribute.get('defindex') == 152:
	                        hi = int(attribute.get('value'))
	                    elif attribute.get('defindex') == 227:
	                        lo = int(attribute.get('value'))
	                if lo is not None and hi is not None:
	                    seed = (lo << 32) + hi
	                    print(request(f"https://api.steampowered.com/ISteamRemoteStorage/GetUGCFileDetails/v1/?key={STEAM_API_KEY}&steamid={steam_id}&ugcid={seed}&appid=440"))
	                    print(f"Reconstructed seed: {seed}")
	                else:
	                    print("Either lo (152) or hi (227) value is missing.")
	else:
		print(f"Failed to fetch inventory for {steam_id}.")
def get_status(steam_ids):
	for batches in batch(steam_ids, 100):
		status_batch = request(f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={batches}")
		for steam_user in status_batch['response']['players']:
			print(steam_user['steamid'], steam_user['communityvisibilitystate'], steam_user['personaname'], steam_user.get('realname', "not set"))

def process(steam_id):
	data = request(f"https://api.steampowered.com/ISteamUser/GetFriendList/v1/?key={STEAM_API_KEY}&steamid={steam_id}&relationship=friend")
	if not data:
		print("account status mismatch, refreshing...")
		status = request(f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id}")
		print(status['response']['players'][0])
	freinds = [friend["steamid"] for friend in data["friendslist"]["friends"]]
	get_status(freinds)
	get_decalid(steam_id)

if __name__ == "__main__":
	print("Starting TFDecal data scraper...")
	process(STEAM_ROOT)


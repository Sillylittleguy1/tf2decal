# RE-DOIN TIME!
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

STEAM_API_KEY = '##############'
STEAM_ROOT = '76561199199514290'  # Arbatrairy Steam ID to start with if the TF2 players file is empty
MAX_RETRIES = 3
RETRY_DELAY = 2
PLAYERFILE = "players.json"
DATAFILE = "tfd.json"

def request(url: str, retries: int = MAX_RETRIES):
	for attempt in range(1, retries + 1):
		try:
			resp = requests.get(url, timeout=15)
			if resp.status_code == 200:
				return resp.json()
			elif resp.status_code == 404:
				return 404
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

def get_decalid(steamid):
	inventory = requests.get(f"https://api.steampowered.com/IEconItems_440/GetPlayerItems/v1/?key={STEAM_API_KEY}&steamid={steam_id}").json()# get inventory of steamid
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
	                    print(f"Reconstructed seed: {seed}")
	                else:
	                    print("Either lo (152) or hi (227) value is missing.")
	else:
		print(f"Failed to fetch inventory for {steamid}.")

def handle_rate_limit():
    now = datetime.utcnow()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    sleep_seconds = (tomorrow - now).total_seconds()
    print(f"Rate limit hit. Sleeping for {sleep_seconds/3600:.1f} hours...")
    time.sleep(sleep_seconds)

def process(steam_id):
	freinds = request(f"https://api.steampowered.com/ISteamUser/GetFriendList/v1/?key={STEAM_API_KEY}&steamid={steam_id}&relationship=friend")
	if not freinds:
		print("account status mismatch, refreshing...")

if __name__ == "__main__":
	print("Starting TFDecal data scraper...")
	process(STEAM_ROOT)

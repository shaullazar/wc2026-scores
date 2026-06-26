#!/usr/bin/env python3
"""
WC 2026 Score Scraper — ESPN as primary source
Fetches scores for a rolling window of dates around today
"""
import json, sys, traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUTPUT = Path(__file__).parent / "scores.json"

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable,"-m","pip","install","requests","-q"])
    import requests

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.espn.com",
    "Referer": "https://www.espn.com/soccer/",
})

# Team name normalization: ESPN name -> our dashboard name
TEAM_MAP = {
    "Cape Verde":        "Cabo Verde",
    "Korea Republic":    "South Korea",
    "South Korea":       "South Korea",
    "Iran":              "IR Iran",
    "IR Iran":           "IR Iran",
    "Bosnia and Herzegovina": "Bosnia-Herz.",
    "Bosnia & Herzegovina":   "Bosnia-Herz.",
    "Trinidad and Tobago":    "Trinidad & Tobago",
    "United States":     "USA",
    "USA":               "USA",
    "Ivory Coast":       "Ivory Coast",
    "Côte d'Ivoire":     "Ivory Coast",
    "New Zealand":       "New Zealand",
}

def norm_team(name):
    return TEAM_MAP.get(name, name)

def fetch_espn_date(date_str):
    """Fetch ESPN scoreboard for a specific date (YYYYMMDD)"""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date_str}"
    r = SESSION.get(url, timeout=12)
    print(f"  ESPN {date_str}: HTTP {r.status_code}")
    if r.status_code != 200:
        return []

    data = r.json()
    matches = []
    for event in data.get("events", []):
        comp = event.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue

        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        status = comp.get("status", {}).get("type", {})
        completed = status.get("completed", False)
        state = status.get("state", "pre")  # pre, in, post
        live = state == "in"

        hs = home.get("score")
        as_ = away.get("score")

        # Only include scores if game is in progress or finished
        if not (completed or live):
            hs = as_ = None
        else:
            hs = int(hs) if hs is not None else 0
            as_ = int(as_) if as_ is not None else 0

        start = event.get("date", "")

        matches.append({
            "home": norm_team(home.get("team", {}).get("displayName", "")),
            "away": norm_team(away.get("team", {}).get("displayName", "")),
            "hs":   hs,
            "as":   as_,
            "done": completed,
            "live": live,
            "utc":  start,
            "venue": comp.get("venue", {}).get("fullName", ""),
            "group": "World Cup",
        })

    done_count = sum(1 for m in matches if m["done"])
    live_count = sum(1 for m in matches if m["live"])
    print(f"    -> {len(matches)} matches ({done_count} done, {live_count} live)")
    return matches

def scrape_espn():
    """Fetch ESPN scores for tournament window: Jun 11 - Jul 19 2026"""
    today = datetime.now(timezone.utc)
    all_matches = []
    seen = set()

    # Fetch today + next 3 days (upcoming) + past 20 days (results)
    dates_to_fetch = []
    for delta in range(-20, 4):
        d = today + timedelta(days=delta)
        if datetime(2026,6,11,tzinfo=timezone.utc) <= d <= datetime(2026,7,19,tzinfo=timezone.utc):
            dates_to_fetch.append(d.strftime("%Y%m%d"))

    print(f"  Fetching {len(dates_to_fetch)} dates...")
    for date_str in dates_to_fetch:
        try:
            matches = fetch_espn_date(date_str)
            for m in matches:
                key = (m["home"], m["away"])
                if key not in seen:
                    seen.add(key)
                    all_matches.append(m)
        except Exception as e:
            print(f"    Date {date_str} failed: {e}")

    print(f"  Total unique matches: {len(all_matches)}")
    return all_matches

def main():
    print("WC 2026 Score Scraper starting...")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    try:
        matches = scrape_espn()
        if not matches:
            print("ESPN returned no matches — keeping existing scores.json")
            sys.exit(0)

        done  = sum(1 for m in matches if m["done"])
        live  = sum(1 for m in matches if m["live"])
        print(f"\nTotal: {len(matches)} matches | {done} completed | {live} live")

        output = {
            "updated": datetime.now(timezone.utc).isoformat(),
            "matches": matches,
            "source":  "espn",
        }
        OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        print(f"Written to scores.json")

    except Exception as e:
        print(f"FATAL: {e}")
        traceback.print_exc()
        if OUTPUT.exists():
            print("Keeping existing scores.json")
            sys.exit(0)
        sys.exit(1)

if __name__ == "__main__":
    main()

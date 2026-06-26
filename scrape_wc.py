#!/usr/bin/env python3
"""
WC 2026 Score Scraper
Scrapes Wikipedia's 2026 FIFA World Cup group stage page
Outputs scores.json to be read by the dashboard
"""

import json, re, urllib.request, urllib.error, ssl, sys
from datetime import datetime, timezone
from pathlib import Path

OUTPUT = Path(__file__).parent / "scores.json"
UA = "Mozilla/5.0 (compatible; WC2026Dashboard/1.0; +https://github.com)"

def fetch(url):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
    return resp.read().decode("utf-8")

def scrape_wikipedia():
    """Scrape match results from Wikipedia's WC 2026 group stage article"""
    url = "https://en.wikipedia.org/w/api.php?action=parse&page=2026_FIFA_World_Cup_group_stage&prop=wikitext&format=json"
    data = json.loads(fetch(url))
    wikitext = data["parse"]["wikitext"]["*"]

    matches = []
    # Parse football-match templates from wikitext
    # {{football box ... }}
    pattern = re.compile(
        r'\{\{[Ff]ootball box\s*\n(.*?)\}\}', re.DOTALL
    )
    for m in pattern.finditer(wikitext):
        block = m.group(1)
        def get(key):
            r = re.search(rf'\|\s*{key}\s*=\s*([^\n|}}]+)', block)
            return r.group(1).strip() if r else ""
        
        home  = get("team1")
        away  = get("team2")
        score = get("score")
        date  = get("date")
        time  = get("time")
        venue = get("stadium")
        group = get("round")

        if not home or not away:
            continue

        # Parse score
        hs, as_ = None, None
        sm = re.match(r'(\d+)\s*[–\-]\s*(\d+)', score)
        if sm:
            hs, as_ = int(sm.group(1)), int(sm.group(2))

        # Parse datetime to UTC ISO
        utc_str = ""
        try:
            dt_str = f"{date} {time}" if time else date
            # Wikipedia uses formats like "26 June 2026" "20:00"
            for fmt in ["%d %B %Y %H:%M", "%B %d, %Y %H:%M", "%d %B %Y"]:
                try:
                    dt = datetime.strptime(dt_str.strip(), fmt)
                    # Wikipedia times are local match venue time; approximate as UTC-4 (ET) for US games
                    utc_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    break
                except ValueError:
                    continue
        except Exception:
            pass

        matches.append({
            "home":  home,
            "away":  away,
            "hs":    hs,
            "as":    as_,
            "done":  hs is not None,
            "utc":   utc_str,
            "venue": venue,
            "group": group,
        })

    return matches

def scrape_sofascore():
    """Try Sofascore API for live/today scores"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.sofascore.com/",
        "Accept": "application/json",
    }
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
    data = json.loads(resp.read().decode())
    
    matches = []
    for event in data.get("events", []):
        # Filter for World Cup events
        tournament = event.get("tournament", {})
        if "world cup" not in tournament.get("name", "").lower() and \
           "world cup" not in tournament.get("uniqueTournament", {}).get("name", "").lower():
            continue
        
        home = event.get("homeTeam", {}).get("name", "")
        away = event.get("awayTeam", {}).get("name", "")
        hs   = event.get("homeScore", {}).get("current")
        as_  = event.get("awayScore", {}).get("current")
        
        status_code = event.get("status", {}).get("code", 0)
        # 0=not started, 6=in progress, 7=half time, 100=finished
        done = status_code == 100
        live = status_code in [6, 7]
        
        start_ts = event.get("startTimestamp", 0)
        utc = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if start_ts else ""
        
        matches.append({
            "home":  home,
            "away":  away,
            "hs":    hs if (done or live) else None,
            "as":    as_ if (done or live) else None,
            "done":  done,
            "live":  live,
            "utc":   utc,
            "venue": event.get("venue", {}).get("stadium", {}).get("name", ""),
            "group": tournament.get("name", "World Cup"),
        })
    
    return matches

def scrape_fotmob():
    """Try Fotmob for today's WC matches"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    url = f"https://www.fotmob.com/api/matches?date={today}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.fotmob.com/",
        "Accept": "application/json",
    }
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
    data = json.loads(resp.read().decode())
    
    matches = []
    for league in data.get("leagues", []):
        if "world cup" not in league.get("name", "").lower() and \
           league.get("id") not in [77, 73]:  # Fotmob WC league IDs
            continue
        for match in league.get("matches", []):
            home = match.get("home", {}).get("name", "")
            away = match.get("away", {}).get("name", "")
            status = match.get("status", {})
            hs = match.get("home", {}).get("score")
            as_ = match.get("away", {}).get("score")
            finished = status.get("finished", False)
            live = status.get("ongoing", False)
            
            start_ts = match.get("status", {}).get("utcTime", 0)
            utc = datetime.fromtimestamp(start_ts/1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if start_ts else ""
            
            matches.append({
                "home":  home,
                "away":  away,
                "hs":    hs if (finished or live) else None,
                "as":    as_ if (finished or live) else None,
                "done":  finished,
                "live":  live,
                "utc":   utc,
                "venue": "",
                "group": "World Cup",
            })
    return matches

def main():
    results = {"updated": datetime.now(timezone.utc).isoformat(), "matches": [], "source": ""}
    
    # Try sources in order
    sources = [
        ("sofascore",  scrape_sofascore),
        ("fotmob",     scrape_fotmob),
        ("wikipedia",  scrape_wikipedia),
    ]
    
    for source_name, fn in sources:
        try:
            print(f"Trying {source_name}...")
            matches = fn()
            if matches:
                results["matches"] = matches
                results["source"] = source_name
                print(f"✓ {source_name}: {len(matches)} matches")
                break
            else:
                print(f"  {source_name}: 0 matches returned")
        except Exception as e:
            print(f"  {source_name} failed: {e}")
    
    if not results["matches"]:
        print("All sources failed — keeping existing scores.json if present")
        if OUTPUT.exists():
            sys.exit(0)
        sys.exit(1)
    
    OUTPUT.write_text(json.dumps(results, indent=2))
    print(f"Written to {OUTPUT}: {len(results['matches'])} matches from {results['source']}")

if __name__ == "__main__":
    main()

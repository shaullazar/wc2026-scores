#!/usr/bin/env python3
"""
WC 2026 Score Scraper — tries multiple sources, keeps best result
"""
import json, re, urllib.request, urllib.error, ssl, sys, traceback
from datetime import datetime, timezone
from pathlib import Path

OUTPUT = Path(__file__).parent / "scores.json"
UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
UA_BOT = "WC2026Dashboard/1.0 (+https://github.com/shaullazar/wc2026-scores)"

def fetch(url, headers=None, timeout=15):
    ctx = ssl.create_default_context()
    h = {"User-Agent": UA_BROWSER, "Accept": "application/json,text/html,*/*", "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    raw = resp.read()
    print(f"  fetch {url[:70]} -> HTTP {resp.status} {len(raw)} bytes")
    return raw.decode("utf-8", errors="replace")

# ── SOURCE 1: Sofascore ───────────────────────────────────────────────────────
def scrape_sofascore():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today}"
    data = json.loads(fetch(url, {"Referer": "https://www.sofascore.com/", "Cache-Control": "no-cache"}))
    matches = []
    for event in data.get("events", []):
        tname = event.get("tournament", {}).get("uniqueTournament", {}).get("name", "")
        if "world cup" not in tname.lower():
            continue
        home = event.get("homeTeam", {}).get("name", "")
        away = event.get("awayTeam", {}).get("name", "")
        hs   = event.get("homeScore", {}).get("current")
        as_  = event.get("awayScore", {}).get("current")
        code = event.get("status", {}).get("code", 0)
        done = code == 100
        live = code in [6, 7, 31]
        ts   = event.get("startTimestamp", 0)
        utc  = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else ""
        matches.append({"home": home, "away": away,
                        "hs": hs if (done or live) else None,
                        "as": as_ if (done or live) else None,
                        "done": done, "live": live, "utc": utc,
                        "venue": "", "group": "World Cup"})
    print(f"  Sofascore: {len(matches)} WC matches")
    return matches

# ── SOURCE 2: Fotmob ──────────────────────────────────────────────────────────
def scrape_fotmob():
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    url = f"https://www.fotmob.com/api/matches?date={today}"
    data = json.loads(fetch(url, {"Referer": "https://www.fotmob.com/"}))
    matches = []
    for league in data.get("leagues", []):
        name = league.get("name", "").lower()
        lid  = league.get("id", 0)
        if "world cup" not in name and lid not in [77, 73, 50]:
            continue
        for m in league.get("matches", []):
            home     = m.get("home", {}).get("name", "")
            away     = m.get("away", {}).get("name", "")
            hs       = m.get("home", {}).get("score")
            as_      = m.get("away", {}).get("score")
            finished = m.get("status", {}).get("finished", False)
            live     = m.get("status", {}).get("ongoing", False)
            ts       = m.get("status", {}).get("utcTime", 0)
            utc      = datetime.fromtimestamp(ts/1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else ""
            matches.append({"home": home, "away": away,
                            "hs": hs if (finished or live) else None,
                            "as": as_ if (finished or live) else None,
                            "done": finished, "live": live, "utc": utc,
                            "venue": "", "group": "World Cup"})
    print(f"  Fotmob: {len(matches)} WC matches")
    return matches

# ── SOURCE 3: Wikipedia group stage (all results) ────────────────────────────
def scrape_wikipedia():
    url = ("https://en.wikipedia.org/w/api.php?action=parse"
           "&page=2026_FIFA_World_Cup_group_stage"
           "&prop=wikitext&format=json")
    data = json.loads(fetch(url, {"User-Agent": UA_BOT}))
    wikitext = data["parse"]["wikitext"]["*"]

    matches = []
    # Match {{football box ... }} templates
    for block in re.findall(r'\{\{[Ff]ootball[\- ]box\b(.*?)\}\}', wikitext, re.DOTALL):
        def get(key):
            r = re.search(rf'\|\s*{re.escape(key)}\s*=\s*([^\n|}}]+)', block)
            return r.group(1).strip() if r else ""

        home  = re.sub(r'\[\[([^|\]]*\|)?([^\]]+)\]\]', r'\2', get("team1"))
        away  = re.sub(r'\[\[([^|\]]*\|)?([^\]]+)\]\]', r'\2', get("team2"))
        score = get("score")
        date  = get("date")
        time_ = get("time")
        venue = re.sub(r'\[\[([^|\]]*\|)?([^\]]+)\]\]', r'\2', get("stadium"))
        group = get("round") or get("group")

        if not home or not away:
            continue

        hs = as_ = None
        sm = re.match(r'(\d+)\s*[–\-]\s*(\d+)', score.replace('&ndash;', '-'))
        if sm:
            hs, as_ = int(sm.group(1)), int(sm.group(2))

        utc = ""
        dt_str = f"{date} {time_}".strip()
        for fmt in ["%d %B %Y %H:%M", "%B %d, %Y %H:%M",
                    "%d %B %Y", "%B %d, %Y"]:
            try:
                dt = datetime.strptime(dt_str, fmt)
                utc = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                break
            except ValueError:
                continue

        matches.append({"home": home.strip(), "away": away.strip(),
                        "hs": hs, "as": as_,
                        "done": hs is not None,
                        "live": False,
                        "utc": utc,
                        "venue": venue.strip(),
                        "group": group.strip()})

    print(f"  Wikipedia: {len(matches)} matches parsed from wikitext")
    return matches

# ── SOURCE 4: BBC Sport ───────────────────────────────────────────────────────
def scrape_bbc():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = (f"https://push.api.bbci.co.uk/batch?t=/data/bbc-morph-football-scores-match-list-data"
           f"/endDate/{today}/startDate/{today}/tournament/world-cup/withPlayerActions/true")
    data = json.loads(fetch(url))
    matches = []
    for block in data.get("payload", []):
        for match in block.get("body", {}).get("matchData", []):
            for m in match.get("tournamentDatesWithEvents", {}).values():
                for event in m:
                    teams = event.get("teams", [])
                    if len(teams) < 2:
                        continue
                    home = teams[0].get("name", {}).get("full", "")
                    away = teams[1].get("name", {}).get("full", "")
                    hs   = teams[0].get("scores", {}).get("match")
                    as_  = teams[1].get("scores", {}).get("match")
                    status = event.get("eventStatus", "")
                    done = status == "RESULT"
                    live = status in ["LIVE", "HALF_TIME"]
                    kickoff = event.get("startTimeInUKHrs", "")
                    matches.append({"home": home, "away": away,
                                    "hs": hs, "as": as_,
                                    "done": done, "live": live,
                                    "utc": kickoff,
                                    "venue": "", "group": "World Cup"})
    print(f"  BBC: {len(matches)} matches")
    return matches

def main():
    existing = {}
    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text())
        except Exception:
            pass

    sources = [
        ("sofascore",  scrape_sofascore),
        ("fotmob",     scrape_fotmob),
        ("bbc",        scrape_bbc),
        ("wikipedia",  scrape_wikipedia),
    ]

    best = []
    best_source = ""
    for name, fn in sources:
        print(f"\nTrying {name}...")
        try:
            result = fn()
            # Prefer source with most done/live matches (most data)
            score = sum(1 for m in result if m.get("done") or m.get("live"))
            total = len(result)
            print(f"  -> {total} total, {score} with scores")
            if total > len(best):
                best = result
                best_source = name
                if score > 0:
                    break  # Found live/scored data — use it
        except Exception as e:
            print(f"  -> FAILED: {e}")
            traceback.print_exc()

    if not best:
        print("\nAll sources failed — keeping existing scores.json")
        sys.exit(0)

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "matches": best,
        "source": best_source
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nWritten {len(best)} matches from '{best_source}' to scores.json")

if __name__ == "__main__":
    main()

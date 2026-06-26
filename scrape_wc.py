#!/usr/bin/env python3
"""
WC 2026 Score Scraper
Uses requests + BeautifulSoup (both available on GitHub Actions ubuntu-latest)
Sources tried in order: Wikipedia HTML → ESPN hidden API → Wikidata SPARQL
"""
import json, re, sys, traceback
from datetime import datetime, timezone
from pathlib import Path

OUTPUT = Path(__file__).parent / "scores.json"

# Install deps if missing (GitHub Actions has pip)
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "beautifulsoup4", "-q"])
    import requests
    from bs4 import BeautifulSoup

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; WC2026ScoreScraper/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
})


# ── SOURCE 1: Wikipedia HTML scrape ──────────────────────────────────────────
def scrape_wikipedia_html():
    """Scrape match results from Wikipedia's WC 2026 group stage HTML page"""
    pages = [
        "2026_FIFA_World_Cup_group_stage",
        "2026_FIFA_World_Cup",
    ]
    for page in pages:
        url = f"https://en.wikipedia.org/wiki/{page}"
        r = SESSION.get(url, timeout=15)
        print(f"  Wikipedia {page}: HTTP {r.status_code} {len(r.text)} bytes")
        if r.status_code != 200:
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        matches = []

        # Find all wikitable rows that look like match results
        # WC tables have: Date | Home | Score | Away | Stadium
        for table in soup.find_all("table", class_=re.compile("wikitable|football")):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 4:
                    continue
                texts = [c.get_text(" ", strip=True) for c in cells]

                # Look for score pattern "X – Y" or "X - Y"
                score_cell = None
                score_idx = -1
                for i, t in enumerate(texts):
                    if re.search(r'^\d+\s*[–\-]\s*\d+$', t.strip()):
                        score_cell = t.strip()
                        score_idx = i
                        break

                if score_cell and score_idx > 0:
                    home = texts[score_idx - 1].strip()
                    away = texts[score_idx + 1].strip() if score_idx + 1 < len(texts) else ""
                    sm = re.match(r'(\d+)\s*[–\-]\s*(\d+)', score_cell)
                    hs, as_ = (int(sm.group(1)), int(sm.group(2))) if sm else (None, None)
                    if home and away and len(home) > 1 and len(away) > 1:
                        matches.append({
                            "home": home, "away": away,
                            "hs": hs, "as": as_,
                            "done": hs is not None,
                            "live": False, "utc": "", "venue": "", "group": "World Cup"
                        })

        if matches:
            print(f"  Found {len(matches)} matches from {page}")
            return matches

    return []


# ── SOURCE 2: ESPN hidden API ─────────────────────────────────────────────────
def scrape_espn():
    """Try ESPN's hidden soccer API"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    slugs = ["fifa.world-cup-2026", "fifa.world", "fifa.worldcup"]
    for slug in slugs:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={today}"
        try:
            r = SESSION.get(url, timeout=10)
            print(f"  ESPN {slug}: HTTP {r.status_code}")
            if r.status_code != 200:
                continue
            data = r.json()
            events = data.get("events", [])
            matches = []
            for e in events:
                comp = e.get("competitions", [{}])[0]
                competitors = comp.get("competitors", [])
                if len(competitors) < 2:
                    continue
                home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                status = comp.get("status", {}).get("type", {})
                done = status.get("completed", False)
                live = status.get("state") == "in"
                hs = int(home.get("score", 0)) if (done or live) else None
                as_ = int(away.get("score", 0)) if (done or live) else None
                start = e.get("date", "")
                matches.append({
                    "home": home.get("team", {}).get("displayName", ""),
                    "away": away.get("team", {}).get("displayName", ""),
                    "hs": hs, "as": as_, "done": done, "live": live,
                    "utc": start, "venue": "", "group": "World Cup"
                })
            if matches:
                print(f"  ESPN {slug}: {len(matches)} matches")
                return matches
        except Exception as e:
            print(f"  ESPN {slug} error: {e}")
    return []


# ── SOURCE 3: Wikidata SPARQL ─────────────────────────────────────────────────
def scrape_wikidata():
    """Query Wikidata for WC 2026 match results via SPARQL"""
    query = """
SELECT ?match ?home ?homeLabel ?away ?awayLabel ?date ?homeScore ?awayScore WHERE {
  ?match wdt:P31 wd:Q16466 .
  ?match wdt:P361 wd:Q11767 .
  ?match wdt:P1706 ?home .
  ?match wdt:P1707 ?away .
  OPTIONAL { ?match wdt:P585 ?date }
  OPTIONAL { ?match wdt:P1654 ?homeScore }
  OPTIONAL { ?match wdt:P1655 ?awayScore }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
LIMIT 200
"""
    url = "https://query.wikidata.org/sparql"
    r = SESSION.get(url, params={"query": query, "format": "json"},
                    headers={"Accept": "application/json"}, timeout=20)
    print(f"  Wikidata SPARQL: HTTP {r.status_code} {len(r.text)} bytes")
    if r.status_code != 200:
        return []

    data = r.json()
    matches = []
    for row in data.get("results", {}).get("bindings", []):
        home  = row.get("homeLabel", {}).get("value", "")
        away  = row.get("awayLabel", {}).get("value", "")
        hs    = row.get("homeScore", {}).get("value")
        as_   = row.get("awayScore", {}).get("value")
        date  = row.get("date", {}).get("value", "")
        if home and away:
            matches.append({
                "home": home, "away": away,
                "hs": int(hs) if hs else None,
                "as": int(as_) if as_ else None,
                "done": hs is not None,
                "live": False,
                "utc": date[:20] if date else "",
                "venue": "", "group": "World Cup"
            })
    print(f"  Wikidata: {len(matches)} matches")
    return matches


# ── SOURCE 4: The Sports DB with correct WC 2026 league ID ───────────────────
def scrape_sportsdb():
    """Search TheSportsDB for WC 2026 league and get recent events"""
    # Search for the correct league ID
    r = SESSION.get(
        "https://www.thesportsdb.com/api/v1/json/3/all_leagues.php?c=International&s=Soccer",
        timeout=10)
    print(f"  SportsDB leagues: HTTP {r.status_code}")
    if r.status_code != 200:
        return []

    data = r.json()
    leagues = data.get("leagues", []) or data.get("countrys", [])
    wc_league = None
    for league in leagues:
        name = (league.get("strLeague") or "").lower()
        if "world cup" in name and "2026" in name:
            wc_league = league
            break
        if "fifa world cup" in name and "under" not in name:
            wc_league = league  # fallback

    if not wc_league:
        print("  SportsDB: no WC league found")
        return []

    lid = wc_league.get("idLeague")
    print(f"  SportsDB: found league {wc_league.get('strLeague')} id={lid}")

    # Get past events
    r2 = SESSION.get(
        f"https://www.thesportsdb.com/api/v1/json/3/eventspastleague.php?id={lid}",
        timeout=10)
    data2 = r2.json()
    events = data2.get("events") or []

    matches = []
    for e in events:
        home = e.get("strHomeTeam", "")
        away = e.get("strAwayTeam", "")
        hs   = e.get("intHomeScore")
        as_  = e.get("intAwayScore")
        utc  = e.get("strTimestamp", "") or e.get("dateEvent", "")
        if home and away:
            matches.append({
                "home": home, "away": away,
                "hs": int(hs) if hs is not None else None,
                "as": int(as_) if as_ is not None else None,
                "done": hs is not None,
                "live": False,
                "utc": utc + "Z" if utc and not utc.endswith("Z") else utc,
                "venue": e.get("strVenue", ""),
                "group": e.get("strLeague", "World Cup")
            })
    print(f"  SportsDB: {len(matches)} past events")
    return matches


def main():
    sources = [
        ("wikipedia",  scrape_wikipedia_html),
        ("espn",       scrape_espn),
        ("sportsdb",   scrape_sportsdb),
        ("wikidata",   scrape_wikidata),
    ]

    best = []
    best_source = ""

    for name, fn in sources:
        print(f"\nTrying {name}...")
        try:
            result = fn()
            scored = sum(1 for m in result if m.get("done"))
            total  = len(result)
            print(f"  -> {total} total, {scored} with scores")
            if total > len(best):
                best = result
                best_source = name
            if scored > 0:
                print(f"  -> Using {name} (has scored matches)")
                break
        except Exception as e:
            print(f"  -> FAILED: {e}")
            traceback.print_exc()

    if not best:
        print("\nAll sources failed — keeping existing scores.json")
        if OUTPUT.exists():
            sys.exit(0)
        sys.exit(1)

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "matches": best,
        "source":  best_source,
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nWritten {len(best)} matches from '{best_source}' to scores.json")


if __name__ == "__main__":
    main()

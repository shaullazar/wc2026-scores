# WC 2026 Score Scraper

Automatically scrapes World Cup 2026 scores every 15 minutes and commits `scores.json` to this repo. The CP-360 dashboard reads this file.

## Setup (5 minutes)

1. Create a new **public** GitHub repo (e.g. `wc2026-scores`)
2. Upload these 3 files: `scrape_wc.py`, `scores.json`, `.github/workflows/scrape.yml`
3. Go to repo **Settings → Actions → General** → set "Workflow permissions" to **Read and write**
4. Copy your raw `scores.json` URL:
   `https://raw.githubusercontent.com/YOUR_USERNAME/wc2026-scores/main/scores.json`
5. Paste that URL into the dashboard when prompted

## How it works

- GitHub Actions runs `scrape_wc.py` every 15 minutes
- The script tries Sofascore → Fotmob → Wikipedia in order
- If any source returns match data it saves to `scores.json` and commits
- The dashboard fetches `scores.json` on load and every 5 minutes
- Zero cost — GitHub Actions free tier gives 2,000 min/month (more than enough)

## Manual trigger

Go to **Actions → WC 2026 Score Scraper → Run workflow** to trigger immediately.

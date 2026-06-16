# World Cup 2026 Dashboard

This project is a dependency-free static dashboard generator. It fetches World Cup data, computes standings and leaderboards locally, and writes a self-contained `index.html`.

## Setup

Run with Python 3.11+:

```sh
python3 scripts/update_dashboard.py
```

Useful flags:

```sh
python3 scripts/update_dashboard.py --dry-run
python3 scripts/update_dashboard.py --force
```

Optional environment variables:

```sh
export TZ=America/New_York
export API_FOOTBALL_KEY=your_api_sports_key
export WORLD_CUP_PROVIDER=api-football
```

If `TZ` is not set, the script uses the machine's local timezone from `datetime.now().astimezone().tzinfo`.

## Data Source

The script defaults to ESPN's keyless soccer scoreboard JSON because it has live fixtures and does not require a secret. This is undocumented, so the parser is isolated behind `fetch_matches()` and logs skipped or missing fields instead of crashing per match.

If `API_FOOTBALL_KEY` is set, the script automatically uses API-Football for `league=1&season=2026`. Keep the key in the environment only; the script never writes it into `index.html`.

## Files

- `scripts/update_dashboard.py`: one standard-library-only updater.
- `index.html`: generated self-contained dashboard.
- `state/state.json`: local last-run hash, timestamps, and summary.
- `cache/`: local timestamped fetched JSON responses for debugging parser breakage.
- `logs/update.log`: local timestamped run log.
- `backups/`: local previous `index.html` copies, retaining the last 20.

The local `state/`, `cache/`, `logs/`, `backups/`, `.vercel/`, and `.env*` paths are ignored by Git and should not be committed. API keys must stay in environment variables only; the updater sends `API_FOOTBALL_KEY` as a request header and does not render it into `index.html`.

## Scheduling

Production updates run through GitHub Actions. The workflow in `.github/workflows/update-dashboard.yml` runs hourly and can also be started manually from the GitHub Actions tab. It regenerates `index.html`, commits it only when data changes, and pushes to `main`; Vercel then deploys the updated static dashboard from GitHub.

The default ESPN provider does not require secrets. To use API-Football in production, add `API_FOOTBALL_KEY` as a GitHub Actions repository secret and set the `WORLD_CUP_PROVIDER` repository variable to `api-football`.

For local-only updates, macOS/Linux cron can still run hourly:

```cron
0 * * * * cd /Users/thalesviniciusf/Desktop/copa && /usr/bin/env python3 scripts/update_dashboard.py
```

Windows Task Scheduler:

Create a basic task that runs hourly. Set the action to:

```text
Program/script: python
Arguments: scripts\update_dashboard.py
Start in: C:\path\to\copa
```

During the tournament, hourly polling is a reasonable default. If you use API-Football's free tier, reduce polling outside match windows to protect the 100 requests/day quota.

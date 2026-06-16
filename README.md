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
- `state/state.json`: last-run hash, timestamps, and summary.
- `cache/`: timestamped fetched JSON responses for debugging parser breakage.
- `logs/update.log`: one timestamped line per run.
- `backups/`: previous `index.html` copies, retaining the last 20.

## Scheduling

macOS/Linux cron, hourly:

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

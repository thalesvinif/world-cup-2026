#!/usr/bin/env python3
"""
Self-updating FIFA World Cup 2026 results dashboard.

Dependency-free by design: only the Python standard library is used.
Provider logic is isolated behind fetch_matches(), which returns normalized match
objects consumed by the local computations and renderer.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
STATE_PATH = ROOT / "state" / "state.json"
CACHE_DIR = ROOT / "cache"
LOG_PATH = ROOT / "logs" / "update.log"
BACKUP_DIR = ROOT / "backups"

API_FOOTBALL_KEY_ENV = "API_FOOTBALL_KEY"
PROVIDER_ENV = "WORLD_CUP_PROVIDER"
TIMEZONE_ENV = "TZ"
TIMEZONE = None
DRY_RUN_MODE = False

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
ESPN_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary"
API_FOOTBALL_FIXTURES_URL = "https://v3.football.api-sports.io/fixtures"
TOURNAMENT_START = dt.date(2026, 6, 11)
TOURNAMENT_END = dt.date(2026, 7, 19)

REQUIRED_HEADINGS = [
    "Resumo",
    "Partidas concluídas",
    "Líderes individuais",
    "Tabelas de pontos",
    "Próximos jogos",
    "Grupos sem estreia",
]

GROUPS = {
    "A": ["Mexico", "South Africa", "Korea Republic", "Czechia"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["United States", "Paraguay", "Australia", "Turkiye"],
    "E": ["Germany", "Curacao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

TEAM_TO_GROUP = {team: group for group, teams in GROUPS.items() for team in teams}

ALIASES = {
    "bosnia-herzegovina": "Bosnia and Herzegovina",
    "bosnia & herzegovina": "Bosnia and Herzegovina",
    "bosnia and herzegovina": "Bosnia and Herzegovina",
    "cape verde islands": "Cape Verde",
    "cape verde": "Cape Verde",
    "colombia": "Colombia",
    "congo dr": "DR Congo",
    "cote d'ivoire": "Ivory Coast",
    "côte d'ivoire": "Ivory Coast",
    "curacao": "Curacao",
    "curaçao": "Curacao",
    "czech republic": "Czechia",
    "czechia": "Czechia",
    "democratic republic of the congo": "DR Congo",
    "dr congo": "DR Congo",
    "england": "England",
    "iran": "Iran",
    "ir iran": "Iran",
    "ivory coast": "Ivory Coast",
    "korea republic": "Korea Republic",
    "new zealand": "New Zealand",
    "south korea": "Korea Republic",
    "turkey": "Turkiye",
    "turkiye": "Turkiye",
    "türkiye": "Turkiye",
    "united states": "United States",
    "usa": "United States",
    "usmnt": "United States",
}

for _team in TEAM_TO_GROUP:
    ALIASES.setdefault(_team.lower(), _team)

FLAGS = {
    "Algeria": "🇩🇿",
    "Argentina": "🇦🇷",
    "Australia": "🇦🇺",
    "Austria": "🇦🇹",
    "Belgium": "🇧🇪",
    "Bosnia and Herzegovina": "🇧🇦",
    "Brazil": "🇧🇷",
    "Canada": "🇨🇦",
    "Cape Verde": "🇨🇻",
    "Colombia": "🇨🇴",
    "Croatia": "🇭🇷",
    "Curacao": "🇨🇼",
    "Czechia": "🇨🇿",
    "DR Congo": "🇨🇩",
    "Ecuador": "🇪🇨",
    "Egypt": "🇪🇬",
    "England": "🏴",
    "France": "🇫🇷",
    "Germany": "🇩🇪",
    "Ghana": "🇬🇭",
    "Haiti": "🇭🇹",
    "Iran": "🇮🇷",
    "Iraq": "🇮🇶",
    "Ivory Coast": "🇨🇮",
    "Japan": "🇯🇵",
    "Jordan": "🇯🇴",
    "Korea Republic": "🇰🇷",
    "Mexico": "🇲🇽",
    "Morocco": "🇲🇦",
    "Netherlands": "🇳🇱",
    "New Zealand": "🇳🇿",
    "Norway": "🇳🇴",
    "Panama": "🇵🇦",
    "Paraguay": "🇵🇾",
    "Portugal": "🇵🇹",
    "Qatar": "🇶🇦",
    "Saudi Arabia": "🇸🇦",
    "Scotland": "🏴",
    "Senegal": "🇸🇳",
    "South Africa": "🇿🇦",
    "Spain": "🇪🇸",
    "Sweden": "🇸🇪",
    "Switzerland": "🇨🇭",
    "Tunisia": "🇹🇳",
    "Turkiye": "🇹🇷",
    "United States": "🇺🇸",
    "Uruguay": "🇺🇾",
    "Uzbekistan": "🇺🇿",
}

TEAM_LABELS_PT = {
    "Australia": "Austrália",
    "Austria": "Áustria",
    "Belgium": "Bélgica",
    "Brazil": "Brasil",
    "Canada": "Canadá",
    "Colombia": "Colômbia",
    "Croatia": "Croácia",
    "Curacao": "Curaçao",
    "Czechia": "Tchéquia",
    "DR Congo": "RD Congo",
    "Ecuador": "Equador",
    "Egypt": "Egito",
    "England": "Inglaterra",
    "France": "França",
    "Germany": "Alemanha",
    "Ghana": "Gana",
    "Iran": "Irã",
    "Iraq": "Iraque",
    "Ivory Coast": "Costa do Marfim",
    "Japan": "Japão",
    "Korea Republic": "Coreia do Sul",
    "Mexico": "México",
    "Morocco": "Marrocos",
    "Netherlands": "Países Baixos",
    "New Zealand": "Nova Zelândia",
    "Norway": "Noruega",
    "Panama": "Panamá",
    "Paraguay": "Paraguai",
    "Portugal": "Portugal",
    "Qatar": "Catar",
    "Saudi Arabia": "Arábia Saudita",
    "Scotland": "Escócia",
    "South Africa": "África do Sul",
    "Spain": "Espanha",
    "Sweden": "Suécia",
    "Switzerland": "Suíça",
    "Tunisia": "Tunísia",
    "Turkiye": "Turquia",
    "United States": "Estados Unidos",
    "Uruguay": "Uruguai",
    "Uzbekistan": "Uzbequistão",
}

WEEKDAYS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
MONTHS_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def local_timezone() -> dt.tzinfo:
    configured = TIMEZONE or os.environ.get(TIMEZONE_ENV)
    if configured:
        try:
            return ZoneInfo(configured)
        except Exception:
            log_warning(f"Invalid timezone {configured!r}; using system local timezone")
    return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc


def log_line(level: str, message: str, *, dry_run: bool = False) -> None:
    line = f"{utc_now().isoformat()}Z [{level.upper()}] {message}\n"
    if dry_run or DRY_RUN_MODE:
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)


def log_warning(message: str) -> None:
    log_line("warning", message)


def normalize_team(name: str | None) -> str:
    raw = (name or "").strip()
    key = re.sub(r"\s+", " ", raw).lower()
    key = key.replace("u.s.", "usa")
    return ALIASES.get(key, raw)


def parse_int(value, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def json_dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(data) -> str:
    return hashlib.sha256(json_dumps(data).encode("utf-8")).hexdigest()


def fetch_json(url: str, *, headers: dict[str, str] | None = None, cache_prefix: str = "response", write_cache: bool = True):
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "wc2026-static-dashboard/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
    if write_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        suffix = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        target = CACHE_DIR / f"{stamp}_{cache_prefix}_{suffix}.json"
        target.write_bytes(body)
    return json.loads(body.decode("utf-8"))


def infer_group(home: str, away: str, provider_group: str | None = None) -> str:
    if provider_group:
        match = re.search(r"Group\s+([A-L])", provider_group, re.I)
        if match:
            return match.group(1).upper()
        if provider_group.strip().upper() in GROUPS:
            return provider_group.strip().upper()
    home_group = TEAM_TO_GROUP.get(home)
    away_group = TEAM_TO_GROUP.get(away)
    if home_group and home_group == away_group:
        return home_group
    return home_group or away_group or "?"


def blank_match(match_id: str) -> dict:
    return {
        "id": match_id,
        "date": None,
        "status": "scheduled",
        "finished": False,
        "group": "?",
        "home_team": "",
        "away_team": "",
        "home_score": None,
        "away_score": None,
        "goals": [],
        "cards": [],
        "team_stats": {},
        "goalkeeper_saves": [],
    }


def parse_espn_scoreboard_event(event: dict) -> dict | None:
    match = blank_match(str(event.get("id") or ""))
    match["date"] = (parse_datetime(event.get("date")) or utc_now()).isoformat()
    status_type = ((event.get("status") or {}).get("type") or {})
    status_name = str(status_type.get("name") or status_type.get("description") or "").lower()
    match["finished"] = bool(status_type.get("completed")) or status_name in {"final", "ft", "full time"}
    match["status"] = "finished" if match["finished"] else ("live" if "in" in status_name else "scheduled")

    competitions = event.get("competitions") or []
    competition = competitions[0] if competitions else {}
    competitors = competition.get("competitors") or []
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home or not away:
        return None
    home_team = normalize_team(((home.get("team") or {}).get("displayName")) or ((home.get("team") or {}).get("name")))
    away_team = normalize_team(((away.get("team") or {}).get("displayName")) or ((away.get("team") or {}).get("name")))
    if not home_team or not away_team:
        return None
    match["home_team"] = home_team
    match["away_team"] = away_team
    match["home_score"] = parse_int(home.get("score"), None)
    match["away_score"] = parse_int(away.get("score"), None)
    match["group"] = infer_group(home_team, away_team, event.get("group", {}).get("name") if isinstance(event.get("group"), dict) else None)
    return match


def parse_espn_summary(match: dict, summary: dict) -> dict:
    try:
        boxscore = summary.get("boxscore") or {}
        for team_block in boxscore.get("teams") or []:
            team_name = normalize_team(((team_block.get("team") or {}).get("displayName")) or ((team_block.get("team") or {}).get("name")))
            stats = {}
            for item in team_block.get("statistics") or []:
                name = str(item.get("name") or item.get("label") or "").lower()
                display = str(item.get("displayValue") or item.get("value") or "")
                if "shots on goal" in name or name in {"sog", "shotsongoal"}:
                    stats["shots_on_goal"] = parse_int(re.search(r"\d+", display).group(0) if re.search(r"\d+", display) else display)
            if team_name and stats:
                match["team_stats"].setdefault(team_name, {}).update(stats)
    except Exception as exc:
        log_warning(f"ESPN boxscore parse skipped for {match.get('id')}: {exc}")

    for play in summary.get("scoringPlays") or []:
        try:
            team_name = normalize_team(((play.get("team") or {}).get("displayName")) or ((play.get("team") or {}).get("name")))
            scorer = ""
            athletes = play.get("participants") or play.get("athletes") or []
            if athletes:
                athlete = athletes[0].get("athlete") if isinstance(athletes[0], dict) else {}
                scorer = athlete.get("displayName") or athlete.get("fullName") or ""
            text = str(play.get("text") or "")
            own_goal = bool(re.search(r"\bown goal\b|\bog\b", text, re.I))
            if scorer and team_name:
                match["goals"].append({"player": scorer, "team": team_name, "own_goal": own_goal})
        except Exception as exc:
            log_warning(f"ESPN scoring play skipped for {match.get('id')}: {exc}")

    for detail in (summary.get("details") or summary.get("keyEvents") or []):
        try:
            text = str(detail.get("text") or detail.get("description") or "")
            lower = text.lower()
            if "yellow" not in lower and "red" not in lower:
                continue
            team_name = normalize_team(((detail.get("team") or {}).get("displayName")) or ((detail.get("team") or {}).get("name")))
            card_type = "red" if "red" in lower else "yellow"
            match["cards"].append({"team": team_name, "type": card_type})
        except Exception as exc:
            log_warning(f"ESPN card detail skipped for {match.get('id')}: {exc}")
    return match


def fetch_matches_from_espn(*, write_cache: bool = True) -> list[dict]:
    events_by_id = {}
    day = TOURNAMENT_START
    while day <= TOURNAMENT_END:
        params = urllib.parse.urlencode({"dates": day.strftime("%Y%m%d")})
        data = fetch_json(f"{ESPN_SCOREBOARD_URL}?{params}", cache_prefix=f"espn_scoreboard_{day:%Y%m%d}", write_cache=write_cache)
        for event in data.get("events") or []:
            event_id = str(event.get("id") or "")
            if event_id:
                events_by_id[event_id] = event
        day += dt.timedelta(days=1)

    matches = []
    for event in events_by_id.values():
        try:
            match = parse_espn_scoreboard_event(event)
            if not match:
                log_warning("ESPN event skipped because home/away teams were missing")
                continue
            if match.get("status") in {"live", "finished"}:
                try:
                    params = urllib.parse.urlencode({"event": match["id"]})
                    summary = fetch_json(f"{ESPN_SUMMARY_URL}?{params}", cache_prefix=f"espn_summary_{match['id']}", write_cache=write_cache)
                    match = parse_espn_summary(match, summary)
                except Exception as exc:
                    log_warning(f"ESPN summary enrichment skipped for {match.get('id')}: {exc}")
            matches.append(match)
        except Exception as exc:
            log_warning(f"ESPN event skipped: {exc}")
    return matches


def parse_api_football_fixture(item: dict) -> dict | None:
    fixture = item.get("fixture") or {}
    teams = item.get("teams") or {}
    goals = item.get("goals") or {}
    league = item.get("league") or {}
    match = blank_match(str(fixture.get("id") or ""))
    match["date"] = (parse_datetime(fixture.get("date")) or utc_now()).isoformat()
    home_team = normalize_team(((teams.get("home") or {}).get("name")))
    away_team = normalize_team(((teams.get("away") or {}).get("name")))
    if not home_team or not away_team:
        return None
    match["home_team"] = home_team
    match["away_team"] = away_team
    match["home_score"] = goals.get("home")
    match["away_score"] = goals.get("away")
    status_short = ((fixture.get("status") or {}).get("short") or "").upper()
    match["finished"] = status_short in {"FT", "AET", "PEN"}
    match["status"] = "finished" if match["finished"] else ("live" if status_short in {"1H", "HT", "2H", "ET", "P"} else "scheduled")
    match["group"] = infer_group(home_team, away_team, league.get("round"))
    for event in item.get("events") or []:
        event_type = str(event.get("type") or "").lower()
        detail = str(event.get("detail") or "")
        team_name = normalize_team(((event.get("team") or {}).get("name")))
        player = ((event.get("player") or {}).get("name")) or ""
        if event_type == "goal" and player and team_name:
            match["goals"].append({"player": player, "team": team_name, "own_goal": "own" in detail.lower()})
        if event_type == "card":
            card_type = "red" if "red" in detail.lower() else "yellow"
            match["cards"].append({"team": team_name, "type": card_type})
    for stat_team in item.get("statistics") or []:
        team_name = normalize_team(((stat_team.get("team") or {}).get("name")))
        for stat in stat_team.get("statistics") or []:
            if str(stat.get("type") or "").lower() == "shots on goal":
                match["team_stats"].setdefault(team_name, {})["shots_on_goal"] = parse_int(stat.get("value"))
    return match


def fetch_matches_from_api_football(*, write_cache: bool = True) -> list[dict]:
    key = os.environ.get(API_FOOTBALL_KEY_ENV)
    if not key:
        raise RuntimeError(f"{API_FOOTBALL_KEY_ENV} is not set")
    params = urllib.parse.urlencode({"league": "1", "season": "2026"})
    headers = {"x-apisports-key": key, "User-Agent": "wc2026-static-dashboard/1.0"}
    data = fetch_json(f"{API_FOOTBALL_FIXTURES_URL}?{params}", headers=headers, cache_prefix="api_football_fixtures", write_cache=write_cache)
    matches = []
    for item in data.get("response") or []:
        try:
            match = parse_api_football_fixture(item)
            if match:
                matches.append(match)
        except Exception as exc:
            log_warning(f"API-Football fixture skipped: {exc}")
    return matches


def fetch_matches(*, write_cache: bool = True) -> list[dict]:
    """Return normalized match objects; swap provider internals here only."""
    provider = os.environ.get(PROVIDER_ENV, "").strip().lower()
    if provider in {"api-football", "apifootball", "api_football"} or (not provider and os.environ.get(API_FOOTBALL_KEY_ENV)):
        return fetch_matches_from_api_football(write_cache=write_cache)
    return fetch_matches_from_espn(write_cache=write_cache)


def completed_matches(matches: list[dict]) -> list[dict]:
    return [m for m in matches if m.get("finished") and m.get("home_score") is not None and m.get("away_score") is not None]


def compute_standings(matches: list[dict]) -> dict[str, list[dict]]:
    standings = {
        group: {
            team: {"team": team, "group": group, "played": 0, "wins": 0, "draws": 0, "losses": 0, "gf": 0, "ga": 0, "gd": 0, "pts": 0}
            for team in teams
        }
        for group, teams in GROUPS.items()
    }
    for match in completed_matches(matches):
        group = match.get("group")
        home = match.get("home_team")
        away = match.get("away_team")
        if group not in standings or home not in standings[group] or away not in standings[group]:
            continue
        hs = parse_int(match.get("home_score"))
        as_ = parse_int(match.get("away_score"))
        h = standings[group][home]
        a = standings[group][away]
        h["played"] += 1
        a["played"] += 1
        h["gf"] += hs
        h["ga"] += as_
        a["gf"] += as_
        a["ga"] += hs
        if hs > as_:
            h["wins"] += 1
            a["losses"] += 1
            h["pts"] += 3
        elif hs < as_:
            a["wins"] += 1
            h["losses"] += 1
            a["pts"] += 3
        else:
            h["draws"] += 1
            a["draws"] += 1
            h["pts"] += 1
            a["pts"] += 1
    output = {}
    for group, table in standings.items():
        rows = []
        for row in table.values():
            row["gd"] = row["gf"] - row["ga"]
            rows.append(row)
        output[group] = sorted(rows, key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["team"]))
    return output


def compute_totals(matches: list[dict]) -> dict:
    done = completed_matches(matches)
    teams = set()
    goals = 0
    yellow = 0
    red = 0
    for match in done:
        teams.add(match.get("home_team"))
        teams.add(match.get("away_team"))
        goals += parse_int(match.get("home_score")) + parse_int(match.get("away_score"))
        for card in match.get("cards") or []:
            if card.get("type") == "red":
                red += 1
            elif card.get("type") == "yellow":
                yellow += 1
    return {"games_played": len(done), "goals": goals, "teams": len([t for t in teams if t]), "yellow_cards": yellow, "red_cards": red}


def compute_goal_scorers(matches: list[dict]) -> list[dict]:
    scorers = {}
    appearances = {}
    for match in completed_matches(matches):
        for team in [match.get("home_team"), match.get("away_team")]:
            appearances[team] = appearances.get(team, 0) + 1
        for goal in match.get("goals") or []:
            if goal.get("own_goal"):
                continue
            player = goal.get("player")
            team = goal.get("team")
            if not player or not team:
                continue
            key = (player, team)
            scorers[key] = scorers.get(key, 0) + 1
    rows = []
    for (player, team), goals in scorers.items():
        played = max(1, appearances.get(team, 1))
        rows.append({"player": player, "team": team, "goals": goals, "avg": goals / played})
    return sorted(rows, key=lambda r: (-r["goals"], -r["avg"], r["player"]))[:5]


def non_own_goals_for(match: dict, team: str) -> int:
    counted = [g for g in match.get("goals") or [] if g.get("team") == team and not g.get("own_goal")]
    if counted:
        return len(counted)
    if team == match.get("home_team"):
        return parse_int(match.get("home_score"))
    if team == match.get("away_team"):
        return parse_int(match.get("away_score"))
    return 0


def compute_goalkeepers(matches: list[dict]) -> list[dict]:
    saves_by_team = {}
    played_by_team = {}
    explicit = {}
    for match in completed_matches(matches):
        for team in [match.get("home_team"), match.get("away_team")]:
            played_by_team[team] = played_by_team.get(team, 0) + 1
        for save in match.get("goalkeeper_saves") or []:
            player = save.get("player") or f"{save.get('team')} goalkeeper"
            team = save.get("team")
            if not team:
                continue
            key = (player, team)
            explicit[key] = explicit.get(key, 0) + parse_int(save.get("saves"))
        if explicit:
            continue
        home = match.get("home_team")
        away = match.get("away_team")
        home_sog = parse_int((match.get("team_stats") or {}).get(home, {}).get("shots_on_goal"))
        away_sog = parse_int((match.get("team_stats") or {}).get(away, {}).get("shots_on_goal"))
        saves_by_team[home] = saves_by_team.get(home, 0) + max(0, away_sog - non_own_goals_for(match, away))
        saves_by_team[away] = saves_by_team.get(away, 0) + max(0, home_sog - non_own_goals_for(match, home))
    rows = []
    source = explicit if explicit else {(f"{team} goalkeeper", team): saves for team, saves in saves_by_team.items()}
    for (player, team), saves in source.items():
        played = max(1, played_by_team.get(team, 1))
        rows.append({"player": player, "team": team, "saves": saves, "avg": saves / played})
    return sorted(rows, key=lambda r: (-r["saves"], -r["avg"], r["player"]))[:5]


def groups_not_started(standings: dict[str, list[dict]]) -> list[str]:
    return [group for group, rows in standings.items() if sum(row["played"] for row in rows) == 0]


def upcoming_matches(matches: list[dict], limit: int = 8) -> list[dict]:
    now = utc_now()
    rows = []
    for match in matches:
        when = parse_datetime(match.get("date"))
        if not when or match.get("finished"):
            continue
        if when >= now or match.get("status") == "scheduled":
            rows.append(match)
    return sorted(rows, key=lambda m: m.get("date") or "")[:limit]


def read_existing_style() -> str:
    if INDEX_PATH.exists():
        text = INDEX_PATH.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"<style[^>]*>(.*?)</style>", text, re.S | re.I)
        if match and "shadcn-dashboard-v5" in match.group(1):
            return match.group(1).strip()
    return FALLBACK_CSS.strip()


def e(value) -> str:
    return html.escape(str(value), quote=True)


def flag(team: str) -> str:
    return FLAGS.get(team, "🏳️")


def team_label(team: str) -> str:
    return TEAM_LABELS_PT.get(team, team)


def format_time(value: str | None, tz: dt.tzinfo) -> str:
    parsed = parse_datetime(value)
    if not parsed:
        return "A definir"
    local = parsed.astimezone(tz)
    weekday = WEEKDAYS_PT[local.weekday()]
    month = MONTHS_PT[local.month - 1]
    return f"{weekday}, {local.day:02d} {month} {local.year} {local:%H:%M} {local:%Z}"


def team_cell(team: str) -> str:
    return f'<span class="flag">{e(flag(team))}</span><span>{e(team_label(team))}</span>'


def match_local_date(match: dict, tz: dt.tzinfo) -> dt.date | None:
    parsed = parse_datetime(match.get("date"))
    if not parsed:
        return None
    return parsed.astimezone(tz).date()


def format_day_label(day: dt.date) -> str:
    return f"{WEEKDAYS_PT[day.weekday()]}, {day.day:02d} {MONTHS_PT[day.month - 1]} {day.year}"


def result_class(match: dict, side: str) -> str:
    hs = parse_int(match.get("home_score"))
    as_ = parse_int(match.get("away_score"))
    if hs == as_:
        return "draw"
    home_won = hs > as_
    if (side == "home" and home_won) or (side == "away" and not home_won):
        return "win"
    return "loss"


def render_dashboard(payload: dict, style: str, tz: dt.tzinfo) -> str:
    matches = payload["matches"]
    standings = payload["standings"]
    totals = payload["totals"]
    updated = payload["updated_local"]
    completed = sorted(completed_matches(matches), key=lambda m: m.get("date") or "", reverse=True)
    upcoming = upcoming_matches(matches)
    scorers = payload["scorers"]
    keepers = payload["goalkeepers"]
    inactive = payload["groups_not_started"]

    stats_html = "".join(
        f'<div class="metric"><span>{e(label)}</span><strong>{e(value)}</strong><small>{e(caption)}</small></div>'
        for label, value, caption in [
            ("Jogos disputados", totals["games_played"], "Apitos finais"),
            ("Gols marcados", totals["goals"], "Total do torneio"),
            ("Seleções em jogo", totals["teams"], "Com ao menos uma partida"),
            ("Cartões amarelos", totals["yellow_cards"], "Disciplina"),
            ("Cartões vermelhos", totals["red_cards"], "Expulsões"),
        ]
    )

    today = utc_now().astimezone(tz).date()
    recent_days = {today, today - dt.timedelta(days=1)}
    completed_by_day: dict[dt.date, list[dict]] = {}
    for match in completed:
        day = match_local_date(match, tz)
        if day:
            completed_by_day.setdefault(day, []).append(match)

    match_day_groups = []
    hidden_day_count = 0
    visible_match_count = 0
    for day in sorted(completed_by_day, reverse=True):
        hidden = day not in recent_days
        hidden_day_count += int(hidden)
        visible_match_count += 0 if hidden else len(completed_by_day[day])
        day_rows = []
        for match in completed_by_day[day]:
            day_rows.append(
                f"""
                <article class="match-card">
                  <div class="match-meta"><span>Grupo {e(match.get('group', '?'))}</span><time>{e(format_time(match.get('date'), tz))}</time></div>
                  <div class="scoreline">
                    <div class="team {result_class(match, 'home')}">{team_cell(match.get('home_team', ''))}</div>
                    <div class="score">{e(match.get('home_score'))}<span>-</span>{e(match.get('away_score'))}</div>
                    <div class="team {result_class(match, 'away')}">{team_cell(match.get('away_team', ''))}</div>
                  </div>
                </article>
                """
            )
        match_day_groups.append(
            f"""
            <div class="match-day" data-match-day="{e(day.isoformat())}"{" hidden" if hidden else ""}>
              <h3 class="day-heading">{e(format_day_label(day))}</h3>
              {''.join(day_rows)}
            </div>
            """
        )
    no_recent = '<p class="empty" id="no-recent-matches">Nenhuma partida concluída hoje ou ontem.</p>' if completed and not visible_match_count else ""
    load_more = '<button class="load-more" type="button" data-load-more>carregar mais</button>' if hidden_day_count else ""
    completed_html = "\n".join(match_day_groups) + no_recent + load_more if match_day_groups else '<p class="empty">Nenhuma partida concluída processada ainda.</p>'

    scorer_rows = "".join(
        f"<tr><td>{e(idx)}</td><td class=\"club\">{team_cell(row['team'])}</td><td>{e(row['player'])}</td><td>{e(row['goals'])}</td><td>{row['avg']:.2f}</td></tr>"
        for idx, row in enumerate(scorers, 1)
    ) or '<tr><td colspan="5">Nenhum dado de artilharia processado ainda.</td></tr>'
    keeper_rows = "".join(
        f"<tr><td>{e(idx)}</td><td class=\"club\">{team_cell(row['team'])}</td><td>{e(row['player'])}</td><td>{e(row['saves'])}</td><td>{row['avg']:.2f}</td></tr>"
        for idx, row in enumerate(keepers, 1)
    ) or '<tr><td colspan="5">Nenhum dado de defesas processado ainda.</td></tr>'

    table_html = []
    for group in sorted(standings):
        leader = standings[group][0] if standings[group] else None
        rows = "".join(
            f"""
            <tr>
              <td class="club">{team_cell(row['team'])}</td>
              <td>{row['played']}</td><td>{row['wins']}</td><td>{row['draws']}</td><td>{row['losses']}</td>
              <td>{row['gf']}</td><td>{row['ga']}</td><td>{row['gd']}</td><td><strong>{row['pts']}</strong></td>
            </tr>
            """
            for row in standings[group]
        )
        table_html.append(
            f"""
            <section class="group-table">
              <div class="table-title"><h3>Grupo {e(group)}</h3><span>{team_cell(leader['team']) if leader else 'A definir'} lidera</span></div>
              <table>
                <thead><tr><th>Seleção</th><th>J</th><th>V</th><th>E</th><th>D</th><th>GP</th><th>GC</th><th>SG</th><th>Pts</th></tr></thead>
                <tbody>{rows}</tbody>
              </table>
            </section>
            """
        )

    next_rows = "".join(
        f"""
        <article class="fixture">
          <div>{team_cell(match.get('home_team', ''))}<span class="versus">vs</span>{team_cell(match.get('away_team', ''))}</div>
          <time>{e(format_time(match.get('date'), tz))}</time>
          <span class="badge">Grupo {e(match.get('group', '?'))}</span>
        </article>
        """
        for match in upcoming
    ) or '<p class="empty">Nenhum próximo jogo processado.</p>'

    inactive_html = "".join(f"<span>Grupo {e(group)}</span>" for group in inactive) or "<span>Todos os grupos já começaram.</span>"

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Copa do Mundo FIFA 2026 - Painel de Resultados</title>
  <style>
{style}
  </style>
</head>
<body>
  <header class="site-header">
    <div class="hero-copy">
      <p class="eyebrow">Copa do Mundo FIFA 2026</p>
      <h1>Painel de Resultados</h1>
      <p class="dek">Resultados de jogos, tabelas e líderes individuais em um painel ao vivo do torneio.</p>
    </div>
    <div class="updated"><span>Última atualização</span><strong>{e(updated)}</strong></div>
  </header>

  <main>
    <section class="section-block">
      <div class="section-heading"><h2>Resumo</h2><p>Totais do torneio a partir das partidas processadas.</p></div>
      <div class="metrics">{stats_html}</div>
    </section>

    <section class="section-block">
      <div class="section-heading"><h2>Partidas concluídas</h2><p>Últimos jogos finalizados, ordenados pelo horário de início.</p></div>
      <div class="matches">{completed_html}</div>
    </section>

    <section class="section-block">
      <div class="section-heading"><h2>Líderes individuais</h2><p>Principais desempenhos individuais a partir dos dados disponíveis.</p></div>
      <div class="leaderboards">
        <div>
          <h3>Artilheiros</h3>
          <table><thead><tr><th>#</th><th>Seleção</th><th>Jogador</th><th>G</th><th>Média</th></tr></thead><tbody>{scorer_rows}</tbody></table>
        </div>
        <div>
          <h3>Goleiros por defesas</h3>
          <table><thead><tr><th>#</th><th>Seleção</th><th>Jogador</th><th>Defesas</th><th>Média</th></tr></thead><tbody>{keeper_rows}</tbody></table>
        </div>
      </div>
    </section>

    <section class="section-block">
      <div class="section-heading"><h2>Tabelas de pontos</h2><p>Classificação dos grupos ordenada por pontos, saldo de gols e gols marcados.</p></div>
      <div class="tables">{''.join(table_html)}</div>
    </section>

    <section class="section-block">
      <div class="section-heading"><h2>Próximos jogos</h2><p>Partidas futuras a partir da tabela processada.</p></div>
      <div class="fixtures">{next_rows}</div>
    </section>

    <section class="section-block">
      <div class="section-heading"><h2>Grupos sem estreia</h2><p>Grupos que ainda aguardam o primeiro resultado concluído.</p></div>
      <div class="chips">{inactive_html}</div>
    </section>
  </main>
  <script>
    (() => {{
      const button = document.querySelector("[data-load-more]");
      if (!button) return;

      const showNextDay = () => {{
        const nextDay = document.querySelector(".match-day[hidden]");
        if (!nextDay) {{
          button.hidden = true;
          return;
        }}

        nextDay.hidden = false;
        const noRecent = document.getElementById("no-recent-matches");
        if (noRecent) noRecent.hidden = true;

        if (!document.querySelector(".match-day[hidden]")) {{
          button.hidden = true;
        }}
      }};

      button.addEventListener("click", showNextDay);
    }})();
  </script>
</body>
</html>
"""


def validate(matches: list[dict], rendered: str) -> None:
    if not matches:
        raise RuntimeError("Refusing to write: zero matches were parsed")
    missing = [heading for heading in REQUIRED_HEADINGS if f">{heading}<" not in rendered]
    if missing:
        raise RuntimeError(f"Refusing to write: rendered HTML is missing headings: {', '.join(missing)}")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp_name, path)


def backup_index() -> None:
    if not INDEX_PATH.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_DIR / f"index_{stamp}.html"
    backup.write_text(INDEX_PATH.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
    backups = sorted(BACKUP_DIR.glob("index_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[20:]:
        old.unlink(missing_ok=True)


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log_warning("Existing state/state.json is invalid JSON; ignoring it")
    return {}


def build_payload(matches: list[dict], tz: dt.tzinfo) -> dict:
    standings = compute_standings(matches)
    return {
        "matches": sorted(matches, key=lambda m: (m.get("date") or "", m.get("id") or "")),
        "standings": standings,
        "totals": compute_totals(matches),
        "scorers": compute_goal_scorers(matches),
        "goalkeepers": compute_goalkeepers(matches),
        "groups_not_started": groups_not_started(standings),
        "updated_local": utc_now().astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def data_only_payload(payload: dict) -> dict:
    return {
        "matches": payload["matches"],
        "standings": payload["standings"],
        "totals": payload["totals"],
        "scorers": payload["scorers"],
        "goalkeepers": payload["goalkeepers"],
        "groups_not_started": payload["groups_not_started"],
    }


def main(argv: list[str] | None = None) -> int:
    global DRY_RUN_MODE
    parser = argparse.ArgumentParser(description="Update the static FIFA World Cup 2026 dashboard.")
    parser.add_argument("--force", action="store_true", help="Rewrite index.html even when the data hash is unchanged.")
    parser.add_argument("--dry-run", action="store_true", help="Print a JSON summary and do not write index/state/log/cache files.")
    args = parser.parse_args(argv)
    DRY_RUN_MODE = args.dry_run

    tz = local_timezone()
    try:
        matches = fetch_matches(write_cache=not args.dry_run)
        payload = build_payload(matches, tz)
        data_hash = stable_hash(data_only_payload(payload))
        state = load_state()
        changed = data_hash != state.get("data_hash")
        style = read_existing_style()
        rendered = render_dashboard(payload, style, tz)
        validate(matches, rendered)
        summary = {
            "provider": os.environ.get(PROVIDER_ENV) or ("api-football" if os.environ.get(API_FOOTBALL_KEY_ENV) else "espn"),
            "matches": len(matches),
            "finished": len(completed_matches(matches)),
            "data_hash": data_hash,
            "previous_hash": state.get("data_hash"),
            "changed": changed,
            "would_write": bool(args.force or changed),
        }
        if args.dry_run:
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        if args.force or changed:
            backup_index()
            atomic_write(INDEX_PATH, rendered)
            state_doc = {
                "data_hash": data_hash,
                "last_run_utc": utc_now().isoformat(),
                "summary": summary,
            }
            atomic_write(STATE_PATH, json.dumps(state_doc, indent=2, sort_keys=True) + "\n")
            log_line("info", f"updated index.html matches={len(matches)} finished={summary['finished']} hash={data_hash}")
        else:
            log_line("info", f"no data change matches={len(matches)} finished={summary['finished']} hash={data_hash}")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        log_line("error", str(exc), dry_run=args.dry_run)
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


FALLBACK_CSS = """
/* shadcn-dashboard-v5 */
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap");
:root {
  color-scheme: light;
  --background: #fafafa;
  --foreground: #09090b;
  --card: #ffffff;
  --card-foreground: #09090b;
  --muted: #f4f4f5;
  --muted-foreground: #71717a;
  --border: #e4e4e7;
  --primary: #18181b;
  --primary-foreground: #fafafa;
  --accent: #f4f4f5;
  --accent-foreground: #18181b;
  --ring: #a1a1aa;
  --success: #dcfce7;
  --success-foreground: #166534;
  --warning: #fef3c7;
  --warning-foreground: #92400e;
  --destructive: #fee2e2;
  --destructive-foreground: #991b1b;
  --radius: 8px;
  --shadow: 0 1px 2px rgb(0 0 0 / 0.04);
}
* { box-sizing: border-box; }
html { background: var(--background); }
body {
  margin: 0;
  min-width: 320px;
  background:
    linear-gradient(180deg, #ffffff 0, var(--background) 340px);
  color: var(--foreground);
  font: 14px/1.5 "Inter", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  text-rendering: optimizeLegibility;
}
strong, b, th, h1, h2, h3 { font-weight: 600; }
.site-header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-end;
  padding: 36px max(20px, 5vw) 26px;
  border-bottom: 1px solid var(--border);
}
.hero-copy { max-width: 760px; }
.eyebrow {
  margin: 0 0 8px;
  color: var(--muted-foreground);
  text-transform: uppercase;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
}
h1, h2, h3, p { overflow-wrap: anywhere; }
h1 { margin: 0; font-size: clamp(38px, 5vw, 72px); line-height: .95; letter-spacing: 0; }
h2 { margin: 0; font-size: 24px; line-height: 1.15; letter-spacing: 0; }
h3 { margin: 0; font-size: 15px; line-height: 1.25; letter-spacing: 0; }
.dek { max-width: 560px; margin: 14px 0 0; color: var(--muted-foreground); font-size: 16px; }
main {
  display: grid;
  gap: 34px;
  padding: 28px max(20px, 5vw) 60px;
}
section { min-width: 0; }
.section-block { display: grid; gap: 14px; }
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
}
.section-heading p {
  max-width: 460px;
  margin: 0;
  color: var(--muted-foreground);
  text-align: right;
}
.updated {
  display: grid;
  gap: 6px;
  justify-items: end;
  min-width: 230px;
  color: var(--muted-foreground);
}
.updated span { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0; }
.updated strong {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  color: var(--foreground);
  box-shadow: var(--shadow);
  white-space: nowrap;
}
.metrics, .leaderboards, .tables { display: grid; gap: 12px; }
.metrics { grid-template-columns: repeat(5, minmax(130px, 1fr)); }
.metric, .match-card, .leaderboards > div, .group-table, .fixture {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
.metric {
  display: grid;
  align-content: space-between;
  min-height: 128px;
  padding: 16px;
}
.metric span { display: block; color: var(--muted-foreground); font-size: 13px; font-weight: 600; }
.metric strong { display: block; margin-top: 10px; font-size: 34px; line-height: 1; letter-spacing: 0; }
.metric small { margin-top: 12px; color: var(--muted-foreground); font-size: 12px; }
.matches, .fixtures { display: grid; gap: 10px; }
.match-day { display: grid; gap: 10px; }
.match-day[hidden] { display: none; }
.day-heading {
  margin-top: 4px;
  color: var(--muted-foreground);
  font-size: 13px;
}
.match-card { padding: 14px; transition: border-color .15s ease, box-shadow .15s ease; }
.match-card:hover { border-color: var(--ring); box-shadow: 0 8px 24px rgb(0 0 0 / 0.06); }
.match-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  color: var(--muted-foreground);
  font-size: 13px;
}
.match-meta span, .badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--muted);
  color: var(--accent-foreground);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.scoreline {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
}
.team {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 44px;
  padding: 9px 11px;
  border: 1px solid transparent;
  border-radius: calc(var(--radius) - 2px);
  font-weight: 600;
}
.team span:last-child, .club span:last-child, .table-title span span:last-child { overflow-wrap: anywhere; }
.team.away { justify-content: flex-end; text-align: right; }
.win { background: var(--success); color: var(--success-foreground); border-color: #bbf7d0; }
.draw { background: var(--muted); color: var(--foreground); border-color: var(--border); }
.loss { background: var(--destructive); color: var(--destructive-foreground); border-color: #fecaca; }
.score {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 82px;
  min-height: 44px;
  padding: 6px 10px;
  border-radius: calc(var(--radius) - 2px);
  background: var(--primary);
  color: var(--primary-foreground);
  font-size: 24px;
  font-weight: 600;
  white-space: nowrap;
}
.score span { color: #a1a1aa; margin: 0 5px; }
.flag { flex: 0 0 auto; line-height: 1; }
.leaderboards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.leaderboards > div { padding: 16px; overflow-x: auto; }
.leaderboards h3 { margin-bottom: 12px; }
.tables { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.group-table { padding: 14px; overflow-x: auto; }
.table-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.table-title > span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted-foreground);
  font-size: 12px;
  font-weight: 600;
  text-align: right;
}
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td {
  padding: 8px 7px;
  border-bottom: 1px solid var(--border);
  text-align: right;
  white-space: nowrap;
}
tbody tr:last-child td { border-bottom: 0; }
th {
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0;
}
th:first-child, td:first-child { text-align: left; }
.club, .fixture > div, .table-title > span {
  min-width: 0;
}
.club, .fixture > div {
  display: flex;
  align-items: center;
  gap: 7px;
}
.fixture {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 14px;
  padding: 13px 14px;
}
.fixture > div { flex-wrap: wrap; font-weight: 600; }
.fixture time { color: var(--muted-foreground); white-space: nowrap; }
.versus { color: var(--muted-foreground); font-weight: 600; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; }
.chips span {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 11px;
  box-shadow: var(--shadow);
  font-size: 13px;
  font-weight: 600;
}
.empty {
  margin: 0;
  padding: 16px;
  color: var(--muted-foreground);
  background: var(--card);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
}
.load-more {
  justify-self: center;
  min-height: 38px;
  padding: 0 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--primary);
  color: var(--primary-foreground);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow);
}
.load-more:hover { background: #27272a; }
.load-more:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
@media (max-width: 1100px) {
  .metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .tables { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .site-header { align-items: start; flex-direction: column; }
  .updated { justify-items: start; min-width: 0; }
  .section-heading { align-items: start; flex-direction: column; }
  .section-heading p { text-align: left; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .leaderboards, .tables { grid-template-columns: 1fr; }
  .fixture { grid-template-columns: 1fr; align-items: start; }
}
@media (max-width: 560px) {
  .site-header { padding-top: 28px; }
  h1 { font-size: 42px; }
  .metrics { grid-template-columns: 1fr; }
  .match-meta { align-items: start; flex-direction: column; }
  .scoreline { grid-template-columns: 1fr; }
  .team.away { justify-content: flex-start; text-align: left; }
  .score { order: -1; width: 100%; }
  .updated strong { white-space: normal; }
}
"""


if __name__ == "__main__":
    raise SystemExit(main())

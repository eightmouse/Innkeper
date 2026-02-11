# Innkeeper - Version 0.8
# @Author: eightmouse

# ------------[      MODULES      ]------------ #
import json
import requests
import os
import sys
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

client_id     = os.getenv("BLIZZARD_CLIENT_ID")
client_secret = os.getenv("BLIZZARD_CLIENT_SECRET")

# ------------[  DATA PERSISTENCE ]------------ #

def save_data(characters):
    with open('characters.json', 'w') as f:
        json.dump([c.to_dict() for c in characters], f, indent=4)

def load_data():
    try:
        with open('characters.json', 'r') as f:
            content = f.read().strip()
            if not content:
                return []
            return [Character.from_dict(c) for c in json.loads(content)]
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def emit(data):
    """Send JSON to stdout (Electron renderer)."""
    print(json.dumps(data))
    sys.stdout.flush()

# ------------[        API        ]------------ #

# Token cache per region so we don't fetch a new one on every command
_token_cache: dict[str, str] = {}

def get_access_token(region: str = "eu") -> str | None:
    if region in _token_cache:
        return _token_cache[region]

    url      = f"https://{region}.battle.net/oauth/token"
    response = requests.post(url, data={"grant_type": "client_credentials"},
                             auth=(client_id, client_secret))
    if response.status_code == 200:
        token = response.json()["access_token"]
        _token_cache[region] = token
        return token

    print(f"[engine] Failed to get token for {region}: {response.status_code}",
          file=sys.stderr)
    return None


def fetch_character(region: str, realm: str, name: str, token: str) -> dict | None:
    """Fetch basic character profile."""
    slug = realm.lower().replace(" ", "-").replace("'", "").replace(".", "")
    url  = f"https://{region}.api.blizzard.com/profile/wow/character/{slug}/{name.lower()}"
    r = requests.get(url,
        params={"namespace": f"profile-{region}", "locale": "en_US"},
        headers={"Authorization": f"Bearer {token}"}
    )
    if r.status_code == 200: return r.json()
    print(f"[engine] fetch_character {r.status_code} | {url} | {r.text[:200]}", file=sys.stderr)
    return None


def fetch_character_media(region: str, realm: str, name: str, token: str) -> str | None:
    """Return best portrait URL from the Armory media API."""
    slug = realm.lower().replace(" ", "-").replace("'", "").replace(".", "")
    url  = (f"https://{region}.api.blizzard.com/profile/wow/character"
            f"/{slug}/{name.lower()}/character-media")
    r = requests.get(url,
        params={"namespace": f"profile-{region}", "locale": "en_US"},
        headers={"Authorization": f"Bearer {token}"}
    )
    if r.status_code != 200:
        print(f"[engine] fetch_media {r.status_code} | {r.text[:200]}", file=sys.stderr)
        return None
    assets = {a["key"]: a["value"] for a in r.json().get("assets", [])}
    for key in ("main-raw", "main", "inset", "avatar"):
        if key in assets:
            return assets[key]
    return None


def fetch_realms(region: str, token: str) -> list[tuple[str, str]]:
    url = f"https://{region}.api.blizzard.com/data/wow/realm/index"
    r   = requests.get(url, params={"namespace": f"dynamic-{region}", "locale": "en_US"},
                       headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 200:
        return [(realm["name"], realm["slug"]) for realm in r.json()["realms"]]
    print(f"[engine] fetch_realms {r.status_code}", file=sys.stderr)
    return []


def auto_add_character(region: str, name: str) -> "Character | None":
    """
    Search all realms in the given region for a character by name.
    Fetches portrait on success. Emits progress to stderr (not stdout).
    """
    token = get_access_token(region)
    if not token:
        return None

    realms = sorted(fetch_realms(region, token))
    if not realms:
        return None

    total = len(realms)
    print(f"[engine] Searching {name} across {total} realms in {region}…", file=sys.stderr)

    for i, (realm_name, _) in enumerate(realms):
        print(f"[engine] {i+1}/{total} {realm_name}", file=sys.stderr)
        data = fetch_character(region, realm_name, name, token)
        if data:
            level       = data.get("level", "?")
            portrait    = fetch_character_media(region, realm_name, name, token)
            char        = Character(name, level, realm_name, region, portrait)
            print(f"[engine] Found: {name} on {realm_name} (lvl {level})", file=sys.stderr)
            return char

    print(f"[engine] {name} not found in {region}", file=sys.stderr)
    return None

# ------------[       CLASS       ]------------ #

class Character:
    def __init__(self, name: str, level, realm: str,
                 region: str = "eu", portrait_url: str | None = None):
        self.name        = name
        self.level       = level
        self.realm       = realm
        self.region      = region
        self.portrait_url = portrait_url
        self.activities  = {
            "Raid":         {"status": "available", "reset": "weekly"},
            "Mythic+":      {"status": "available", "reset": "weekly"},
            "Expeditions":  {"status": "available", "reset": "weekly"},
            "World Quests": {"status": "available", "reset": "daily"},
        }
        self.last_reset_check = datetime.now(UTC)

    # ── Reset logic ──────────────────────────────────────

    def get_last_reset_boundary(self, reset_type: str) -> datetime:
        """Most recent 08:00 UTC boundary (daily or weekly/Wednesday)."""
        now      = datetime.now(UTC)
        boundary = now.replace(hour=8, minute=0, second=0, microsecond=0)

        if reset_type == "daily":
            if now < boundary:
                boundary -= timedelta(days=1)
            return boundary

        # weekly: Wednesday (weekday 2)
        days_since_wed = (now.weekday() - 2) % 7
        boundary      -= timedelta(days=days_since_wed)
        if now < boundary:
            boundary -= timedelta(days=7)
        return boundary

    def check_resets(self):
        daily_b  = self.get_last_reset_boundary("daily")
        weekly_b = self.get_last_reset_boundary("weekly")
        modified = False

        for data in self.activities.values():
            boundary = weekly_b if data["reset"] == "weekly" else daily_b
            if self.last_reset_check < boundary:
                data["status"] = "available"
                modified = True

        if modified:
            self.last_reset_check = datetime.now(UTC)
            print(f"[engine] Resets applied for {self.name}", file=sys.stderr)

    # ── Mutation ─────────────────────────────────────────

    def toggle_activity(self, activity_name: str):
        if activity_name in self.activities:
            current = self.activities[activity_name]["status"]
            self.activities[activity_name]["status"] = (
                "completed" if current == "available" else "available"
            )

    # ── Serialisation ────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name":             self.name,
            "level":            self.level,
            "realm":            self.realm,
            "region":           self.region,
            "portrait_url":     self.portrait_url,
            "activities":       self.activities,
            "last_reset_check": self.last_reset_check.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict) -> "Character":
        char = Character(
            data["name"],
            data["level"],
            data["realm"],
            data.get("region", "eu"),
            data.get("portrait_url"),
        )
        char.activities       = data["activities"]
        char.last_reset_check = datetime.fromisoformat(
            data.get("last_reset_check", datetime.now(UTC).isoformat())
        )
        return char

# ------------[       MAIN        ]------------ #

def find_character(characters: list, name: str, realm: str) -> "Character | None":
    n, r = name.lower(), realm.lower()
    return next((c for c in characters if c.name.lower() == n and c.realm.lower() == r), None)


def main():
    emit({"status": "ready"})

    # Warn immediately if API credentials are absent
    if not client_id or not client_secret:
        emit({"status": "error",
              "message": "Blizzard API credentials missing — check your .env file (BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET)"})

    characters: list[Character] = load_data()
    for char in characters:
        char.check_resets()
    save_data(characters)

    for raw_line in sys.stdin:
        command = raw_line.strip()
        if not command:
            continue

        # ── GET_CHARACTERS ─────────────────────────────
        if command == "GET_CHARACTERS":
            emit([c.to_dict() for c in characters])

        # ── ADD_CHARACTER:<region>:<realm>:<n> (direct, fast) ──
        elif command.startswith("ADD_CHARACTER:"):
            parts = command.split(":", 3)
            if len(parts) == 4:
                _, region, realm, name = parts
                region, realm, name = region.strip(), realm.strip(), name.strip()
                token = get_access_token(region)
                if not token:
                    emit({"status": "error", "message": "Could not authenticate with Blizzard API"})
                else:
                    data = fetch_character(region, realm, name, token)
                    if data:
                        level    = data.get("level", "?")
                        portrait = fetch_character_media(region, realm, name, token)
                        char     = Character(name, level, realm, region, portrait)
                        if not find_character(characters, char.name, char.realm):
                            characters.append(char)
                            save_data(characters)
                        emit({"status": "added", "character": char.to_dict()})
                    else:
                        emit({"status": "not_found"})

        # ── AUTO_ADD:<region>:<name> ────────────────────
        elif command.startswith("AUTO_ADD:"):
            parts = command.split(":", 2)
            if len(parts) == 3:
                _, region, name = parts
                char = auto_add_character(region.strip(), name.strip())
                if char:
                    # Avoid duplicates
                    exists = find_character(characters, char.name, char.realm)
                    if not exists:
                        characters.append(char)
                        save_data(characters)
                    emit({"status": "added", "character": char.to_dict()})
                else:
                    emit({"status": "not_found"})

        # ── DELETE_CHARACTER:<name>:<realm> ─────────────
        elif command.startswith("DELETE_CHARACTER:"):
            parts = command.split(":", 2)
            if len(parts) == 3:
                _, name, realm = parts
                char = find_character(characters, name.strip(), realm.strip())
                if char:
                    characters.remove(char)
                    save_data(characters)
                    emit({"status": "deleted", "name": name, "realm": realm})

        # ── TOGGLE_ACTIVITY:<name>:<realm>:<activity> ───
        elif command.startswith("TOGGLE_ACTIVITY:"):
            parts = command.split(":", 3)
            if len(parts) == 4:
                _, name, realm, activity = parts
                char = find_character(characters, name.strip(), realm.strip())
                if char:
                    char.toggle_activity(activity.strip())
                    save_data(characters)
                    emit({"status": "toggled", "name": name,
                          "activity": activity, "new_status": char.activities.get(activity, {}).get("status")})

        # ── EXIT ────────────────────────────────────────
        elif command == "EXIT":
            save_data(characters)
            break


if __name__ == "__main__":
    main()
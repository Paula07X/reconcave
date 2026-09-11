"""Compare the current scan's discovered hosts against the last saved scan
for the same target, so repeat runs can highlight what's new."""

import json
import logging
from pathlib import Path

log = logging.getLogger("reconcave")

DEFAULT_STATE_DIR = Path.home() / ".reconcave" / "state"


def _state_path(target: str, state_dir: Path) -> Path:
    safe_name = target.replace("/", "_").replace(":", "_")
    return state_dir / f"{safe_name}.json"


def load_previous_hosts(target: str, state_dir: Path = DEFAULT_STATE_DIR) -> set:
    path = _state_path(target, state_dir)
    if not path.exists():
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        return set(data.get("hosts", []))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Could not read previous scan state at %s: %s", path, e)
        return set()


def save_current_hosts(target: str, hosts: set, state_dir: Path = DEFAULT_STATE_DIR):
    state_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(target, state_dir)
    try:
        with open(path, "w") as f:
            json.dump({"target": target, "hosts": sorted(hosts)}, f, indent=2)
    except OSError as e:
        log.warning("Could not save scan state at %s: %s", path, e)


def compute_diff(current_hosts: set, previous_hosts: set) -> dict:
    return {
        "new": sorted(current_hosts - previous_hosts),
        "removed": sorted(previous_hosts - current_hosts),
        "unchanged_count": len(current_hosts & previous_hosts),
        "is_first_scan": len(previous_hosts) == 0,
    }

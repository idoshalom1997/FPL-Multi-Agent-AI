"""
The two private IDs - your FPL entry and your mini-league - live in config.json,
which is NOT in the repository (see config.example.json). A league ID would let
anyone look up the other managers' real names, so it never goes public.
"""
import json
from pathlib import Path

_path = Path(__file__).with_name("config.json")
_cfg = json.loads(_path.read_text(encoding="utf-8")) if _path.exists() else {}

ENTRY_ID = int(_cfg.get("entry_id", 0))
LEAGUE_ID = int(_cfg.get("league_id", 0))

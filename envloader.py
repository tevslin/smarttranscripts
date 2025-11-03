"""
lib/envloader.py

Minimal environment loader that walks up the directory tree and merges keys from .env files into os.environ.
Reusable across modules (meetingindexer, meetingreporter, factory, etc.).
Now includes diagnostic prints so you can see what files are read and what keys are set.

This version is safe to import from anywhere in the project (whether running a script from lib/ or from another folder).
As long as `lib` is on sys.path (because it is a package with __init__.py), you can do:

    from lib import envloader
    envloader.load_env_upwards(Path(__file__).resolve().parent, ["PINECONE_API_KEY", "OPENAI_API_KEY"])

and it will work consistently.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Iterable

__all__ = ["parse_env_file", "load_env_upwards"]


# Ensure lib/ can be imported whether run from project root or lib folder
_current_file = Path(__file__).resolve()
_lib_dir = _current_file.parent
_project_root = _lib_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a minimal .env file (KEY=VALUE, supports quotes, ignores comments)."""
    env: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return env
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def load_env_upwards(start: Path | None = None, keys: Iterable[str] = ()) -> None:
    """Walk upward from *start* (or CWD) to root, merging any of *keys* from .env files into os.environ
    **only if** that key is not already set.

    Prints diagnostics: which .env files were read, and which keys were set.
    """
    cur = (start or Path.cwd()).resolve()
    seen: set[str] = set()
    print(f"[envloader] Starting search from {cur}")
    while True:
        env_path = cur / ".env"
        if env_path.exists() and str(env_path) not in seen:
            seen.add(str(env_path))
            print(f"[envloader] Found .env at {env_path}")
            parsed = parse_env_file(env_path)
            for k in keys:
                if k in parsed and not os.getenv(k):
                    os.environ[k] = parsed[k]
                    print(f"[envloader] Set {k} from {env_path}")
                elif k in parsed:
                    print(f"[envloader] {k} already in environment, skipping {env_path}")
        if cur.parent == cur:
            break
        cur = cur.parent
    for k in keys:
        val = os.getenv(k)
        if val:
            print(f"[envloader] Final value for {k}: {val[:6]}... (len {len(val)})")
        else:
            print(f"[envloader] {k} not found in any .env or environment")

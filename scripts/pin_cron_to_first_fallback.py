#!/usr/bin/env python3
"""Pin the two weekly cron agent jobs to whatever model is currently
fallback_providers[0] in ~/.hermes/config.yaml.

Called by openrouter_fallback_check.py after a successful chain update.
Also safe to run directly for an immediate sync.

Pin target jobs (by ID):
  fe2333f495f0 — weekly-auburn-and-college-football-digest  (Mon 5am)
  d9a937ce7f72 — atlanta-concert-scout-from-youtube-music-playlist  (Mon 6am)

Exits non-zero if the chain is empty or the cron edit fails. Never
modifies the primary model.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()
CONFIG_PATH = Path(
    os.environ.get("HERMES_CONFIG_PATH", HERMES_HOME / "config.yaml")
).expanduser()

PINNED_CRON_IDS = [
    "fe2333f495f0",  # weekly-auburn-and-college-football-digest
    "d9a937ce7f72",  # atlanta-concert-scout-from-youtube-music-playlist
]


def load_yaml(path: Path) -> dict:
    # Avoid pulling in pyyaml if we don't need to; fall back to a minimal parser.
    try:
        import yaml  # type: ignore
        with path.open() as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError("config root is not a mapping")
        return data
    except ImportError:
        # Minimal YAML parse: just grab the fallback_providers block.
        text = path.read_text()
        if "fallback_providers" not in text:
            return {}
        # Use a quick PyYAML-free extraction — we only need the providers list.
        # This is fragile, so prefer the import path when available.
        raise RuntimeError(
            "PyYAML is required to read Hermes config. "
            "Activate the Hermes venv: `source ~/.hermes/venv/bin/activate`."
        )


def get_first_fallback(cfg: dict) -> dict | None:
    chain = cfg.get("fallback_providers")
    if not isinstance(chain, list) or not chain:
        return None
    first = chain[0]
    if not isinstance(first, dict):
        return None
    provider = first.get("provider")
    model = first.get("model")
    if not provider or not model:
        return None
    return {"provider": provider, "model": model}


def hermes_cron_edit(job_id: str, provider: str, model: str) -> tuple[bool, str]:
    """Run `hermes cron edit <id> --model <m> --provider <p>` and return (ok, output)."""
    proc = subprocess.run(
        [
            "hermes",
            "cron",
            "edit",
            job_id,
            "--model",
            model,
            "--provider",
            provider,
        ],
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return False, err or out or f"exit {proc.returncode}"
    return True, out or "ok"


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"pin_cron_to_first_fallback: config not found: {CONFIG_PATH}", file=sys.stderr)
        return 2

    cfg = load_yaml(CONFIG_PATH)
    first = get_first_fallback(cfg)
    if first is None:
        print(
            "pin_cron_to_first_fallback: fallback_providers is empty or malformed; nothing to pin",
            file=sys.stderr,
        )
        return 3

    print(
        f"pin_cron_to_first_fallback: syncing {len(PINNED_CRON_IDS)} job(s) to "
        f"{first['provider']}/{first['model']}"
    )

    failures = []
    for job_id in PINNED_CRON_IDS:
        ok, msg = hermes_cron_edit(job_id, first["provider"], first["model"])
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {job_id}: {msg.splitlines()[0] if msg else '(no output)'}")
        if not ok:
            failures.append((job_id, msg))

    if failures:
        print(
            f"pin_cron_to_first_fallback: {len(failures)} failure(s): {failures}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

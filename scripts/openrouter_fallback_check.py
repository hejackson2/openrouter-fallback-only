#!/usr/bin/env python3
"""Hermes OpenRouter free-model fallback rotator (tier-list version).

Deterministic, script-only cron job:
  1. Read the user-maintained tier list at ~/.hermes/openrouter_tiers.json
  2. Fetch OpenRouter models
  3. Filter to :free models with sane metadata
  4. Drop any model below MIN_CONTEXT_LENGTH or below MIN_TIER_SCORE
  5. Probe healthy candidates
  6. Rank by tier_score desc, then unthrottled first, then context_length desc, then newer
  7. Persist the best fallback chain into Hermes config
  8. Preserve the existing primary model/provider entirely
  9. Store previous fallback selection in a local state file for diffing

The tier list is a small JSON file the user can edit to add/upgrade/downgrade
specific models. Models not in the list get a default score (1), which is
effectively excluded by the default MIN_TIER_SCORE.
"""

from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any

import requests
import yaml

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
HTTP_TIMEOUT = 10
BATCH_SIZE = 4
BATCH_SLEEP_SECONDS = 0.25
DEFAULT_CHAIN_LENGTH = 3
DEFAULT_TIER_CONFIG_PATH = "~/.hermes/openrouter_tiers.json"
DEFAULT_TIER_SCORE = 1  # any model not in the tier list gets this


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()


def config_path() -> Path:
    return Path(os.environ.get("HERMES_CONFIG_PATH", hermes_home() / "config.yaml")).expanduser()


def state_path() -> Path:
    return Path(
        os.environ.get(
            "HERMES_STATE_PATH",
            hermes_home() / "state" / "openrouter_fallback_rotator.json",
        )
    ).expanduser()


def backup_path() -> Path:
    return Path(os.environ.get("HERMES_BACKUP_PATH", hermes_home() / "config.yaml.bak")).expanduser()


def tier_config_path() -> Path:
    raw = os.environ.get("HERMES_TIER_CONFIG_PATH", DEFAULT_TIER_CONFIG_PATH)
    return Path(raw).expanduser()


def openrouter_base_url() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", OPENROUTER_API_BASE).rstrip("/")


def desired_chain_length() -> int:
    raw = os.environ.get("OPENROUTER_FALLBACK_CHAIN_LENGTH", str(DEFAULT_CHAIN_LENGTH)).strip()
    try:
        value = int(raw)
    except ValueError:
        fail(f"diagnostic: invalid OPENROUTER_FALLBACK_CHAIN_LENGTH: {raw!r}")
    if value < 1:
        fail("diagnostic: OPENROUTER_FALLBACK_CHAIN_LENGTH must be at least 1")
    return value


def fail(msg: str, code: int = 1) -> None:
    print(msg)
    raise SystemExit(code)


def read_json_state(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text())
    except Exception:
        return None


def write_atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def copy_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", dir=str(dst.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out_fh, src.open("rb") as in_fh:
            shutil.copyfileobj(in_fh, out_fh)
            out_fh.flush()
            os.fsync(out_fh.fileno())
        os.replace(tmp, dst)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"diagnostic: config missing: {path}")
    try:
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        fail(f"diagnostic: config parse failed: {path}: {exc}")
    if not isinstance(data, dict):
        fail(f"diagnostic: config root is not a mapping: {path}")
    return data


def dump_config(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)


# ---------- Tier list ------------------------------------------------------


def load_tier_config(path: Path) -> dict[str, Any]:
    """Load the user-maintained tier list. Always succeeds — missing file
    means use defaults (everything at DEFAULT_TIER_SCORE)."""
    defaults = {
        "min_context_length": 32000,
        "min_tier_score": 4,
        "tiers": {},
    }
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        # Bad JSON is a config error worth failing on — better than silently
        # treating every model as tier 1 and writing that to fallback_providers.
        fail(f"diagnostic: tier config parse failed: {path}: {exc}")
    if not isinstance(data, dict):
        fail(f"diagnostic: tier config root is not a mapping: {path}")
    out = dict(defaults)
    if isinstance(data.get("min_context_length"), int) and data["min_context_length"] > 0:
        out["min_context_length"] = data["min_context_length"]
    if isinstance(data.get("min_tier_score"), int) and data["min_tier_score"] >= 0:
        out["min_tier_score"] = data["min_tier_score"]
    tiers_in = data.get("tiers", {})
    if not isinstance(tiers_in, dict):
        fail(f"diagnostic: tier config 'tiers' is not a mapping: {path}")
    out["tiers"] = {}
    for model_id, entry in tiers_in.items():
        if not isinstance(model_id, str) or not isinstance(entry, dict):
            continue
        score = entry.get("score")
        if not isinstance(score, int):
            continue
        out["tiers"][model_id] = {
            "score": score,
            "note": entry.get("note", "") if isinstance(entry.get("note"), str) else "",
        }
    return out


def tier_score_for(model_id: str, tiers: dict[str, dict[str, Any]]) -> int:
    entry = tiers.get(model_id)
    if isinstance(entry, dict) and isinstance(entry.get("score"), int):
        return entry["score"]
    return DEFAULT_TIER_SCORE


# ---------- OpenRouter I/O ------------------------------------------------


def env_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    env_file = hermes_home() / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "OPENROUTER_API_KEY":
                v = v.strip().strip('"').strip("'")
                if v:
                    return v
    fail("diagnostic: OPENROUTER_API_KEY is missing from the environment and ~/.hermes/.env")


def fetch_models(api_key: str) -> tuple[list[dict[str, Any]], int]:
    url = f"{openrouter_base_url()}/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://hermes-agent.nousresearch.com",
        "X-Title": "Hermes OpenRouter Fallback Rotator",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        fail(f"diagnostic: model fetch failed: {exc}")
    if resp.status_code != 200:
        snippet = resp.text[:300].replace("\n", " ")
        fail(f"diagnostic: model fetch HTTP {resp.status_code}: {snippet}")
    try:
        payload = resp.json()
    except Exception as exc:
        fail(f"diagnostic: model fetch returned invalid JSON: {exc}")
    models = payload.get("data", payload)
    if not isinstance(models, list):
        fail("diagnostic: model list payload missing data array")
    return models, len(models)


def as_int(value: Any) -> int | None:
    try:
        if isinstance(value, bool):
            return None
        return int(value)
    except Exception:
        return None


def as_float(value: Any) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        return float(value)
    except Exception:
        return None


def normalize_model(raw: dict[str, Any]) -> dict[str, Any] | None:
    model_id = raw.get("id")
    if not isinstance(model_id, str) or not model_id.endswith(":free"):
        return None
    context_length = as_int(raw.get("context_length"))
    created = as_int(raw.get("created"))
    pricing = raw.get("pricing") or {}
    if not isinstance(pricing, dict):
        return None
    prompt_price = as_float(pricing.get("prompt"))
    completion_price = as_float(pricing.get("completion"))
    if context_length is None or context_length <= 0:
        return None
    if created is None:
        created = 0
    if prompt_price is None or completion_price is None:
        return None
    if abs(prompt_price) > 1e-12 or abs(completion_price) > 1e-12:
        return None
    return {
        "id": model_id,
        "context_length": context_length,
        "created": created,
        "pricing": {"prompt": prompt_price, "completion": completion_price},
    }


def probe_one(model_id: str, api_key: str) -> dict[str, Any]:
    url = f"{openrouter_base_url()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://hermes-agent.nousresearch.com",
        "X-Title": "Hermes OpenRouter Fallback Rotator",
    }
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
    except requests.Timeout:
        return {"status": "timeout"}
    except requests.RequestException as exc:
        return {"status": "error", "error": str(exc)}
    if resp.status_code == 200:
        return {"status": "healthy", "http": 200}
    if resp.status_code == 429:
        return {"status": "throttled", "http": 429}
    return {"status": "unhealthy", "http": resp.status_code, "body": resp.text[:120]}


def probe_models(models: list[dict[str, Any]], api_key: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for idx in range(0, len(models), BATCH_SIZE):
        batch = models[idx: idx + BATCH_SIZE]
        with cf.ThreadPoolExecutor(max_workers=BATCH_SIZE) as pool:
            fut_map = {pool.submit(probe_one, m["id"], api_key): m for m in batch}
            for fut in cf.as_completed(fut_map):
                m = fut_map[fut]
                probe = fut.result()
                results.append({**m, **probe})
        if idx + BATCH_SIZE < len(models):
            time.sleep(BATCH_SLEEP_SECONDS)
    return results


# ---------- Ranking --------------------------------------------------------


def rank_candidates(
    models: list[dict[str, Any]],
    tier_config: dict[str, Any],
) -> list[dict[str, Any]]:
    min_ctx = int(tier_config.get("min_context_length", 32000))
    min_score = int(tier_config.get("min_tier_score", 4))
    tiers = tier_config.get("tiers", {})

    def sort_key(m: dict[str, Any]) -> tuple[int, int, int, int, str]:
        throttled_rank = 1 if m.get("status") == "throttled" else 0
        score = tier_score_for(m["id"], tiers)
        # We want highest score first, so negate.
        return (
            throttled_rank,
            -score,
            -int(m["context_length"]),
            -int(m.get("created", 0)),
            str(m["id"]),
        )

    eligible = []
    for m in models:
        if m.get("status") not in {"healthy", "throttled"}:
            continue
        if int(m["context_length"]) < min_ctx:
            continue
        if tier_score_for(m["id"], tiers) < min_score:
            continue
        eligible.append(m)
    return sorted(eligible, key=sort_key)


def desired_fallbacks(top_models: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"provider": "openrouter", "model": model["id"]} for model in top_models]


def config_matches(data: dict[str, Any], desired: list[dict[str, str]]) -> bool:
    current_fallback = data.get("fallback_providers")
    return current_fallback == desired


def summarize_models(models: list[dict[str, Any]]) -> str:
    return ", ".join(f"{m['id']}({m['context_length']})" for m in models)


def summarize_fallbacks(fallbacks: list[dict[str, str]]) -> str:
    return ", ".join(f"{entry['model']}" for entry in fallbacks)


def sync_cron_pins_enabled() -> bool:
    raw = os.environ.get("OPENROUTER_SYNC_CRON_PINS", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def sync_cron_pins() -> None:
    """Optionally pin selected cron jobs to the new first fallback.

    This is opt-in. Set OPENROUTER_SYNC_CRON_PINS=1 to enable it. The
    helper is delegated to a small external script so the rotator stays
    focused on chain selection. Errors here are non-fatal — the chain is
    already written and the cron jobs can be re-pinned manually if needed.
    """
    if not sync_cron_pins_enabled():
        print("sync_cron_pins: disabled (set OPENROUTER_SYNC_CRON_PINS=1 to enable)")
        return
    pin_script = hermes_home() / "scripts" / "pin_cron_to_first_fallback.py"
    if not pin_script.exists():
        print("sync_cron_pins: pin script not found; skipping")
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(pin_script)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        print(f"sync_cron_pins: failed to invoke pin script: {exc}")
        return
    if proc.stdout:
        for line in proc.stdout.splitlines():
            print(f"sync_cron_pins: {line}")
    if proc.returncode != 0:
        print(
            f"sync_cron_pins: pin script exited {proc.returncode}: "
            f"{(proc.stderr or '').strip()}"
        )


# ---------- Main -----------------------------------------------------------


def main() -> None:
    cfg_path = config_path()
    st_path = state_path()
    bak_path = backup_path()
    t_path = tier_config_path()

    cfg = load_config(cfg_path)
    api_key = env_api_key()
    chain_length = desired_chain_length()
    tier_config = load_tier_config(t_path)

    raw_models, fetched_count = fetch_models(api_key)
    normalized = [m for m in (normalize_model(x) for x in raw_models if isinstance(x, dict)) if m]
    probed = probe_models(normalized, api_key)
    ranked = rank_candidates(probed, tier_config)

    if len(ranked) < chain_length:
        healthy_count = len(ranked)
        fail(
            f"diagnostic: eligible model count too low: {healthy_count} "
            f"(need at least {chain_length}). "
            f"min_context_length={tier_config['min_context_length']}, "
            f"min_tier_score={tier_config['min_tier_score']}. "
            f"Consider lowering min_tier_score in {t_path}."
        )

    top_models = ranked[:chain_length]
    if any(not m.get("id") or m.get("context_length", 0) <= 0 for m in top_models):
        fail("diagnostic: fallback selection validation failed")

    desired = desired_fallbacks(top_models)
    healthy_count = len(ranked)
    current_state = read_json_state(st_path) or {}
    previous_selected = current_state.get("fallbacks") if isinstance(current_state, dict) else None
    prev_summary = "n/a"
    if isinstance(previous_selected, list) and previous_selected:
        try:
            prev_summary = summarize_fallbacks(previous_selected)
        except Exception:
            prev_summary = "n/a"

    current_matches = config_matches(cfg, desired)
    ts = utc_now()

    if current_matches:
        current_summary = summarize_models(top_models)
        print(
            f"{ts} no change; fetched={fetched_count} eligible={healthy_count} "
            f"min_score={tier_config['min_tier_score']} "
            f"min_ctx={tier_config['min_context_length']} "
            f"fallbacks={current_summary}"
        )
        return

    try:
        st_path.parent.mkdir(parents=True, exist_ok=True)
        test_path = st_path.parent / f".write-test.{os.getpid()}.tmp"
        test_path.write_text(ts, encoding="utf-8")
        test_path.unlink()
    except Exception as exc:
        fail(f"diagnostic: state directory not writable: {st_path.parent}: {exc}")

    try:
        copy_atomic(cfg_path, bak_path)
    except Exception as exc:
        fail(f"diagnostic: backup write failed: {exc}")

    updated = dict(cfg)
    updated["fallback_providers"] = desired
    updated.pop("fallback_model", None)

    try:
        write_atomic_text(cfg_path, dump_config(updated))
    except Exception as exc:
        fail(f"diagnostic: config write failed: {exc}")

    try:
        new_state = {
            "timestamp": ts,
            "fallbacks": desired,
            "selected_models": top_models,
            "tier_config_path": str(t_path),
            "min_tier_score": tier_config["min_tier_score"],
            "min_context_length": tier_config["min_context_length"],
        }
        write_atomic_text(st_path, json.dumps(new_state, indent=2, sort_keys=True) + "\n")
    except Exception as exc:
        fail(f"diagnostic: state write failed: {exc}")

    diff_text = (
        f"diff: {prev_summary} -> {summarize_fallbacks(desired)}"
        if prev_summary != summarize_fallbacks(desired)
        else "diff: none"
    )
    print(
        f"{ts} fetched={fetched_count} eligible={healthy_count} "
        f"min_score={tier_config['min_tier_score']} "
        f"min_ctx={tier_config['min_context_length']} "
        f"fallbacks={summarize_models(top_models)}"
    )
    print(diff_text)
    sync_cron_pins()


if __name__ == "__main__":
    main()

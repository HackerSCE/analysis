import json
import logging
import os
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)

DEFAULT_REDIRECT_URI = "http://127.0.0.1:5000/callback"
RUNTIME_CONFIG_PATH = Path(__file__).resolve().parents[1] / "instance" / "fyers_runtime_config.json"
_lock = threading.Lock()


def get_fyers_config():
    runtime_config = _load_runtime_config()
    env_config = _get_env_config()
    merged = {
        "client_id": runtime_config.get("client_id") or env_config["client_id"],
        "secret_key": runtime_config.get("secret_key") or env_config["secret_key"],
        "redirect_uri": runtime_config.get("redirect_uri") or env_config["redirect_uri"],
        "source": runtime_config.get("source") or env_config["source"],
        "updated_at": runtime_config.get("updated_at") or env_config.get("updated_at"),
    }
    merged["configured"] = all(merged.get(key) for key in ("client_id", "secret_key", "redirect_uri"))
    if not merged["configured"]:
        merged["source"] = "missing"
    return merged


def describe_fyers_config():
    config = get_fyers_config()
    return {
        "configured": bool(config.get("configured")),
        "source": config.get("source") or "missing",
        "client_id": config.get("client_id") or "",
        "redirect_uri": config.get("redirect_uri") or "",
        "has_secret_key": bool(config.get("secret_key")),
        "updated_at": config.get("updated_at"),
    }


def save_fyers_config(client_id=None, secret_key=None, redirect_uri=None):
    current = get_fyers_config()
    config = {
        "client_id": _clean_value(client_id) or current.get("client_id") or "",
        "secret_key": _clean_value(secret_key) or current.get("secret_key") or "",
        "redirect_uri": _clean_value(redirect_uri) or current.get("redirect_uri") or DEFAULT_REDIRECT_URI,
        "source": "runtime",
        "updated_at": datetime.utcnow().isoformat(),
    }
    if not all(config.get(key) for key in ("client_id", "secret_key", "redirect_uri")):
        missing = [key for key in ("client_id", "secret_key", "redirect_uri") if not config.get(key)]
        raise ValueError(f"Missing FYERS credential values: {', '.join(missing)}")

    _write_runtime_config(config)
    logger.info("FYERS runtime config saved: %s", _mask_config(config))
    return describe_fyers_config()


def clear_fyers_config():
    with _lock:
        if RUNTIME_CONFIG_PATH.exists():
            RUNTIME_CONFIG_PATH.unlink()
    logger.info("FYERS runtime config cleared")
    return describe_fyers_config()


def _get_env_config():
    return {
        "client_id": _clean_value(os.getenv("FYERS_CLIENT_ID")),
        "secret_key": _clean_value(os.getenv("FYERS_SECRET_KEY")),
        "redirect_uri": _clean_value(os.getenv("FYERS_REDIRECT_URI")) or DEFAULT_REDIRECT_URI,
        "source": "env",
    }


def _load_runtime_config():
    with _lock:
        if not RUNTIME_CONFIG_PATH.exists():
            return {}
        try:
            payload = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {}
            return {
                "client_id": _clean_value(payload.get("client_id")),
                "secret_key": _clean_value(payload.get("secret_key")),
                "redirect_uri": _clean_value(payload.get("redirect_uri")) or DEFAULT_REDIRECT_URI,
                "source": "runtime",
                "updated_at": _clean_value(payload.get("updated_at")),
            }
        except Exception as exc:
            logger.warning("Unable to load FYERS runtime config: %s", exc)
            return {}


def _write_runtime_config(config):
    payload = {
        "client_id": config.get("client_id") or "",
        "secret_key": config.get("secret_key") or "",
        "redirect_uri": config.get("redirect_uri") or DEFAULT_REDIRECT_URI,
        "updated_at": config.get("updated_at") or datetime.utcnow().isoformat(),
    }
    RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = RUNTIME_CONFIG_PATH.with_suffix(".json.tmp")
    with _lock:
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(RUNTIME_CONFIG_PATH)


def _clean_value(value):
    if value is None:
        return ""
    return str(value).strip()


def _mask_config(config):
    masked = deepcopy(config)
    if masked.get("secret_key"):
        masked["secret_key"] = "***"
    return masked

"""
widget_config.py
----------------
Stores and retrieves widget appearance/behaviour settings as a JSON file.
Merchants update these from the admin dashboard; the widget reads them on load.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

_HERE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR    = os.path.join(_HERE, os.getenv("DATA_DIR", "data"))
CONFIG_PATH = os.path.join(DATA_DIR, "widget_config.json")

DEFAULTS: dict = {
    "primaryColor": "#008060",
    "position":     "bottom-right",   # bottom-right | bottom-left
    "title":        "ShopAssist AI",
    "subtitle":     "Ask me anything about our products",
    "welcomeMsg":   "Hi! How can I help you shop today?",
    "showBranding": True,
}


def load() -> dict:
    """Return current config merged with defaults (so new keys are always present)."""
    try:
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            return {**DEFAULTS, **saved}
    except Exception as exc:
        print(f"[widget_config] load failed: {exc}")
    return DEFAULTS.copy()


def save(updates: dict) -> dict:
    """Merge updates into current config, persist to disk, return the saved config."""
    current = load()
    allowed = set(DEFAULTS)
    for k, v in updates.items():
        if k in allowed:
            current[k] = v
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return current

"""Loads config.yaml into a simple attribute-accessible config object.

Every tunable parameter lives in config.yaml; nothing here should hardcode a
strategy parameter. Paths in the config are relative to the repo root.
"""

import os
from typing import Any, Dict

import yaml

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


class Config:
    """Thin wrapper over the parsed YAML dict with dotted attribute access
    and paths resolved to absolute paths rooted at the repo root."""

    _PATH_KEYS = ("cache_dir", "bhavcopy_cache_dir", "reports_dir", "signals_log_file")

    def __init__(self, data: Dict[str, Any]):
        self._data = data
        for key in self._PATH_KEYS:
            if key in data and not os.path.isabs(data[key]):
                data[key] = os.path.join(_REPO_ROOT, data[key])

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(f"No config key '{name}' in config.yaml") from exc

    def get(self, name: str, default: Any = None) -> Any:
        return self._data.get(name, default)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)


def load_config(path: str = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cfg = Config(data)
    os.makedirs(cfg.cache_dir, exist_ok=True)
    os.makedirs(cfg.bhavcopy_cache_dir, exist_ok=True)
    os.makedirs(cfg.reports_dir, exist_ok=True)
    return cfg

import os
import sys
from typing import List


def get_base_dir() -> str:
    """Return the directory used as runtime base (handles PyInstaller onefile)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _candidate_config_names() -> List[str]:
    """Only YAML configs are supported now."""
    return ["config.yml", "config.yaml"]


def get_bundled_config_paths() -> list[str]:
    """
    Paths for built-in default config (inside the bundle or next to the script).
    Only YAML configs are supported now.
    """
    bundle_dir = getattr(sys, "_MEIPASS", None)  # PyInstaller onefile temp dir
    base = bundle_dir or os.path.dirname(os.path.abspath(__file__))
    return [os.path.join(base, name) for name in _candidate_config_names()]


def get_external_config_paths() -> list[str]:
    """
    Paths for user-override config (next to the executable).
    Only YAML configs are supported now.
    """
    base_dir = get_base_dir()
    return [os.path.join(base_dir, name) for name in _candidate_config_names()]

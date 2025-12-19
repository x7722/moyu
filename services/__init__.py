# Service modules for moyu
from .snapshot import save_snapshot, get_snapshot_dir
from .work_app import switch_to_work_app, get_os_command_key

__all__ = [
    "save_snapshot",
    "get_snapshot_dir",
    "switch_to_work_app",
    "get_os_command_key",
]

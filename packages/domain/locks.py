import os
import shutil
from datetime import datetime

import fasteners

DEFAULT_LOCK_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "workflow.lock")
DEFAULT_BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "backups")


class WorkflowLock:
    def __init__(self, lock_file: str = None):
        self.lock_file = lock_file or DEFAULT_LOCK_FILE
        os.makedirs(os.path.dirname(self.lock_file), exist_ok=True)
        self._lock = fasteners.InterProcessLock(self.lock_file)

    def __enter__(self):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Another workflow is already running")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()
        return False


def create_backup(db_path: str, backup_dir: str = None) -> str:
    backup_dir = backup_dir or DEFAULT_BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = os.path.join(backup_dir, f"stock_kb_{timestamp}.sqlite")
    shutil.copy2(db_path, backup_path)
    return backup_path


def list_backups(backup_dir: str = None) -> list:
    backup_dir = backup_dir or DEFAULT_BACKUP_DIR
    if not os.path.exists(backup_dir):
        return []
    files = [f for f in os.listdir(backup_dir) if f.endswith(".sqlite")]
    files.sort(reverse=True)
    return [os.path.join(backup_dir, f) for f in files]


def rollback_to_backup(db_path: str, backup_path: str):
    shutil.copy2(backup_path, db_path)

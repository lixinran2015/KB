import multiprocessing
import os
import tempfile
import time

import pytest

from packages.domain.locks import (
    WorkflowLock,
    create_backup,
    list_backups,
    rollback_to_backup,
)


def _try_acquire(lock_file, result_queue):
    lock = WorkflowLock(lock_file=lock_file)
    try:
        with lock:
            result_queue.put("acquired")
            time.sleep(0.3)
    except RuntimeError as e:
        result_queue.put(str(e))


def test_workflow_lock_acquire_and_release():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        lock_file = f.name

    lock = WorkflowLock(lock_file=lock_file)
    with lock:
        pass  # Lock acquired and will be released on exit

    os.unlink(lock_file)


def test_lock_blocks_concurrent_access():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        lock_file = f.name

    result_queue = multiprocessing.Queue()

    p1 = multiprocessing.Process(target=_try_acquire, args=(lock_file, result_queue))
    p1.start()
    time.sleep(0.1)  # Let p1 acquire lock

    p2 = multiprocessing.Process(target=_try_acquire, args=(lock_file, result_queue))
    p2.start()

    p1.join(timeout=2)
    p2.join(timeout=2)

    results = []
    while not result_queue.empty():
        results.append(result_queue.get())

    assert "acquired" in results
    assert any("already running" in r for r in results)

    os.unlink(lock_file)


def test_create_and_rollback_backup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        with open(db_path, "w") as f:
            f.write("original")

        backup_path = create_backup(db_path, backup_dir=tmpdir)
        assert os.path.exists(backup_path)

        # Modify original
        with open(db_path, "w") as f:
            f.write("modified")

        # Rollback
        rollback_to_backup(db_path, backup_path)
        with open(db_path, "r") as f:
            content = f.read()
        assert content == "original"


def test_list_backups():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        with open(db_path, "w") as f:
            f.write("dummy")

        b1 = create_backup(db_path, backup_dir=tmpdir)
        b2 = create_backup(db_path, backup_dir=tmpdir)

        backups = list_backups(backup_dir=tmpdir)
        assert len(backups) == 2
        assert backups[0] == b2  # Most recent first
        assert backups[1] == b1

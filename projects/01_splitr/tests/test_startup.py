"""Starting the app with run.py: clean errors for unusable databases, safe defaults."""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import run

PROJECT = Path(run.__file__).resolve().parent


def make_unusable_database(path):
    """A database in the original (pre-users) layout, which the app refuses to open."""
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE groups (id INTEGER PRIMARY KEY, name TEXT);")
    conn.close()


def test_an_old_database_stops_startup_with_a_clear_message_not_a_traceback(tmp_path):
    make_unusable_database(tmp_path / "splitr.db")
    result = subprocess.run(
        [sys.executable, str(PROJECT / "run.py"), "8091"],
        cwd=tmp_path,
        env={"PYTHONPATH": str(PROJECT), "PATH": ""},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "cannot start" in result.stderr and "old schema" in result.stderr
    assert str((tmp_path / "splitr.db").resolve()) in result.stderr  # full path, not cwd-relative
    assert "move or delete" in result.stderr  # says what to do about it


def test_a_fresh_directory_starts_and_creates_the_database(tmp_path, monkeypatch):
    import flask

    started = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SPLITR_DEBUG", raising=False)
    monkeypatch.setattr(flask.Flask, "run", lambda self, **kw: started.update(kw))

    assert run.main(["run.py", "8123"]) == 0
    assert started == {"host": "127.0.0.1", "port": 8123, "debug": False}
    assert (tmp_path / "splitr.db").exists()


@pytest.mark.parametrize("value, expected", [("1", True), ("true", True), ("0", False), ("", False)])
def test_debug_is_only_on_when_asked(tmp_path, monkeypatch, value, expected):
    import flask

    started = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SPLITR_DEBUG", value)
    monkeypatch.setattr(flask.Flask, "run", lambda self, **kw: started.update(kw))
    run.main(["run.py"])
    assert started["debug"] is expected
    assert started["port"] == 8080


def test_the_schema_error_is_still_a_runtime_error():
    from splitr.db import SchemaError

    assert issubclass(SchemaError, RuntimeError)  # older callers catching RuntimeError keep working

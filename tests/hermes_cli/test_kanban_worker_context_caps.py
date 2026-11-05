"""Worker context stays small on long-lived cards.

A card that loops through many review rounds accumulated its full history in every
spawn prompt (10 prior attempts + 30 comments). Workers only need the latest few;
older ones are summarised by the "omitted" marker and still reachable via kanban_show.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_connect as kbc


@pytest.fixture
def kanban_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def _seed_closed_runs(conn, task_id: str, count: int) -> None:
    now = int(time.time())
    for i in range(1, count + 1):
        conn.execute(
            "INSERT INTO task_runs (task_id, profile, status, started_at, ended_at, outcome, summary) "
            "VALUES (?, 'implementer', 'done', ?, ?, 'review_requested', ?)",
            (task_id, now - 10_000 + i * 10, now - 10_000 + i * 10 + 5, f"run-summary-{i:02d}"),
        )
    conn.commit()


def test_worker_context_shows_only_latest_three_attempts(kanban_home: Path) -> None:
    with kbc.connect() as conn:
        tid = kb.create_task(conn, title="long-lived card", assignee="implementer")
        _seed_closed_runs(conn, tid, 12)

        ctx = kb.build_worker_context(conn, tid)

    assert "run-summary-12" in ctx
    assert "run-summary-10" in ctx
    assert "run-summary-09" not in ctx
    assert "9 earlier attempts omitted; showing most recent 3" in ctx


def test_worker_context_shows_only_latest_ten_comments(kanban_home: Path) -> None:
    with kbc.connect() as conn:
        tid = kb.create_task(conn, title="chatty card", assignee="implementer")
        for i in range(1, 26):
            kb.add_comment(conn, tid, "reviewer", f"comment-body-{i:02d}")

        ctx = kb.build_worker_context(conn, tid)

    assert "comment-body-25" in ctx
    assert "comment-body-16" in ctx
    assert "comment-body-15" not in ctx
    assert "15 earlier comments omitted; showing most recent 10" in ctx

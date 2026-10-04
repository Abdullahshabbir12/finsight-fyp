"""Local run snapshots. Neither API keys nor original PDF binaries are stored."""
import os
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from src.models import Run, upgrade_run


@contextmanager
def connection(path: str | None = None):
    target = Path(path or os.getenv("FINSIGHT_DB_PATH", "data/finsight.sqlite3"))
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, company TEXT NOT NULL, created_at TEXT NOT NULL, is_demo INTEGER NOT NULL, payload TEXT NOT NULL)")
        yield conn


def save_run(run: Run, path: str | None = None) -> None:
    with connection(path) as conn:
        conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET company=excluded.company, payload=excluded.payload",
                     (run.id, run.company.name, run.created_at, int(run.is_demo), run.model_dump_json()))


def list_runs(path: str | None = None) -> list[tuple]:
    with connection(path) as conn:
        return conn.execute("SELECT id, company, created_at, is_demo FROM runs ORDER BY created_at DESC LIMIT 50").fetchall()


def load_run(run_id: str, path: str | None = None) -> Run:
    with connection(path) as conn:
        row = conn.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        raise ValueError("Saved run was not found.")
    return upgrade_run(Run.model_validate_json(row[0]))

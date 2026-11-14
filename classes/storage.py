"""Stores tasks and places permanently in a SQLite database."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from classes.location import Place
from classes.task import Task

SCHEMA = """
CREATE TABLE IF NOT EXISTS places (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    latitude  REAL    NOT NULL,
    longitude REAL    NOT NULL,
    radius_m  INTEGER NOT NULL DEFAULT 300
);
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    priority     TEXT    NOT NULL DEFAULT 'mittel',
    due_date     TEXT,
    tags         TEXT    NOT NULL DEFAULT '[]',
    done         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL,
    completed_at TEXT,
    location_id  INTEGER REFERENCES places(id) ON DELETE SET NULL
);
"""
COLUMNS = ("title", "description", "priority", "due_date", "tags", "done", "created_at", "completed_at",
           "location_id")
PLACE_COLUMNS = ("name", "latitude", "longitude", "radius_m")


class SqliteStorage:
    """Access to the SQLite database with the tables 'tasks' and 'places'."""
    def __init__(self, path: Path):
        """Creates the folder and tables if necessary and migrates old databases."""
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    # --- Tasks ---------------------------------------------------------------
    def load(self) -> list:
        """Loads all tasks."""
        return [self._to_task(row) for row in self._query("SELECT * FROM tasks ORDER BY id")]

    def insert(self, task: Task) -> int:
        """Saves a new task and returns its id."""
        values = self._to_row(task)
        sql = f"INSERT INTO tasks ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})"
        return self._execute(sql, [values[c] for c in COLUMNS]).lastrowid

    def update(self, task: Task):
        """Overwrites an existing task."""
        values = self._to_row(task)
        assignments = ", ".join(f"{c} = ?" for c in COLUMNS)
        self._execute(f"UPDATE tasks SET {assignments} WHERE id = ?", [values[c] for c in COLUMNS] + [task.id])

    def delete(self, task_id: int):
        """Deletes a task."""
        self._execute("DELETE FROM tasks WHERE id = ?", [task_id])

    def delete_completed(self) -> int:
        """Deletes all completed tasks and returns the count."""
        return self._execute("DELETE FROM tasks WHERE done = 1").rowcount

    # --- Places ----------------------------------------------------------------
    def load_places(self) -> list:
        """Loads all places, sorted by name."""
        return [Place(**dict(row)) for row in self._query("SELECT * FROM places ORDER BY name")]

    def insert_place(self, place: Place) -> int:
        """Saves a new place; duplicate names are not allowed."""
        sql = f"INSERT INTO places ({', '.join(PLACE_COLUMNS)}) VALUES (?, ?, ?, ?)"
        try:
            return self._execute(sql, [getattr(place, c) for c in PLACE_COLUMNS]).lastrowid
        except sqlite3.IntegrityError as error:
            raise ValueError(f"Ort '{place.name}' existiert bereits") from error

    def update_place(self, place: Place):
        """Overwrites an existing place."""
        assignments = ", ".join(f"{c} = ?" for c in PLACE_COLUMNS)
        try:
            self._execute(f"UPDATE places SET {assignments} WHERE id = ?",
                          [getattr(place, c) for c in PLACE_COLUMNS] + [place.id])
        except sqlite3.IntegrityError as error:
            raise ValueError(f"Ort '{place.name}' existiert bereits") from error

    def delete_place(self, place_id: int):
        """Deletes a place."""
        self._execute("DELETE FROM places WHERE id = ?", [place_id])  # keep the tasks, location_id -> NULL

    # --- Helpers ---------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        """Opens a connection with foreign keys enabled."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _execute(self, sql: str, params=()) -> sqlite3.Cursor:
        """Runs a writing statement in a transaction."""
        with closing(self._connect()) as conn, conn:  # second "conn" = transaction (commit/rollback)
            return conn.execute(sql, params)

    def _query(self, sql: str, params=()) -> list:
        """Runs a query and returns all rows."""
        with closing(self._connect()) as conn:
            return conn.execute(sql, params).fetchall()

    @staticmethod
    def _migrate(conn: sqlite3.Connection):
        """Extends older databases without the place column (existing tasks are kept)."""
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
        if "location_id" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN location_id INTEGER REFERENCES places(id) ON DELETE SET NULL")

    @staticmethod
    def _to_row(task: Task) -> dict:
        """Converts a task into column values (tags as JSON text)."""
        row = task.to_dict()
        row["tags"] = json.dumps(row["tags"], ensure_ascii=False)
        row["done"] = int(row["done"])
        return row

    @staticmethod
    def _to_task(row: sqlite3.Row) -> Task:
        """Converts a database row into a task."""
        data = dict(row)
        data["tags"] = json.loads(data["tags"] or "[]")
        return Task.from_dict(data)

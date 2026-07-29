"""Durable sale log for the live auction.

Every sale is committed to SQLite the moment it is entered, so a crashed
laptop, a closed lid or a kicked power cable costs at most the lot currently
on the clock. Three hours of entered sales living only in a Python process is
not a risk worth taking for the sake of avoiding one file.

The log is the source of truth: `LiveAuction` recomputes every derived figure
from it rather than persisting budgets or roster counts, so there is no
possibility of a stored total disagreeing with the sales that produced it.
Undo pops the last row, which is why the table is keyed by sequence.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from data.models import Position
from engine.live_auction import Sale

SCHEMA = """
CREATE TABLE IF NOT EXISTS sales (
    sequence    INTEGER PRIMARY KEY,
    player_id   TEXT NOT NULL,
    player_name TEXT NOT NULL,
    team        TEXT NOT NULL,
    price       INTEGER NOT NULL,
    position    TEXT,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class AuctionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False because FastAPI runs sync handlers on a
        # threadpool, so the connection opened at startup is used from worker
        # threads. The lock is what actually makes that safe -- without it this
        # crashes on the first sale entered at the table.
        self._connection = sqlite3.connect(
            self.path, isolation_level=None, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._connection.execute(SCHEMA)

    def append(self, sale: Sale) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT OR REPLACE INTO sales "
                "(sequence, player_id, player_name, team, price, position) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    sale.sequence, sale.player_id, sale.player_name,
                    sale.team, sale.price, sale.position.value if sale.position else None,
                ),
            )

    def pop(self) -> None:
        """Drop the highest-sequence row, mirroring an undo in memory."""
        with self._lock:
            self._connection.execute(
                "DELETE FROM sales WHERE sequence = (SELECT MAX(sequence) FROM sales)"
            )

    def load(self) -> list[Sale]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM sales ORDER BY sequence").fetchall()
        return [
            Sale(
                sequence=row["sequence"],
                player_id=row["player_id"],
                player_name=row["player_name"],
                team=row["team"],
                price=row["price"],
                position=Position(row["position"]) if row["position"] else None,
            )
            for row in rows
        ]

    def clear(self) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM sales")

    def close(self) -> None:
        self._connection.close()

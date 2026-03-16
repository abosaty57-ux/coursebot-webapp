"""
Shared database helper — used by both the bot and the web app.
The bot writes to it directly (same machine / Railway volume).
"""
import os
import sqlite3
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "qa.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS qa (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                q_no       TEXT UNIQUE NOT NULL,
                question   TEXT NOT NULL,
                answer     TEXT NOT NULL,
                track      TEXT DEFAULT '',
                lecture    TEXT DEFAULT '',
                date_added TEXT DEFAULT ''
            )
        """)
        conn.commit()


def add_entry(q_no: str, question: str, answer: str, track: str, lecture: str) -> str:
    """Insert or replace a Q&A entry. Returns q_no."""
    date_added = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO qa (q_no, question, answer, track, lecture, date_added) VALUES (?,?,?,?,?,?)",
            (q_no, question, answer, track, lecture, date_added)
        )
        conn.commit()
    return q_no


def next_q_no() -> str:
    with get_db() as conn:
        rows = conn.execute("SELECT q_no FROM qa").fetchall()
    nums = [
        int(r["q_no"][1:]) for r in rows
        if r["q_no"].startswith("Q") and r["q_no"][1:].isdigit()
    ]
    return f"Q{(max(nums, default=0) + 1):03d}"


def import_from_excel(excel_path: str):
    """One-time import of existing Excel data into SQLite."""
    try:
        import pandas as pd
        df = pd.read_excel(excel_path, dtype=str).fillna("")
        df.columns = [c.strip() for c in df.columns]
        init_db()
        with get_db() as conn:
            for _, row in df.iterrows():
                conn.execute(
                    "INSERT OR IGNORE INTO qa (q_no, question, answer, track, lecture, date_added) VALUES (?,?,?,?,?,?)",
                    (
                        row.get("Q_No", ""),
                        row.get("Question", ""),
                        row.get("Answer", ""),
                        row.get("Track", ""),
                        row.get("Lecture", ""),
                        row.get("Date Added", ""),
                    )
                )
            conn.commit()
        print(f"Imported {len(df)} rows from {excel_path}")
    except Exception as e:
        print(f"Excel import failed: {e}")

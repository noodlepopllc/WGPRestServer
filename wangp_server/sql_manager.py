import sqlite3
import time
import json

class JobDB:
    VALID_STATES = {
        "pending",
        "running",
        "complete",
        "errored",
        "cancel",
        "cancelled",
        "killed"
    }

    def __init__(self, path):
        self.path = path
        self._ensure_tables()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _ensure_tables(self):
        conn = self._connect()
        cur = conn.cursor()

        # Canonical job table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_pid INTEGER,
                child_pid INTEGER,
                input_json TEXT,
                output_json TEXT,
                state TEXT NOT NULL
            );
        """)

        # Append-only update log
        cur.execute("""
            CREATE TABLE IF NOT EXISTS job_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                progress REAL,
                message TEXT,
                timestamp REAL NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
        """)

        conn.commit()
        conn.close()

    # ---------------------------------------------------------
    # JOBS TABLE (canonical state)
    # ---------------------------------------------------------

    def insert_job(self, parent_pid, child_pid, input_json):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO jobs (parent_pid, child_pid, input_json, state)
            VALUES (?, ?, ?, ?)
        """, (parent_pid, child_pid, json.dumps(input_json), "pending"))
        job_id = cur.lastrowid
        conn.commit()
        conn.close()
        return job_id

    def set_job_state(self, job_id, state, output=None):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            UPDATE jobs
            SET state = ?, output_json = ?
            WHERE id = ?
        """, (state, output, job_id))
        conn.commit()
        conn.close()


    def any_job_running(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM jobs WHERE state='running' LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()
        return row[0] if row else 0


    def get_job(self, job_id):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        row = cur.fetchone()
        conn.close()
        return row

    def get_all_jobs(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM jobs ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()
        return rows

    # ---------------------------------------------------------
    # JOB UPDATES TABLE (append-only)
    # ---------------------------------------------------------

    def add_job_update(self, job_id, progress=None, message=None):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO job_updates (job_id, progress, message, timestamp)
            VALUES (?, ?, ?, ?)
        """, (job_id, progress, message, time.time()))
        conn.commit()
        conn.close()

    def get_latest_update(self, job_id):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT progress, message, timestamp
            FROM job_updates
            WHERE job_id=?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (job_id,))
        row = cur.fetchone()
        conn.close()
        return row

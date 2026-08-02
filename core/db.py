"""
db.py — Centralised PostgreSQL connection pool for ArticulateX.

Provides:
    init_pool()   — call once at app startup (before init_db)
    get_conn()    — context manager; yields a connection from the pool
    close_pool()  — call at shutdown to release all connections

Connection lifecycle inside get_conn():
    1. Clean exit  → conn.commit(), then conn returned to pool.
    2. Exception   → conn.rollback(), then conn returned to pool, exception re-raised.
    3. Caller catches an error (e.g. UniqueViolation) and calls conn.rollback()
       inside the with-block → the context manager's clean-exit path runs
       conn.commit(), which is a no-op on the fresh transaction state after
       rollback.  The connection is returned to the pool in a healthy state.

    In ALL cases the connection is returned to the pool via a finally block,
    so connections are never leaked.
"""

import os
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
DATABASE_URL: str | None = os.getenv("DATABASE_URL")
_pool: pool.ThreadedConnectionPool | None = None


def init_pool(minconn: int = 2, maxconn: int = 10) -> None:
    """
    Create the global connection pool.

    Must be called exactly once at application startup (before init_db).
    Reads DATABASE_URL from the environment.
    """
    global _pool, DATABASE_URL

    # Re-read in case .env was loaded after module import
    DATABASE_URL = os.getenv("DATABASE_URL")

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Set it to your Neon connection string "
            "(e.g. postgresql://user:pass@host/db?sslmode=require)."
        )

    _pool = pool.ThreadedConnectionPool(minconn, maxconn, DATABASE_URL)
    print(f"[DB] Connection pool created (min={minconn}, max={maxconn})")


@contextmanager
def get_conn():
    """
    Context manager that checks out a connection from the pool.

    Usage
    -----
    Normal query (auto-committed on success):

        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ...")

    Insert-once guard (caller catches UniqueViolation):

        with get_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute("INSERT ...")
            except psycopg2.errors.UniqueViolation:
                conn.rollback()   # ← clears the aborted transaction
                # continue — context manager will commit (no-op) and
                # return the connection to the pool in a clean state.

    Guarantees
    ----------
    • On clean exit: conn.commit() then pool.putconn(conn).
    • On unhandled exception: conn.rollback() then pool.putconn(conn),
      then the exception is re-raised.
    • The connection is ALWAYS returned to the pool (finally block),
      even if commit() or rollback() itself raises.
    """
    if _pool is None:
        raise RuntimeError(
            "Connection pool is not initialised. Call init_pool() first."
        )

    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def close_pool() -> None:
    """
    Close every connection in the pool.

    Call once at application shutdown (optional but good hygiene).
    """
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        print("[DB] Connection pool closed")

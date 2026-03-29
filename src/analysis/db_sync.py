"""Shared database helper for analysis (psycopg2 synchronous — read-heavy workloads)."""

import os

import psycopg2

from shared.config import DB_CONFIG


def get_connection():
    """Get a synchronous psycopg2 connection for analysis queries."""
    connect_timeout = int(os.environ.get("ANALYSIS_DB_CONNECT_TIMEOUT_SECONDS", os.environ.get("POSTGRES_CONNECT_TIMEOUT", "5")))
    statement_timeout_ms = int(
        os.environ.get("ANALYSIS_DB_STATEMENT_TIMEOUT_MS", os.environ.get("POSTGRES_STATEMENT_TIMEOUT_MS", "60000"))
    )
    return psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        dbname=DB_CONFIG["database"],
        connect_timeout=max(1, connect_timeout),
        application_name="polyedge-analysis",
        options=(f"-c statement_timeout={statement_timeout_ms}" if statement_timeout_ms > 0 else None),
    )

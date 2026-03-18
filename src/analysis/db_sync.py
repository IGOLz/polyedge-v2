"""Shared database helper for analysis (psycopg2 synchronous — read-heavy workloads)."""

import os

import psycopg2

from shared.config import DB_CONFIG


def get_connection():
    """Get a synchronous psycopg2 connection for analysis queries."""
    return psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        dbname=DB_CONFIG["database"],
    )

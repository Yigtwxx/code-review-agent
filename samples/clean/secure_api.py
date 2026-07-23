"""Hardened counterpart of samples/vulnerable/vulnerable_api.py.

Used as the false-positive control set: a review of this file should produce no
high or critical findings.
"""

import hashlib
import os
import secrets
import sqlite3
import subprocess
from html import escape
from pathlib import Path

import requests
from flask import Flask, abort, request

app = Flask(__name__)

# Credentials come from the environment; nothing sensitive is in source.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

REPORTS_ROOT = Path("/var/reports").resolve()
ALLOWED_PING_HOSTS = frozenset({"api.example.com", "cdn.example.com"})


def get_user(username: str) -> list[tuple[str, str, str]]:
    """Look up a user by name using a parameterised statement."""
    with sqlite3.connect("app.db") as conn:
        cursor = conn.execute(
            "SELECT id, email, role FROM users WHERE username = ?", (username,)
        )
        return cursor.fetchall()


@app.route("/search")
def search() -> str:
    term = request.args.get("q", "")
    with sqlite3.connect("app.db") as conn:
        rows = conn.execute(
            "SELECT id, name FROM products WHERE name LIKE ?", (f"%{term}%",)
        ).fetchall()
    # Output is escaped, so user input cannot become markup.
    return f"<h1>Results for {escape(term)}</h1><p>{escape(str(rows))}</p>"


@app.route("/ping")
def ping() -> str:
    host = request.args.get("host", "")
    if host not in ALLOWED_PING_HOSTS:
        abort(400, "Host is not on the allow list")
    # No shell, and the argument list is fixed.
    result = subprocess.run(
        ["/sbin/ping", "-c", "1", host],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.stdout


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a password hash with a memory-hard KDF."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return digest, salt


def fetch_profile(url: str) -> str:
    """Fetch a profile from a vetted host with certificate verification on."""
    if not url.startswith("https://api.example.com/"):
        raise ValueError("Refusing to fetch from an untrusted host")
    return requests.get(url, timeout=10).text


def read_report(name: str) -> str:
    """Read a report, refusing any path that escapes the reports directory."""
    candidate = (REPORTS_ROOT / name).resolve()
    if not candidate.is_relative_to(REPORTS_ROOT):
        raise ValueError("Path escapes the reports directory")
    return candidate.read_text(encoding="utf-8")


if __name__ == "__main__":
    app.run(host="127.0.0.1", debug=False)

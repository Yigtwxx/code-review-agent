"""Deliberately vulnerable Flask API used as review fixture.

DO NOT DEPLOY. Every defect here is intentional; the inline comments mark each one.
"""

import hashlib
import os
import pickle
import sqlite3
import subprocess

import requests
from flask import Flask, request

app = Flask(__name__)

# Hardcoded credentials committed to source control.
STRIPE_SECRET_KEY = "sk_live_EXAMPLEFIXTURENOTAREALKEY000000"
DB_PASSWORD = "EXAMPLE-FIXTURE-NOT-REAL-PASSWORD"
AWS_ACCESS_KEY_ID = "AKIAEXAMPLEFIXTURE00"


def get_user(username):
    """Look up a user by name."""
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    # SQL injection: the username is concatenated straight into the statement.
    query = "SELECT id, email, role FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchall()


@app.route("/search")
def search():
    term = request.args.get("q")
    conn = sqlite3.connect("app.db")
    rows = conn.execute(f"SELECT * FROM products WHERE name LIKE '%{term}%'").fetchall()
    # Reflected XSS: user input is interpolated into HTML without escaping.
    return f"<h1>Results for {term}</h1><p>{rows}</p>"


@app.route("/calc")
def calculate():
    expression = request.args.get("expr")
    # Remote code execution through eval on user input.
    return str(eval(expression))


@app.route("/ping")
def ping():
    host = request.args.get("host")
    # Command injection: shell=True with an interpolated argument.
    output = subprocess.check_output(f"ping -c 1 {host}", shell=True)
    return output


@app.route("/load", methods=["POST"])
def load_state():
    # Insecure deserialization of attacker-controlled bytes.
    return str(pickle.loads(request.data))


def hash_password(password):
    # MD5 is not a password hash.
    return hashlib.md5(password.encode()).hexdigest()


def fetch_profile(url):
    # TLS verification disabled, and the URL is unvalidated (SSRF).
    return requests.get(url, verify=False, timeout=10).text


def read_report(name):
    # Path traversal: the caller controls the whole path.
    with open(os.path.join("/var/reports", name)) as handle:
        return handle.read()


if __name__ == "__main__":
    # Debug mode exposes the Werkzeug console; binding to 0.0.0.0 exposes it.
    app.run(host="0.0.0.0", debug=True)

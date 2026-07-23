"""Layer classification decides which agents see a file."""

import pytest

from app.agents.partition import classify, partition
from app.schemas.finding import Layer
from app.schemas.source import Language, SourceFile


def make(path: str, content: str = "", language: Language = Language.PYTHON):
    return SourceFile(path=path, content=content, language=language)


@pytest.mark.parametrize(
    ("path", "language", "expected"),
    [
        ("components/Card.tsx", Language.TSX, Layer.FRONTEND),
        ("src/styles/main.css", Language.CSS, Layer.FRONTEND),
        ("api/routes/orders.py", Language.PYTHON, Layer.BACKEND),
        ("db/migrations/0001_init.sql", Language.SQL, Layer.DATABASE),
        ("Dockerfile", Language.DOCKERFILE, Layer.CONFIG_INFRA),
        ("deploy/compose.yml", Language.YAML, Layer.CONFIG_INFRA),
    ],
)
def test_path_and_language_decide_the_layer(path, language, expected) -> None:
    assert expected in classify(make(path, language=language))


def test_react_import_makes_a_plain_file_frontend() -> None:
    source = make(
        "widget.jsx",
        "import React from 'react';\nexport const W = () => <div/>;",
        Language.JAVASCRIPT,
    )

    assert Layer.FRONTEND in classify(source)


def test_fastapi_import_makes_a_plain_file_backend() -> None:
    source = make("handler.py", "from fastapi import APIRouter\nrouter = APIRouter()")

    assert Layer.BACKEND in classify(source)


def test_raw_sql_makes_a_plain_file_database() -> None:
    source = make("report.py", 'q = "SELECT id FROM orders"\nconn.execute(q)')

    assert Layer.DATABASE in classify(source)


def test_a_file_can_belong_to_two_layers() -> None:
    """A route handler that also queries the database is reviewed by both."""
    source = make(
        "api/orders.py",
        "from fastapi import APIRouter\n"
        "import sqlite3\n"
        'conn.execute("SELECT * FROM orders")\n',
    )

    layers = classify(source)

    assert Layer.BACKEND in layers
    assert Layer.DATABASE in layers


def test_unrecognised_file_falls_back_to_generic() -> None:
    assert classify(make("thing.py", "x = 1")) == [Layer.GENERIC]


def test_partition_annotates_each_file_and_groups_them() -> None:
    files = [
        make("components/Card.tsx", "", Language.TSX),
        make("api/main.py", "from fastapi import FastAPI"),
    ]

    grouped = partition(files)

    assert files[0].layers == [Layer.FRONTEND.value]
    assert Layer.BACKEND in grouped
    assert grouped[Layer.FRONTEND] == [files[0]]

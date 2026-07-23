"""Assign each file to one or more architectural layers.

This is deliberately deterministic: path shape first, then what the file
imports and calls. An LLM classifier would add a slow, non-reproducible step
before the work that actually needs a model, and would make two runs of the
same review disagree about which agents even ran.

A file may belong to several layers - a Next.js server action is both frontend
and backend - and is then reviewed by each, with duplicates removed later.
"""

import re
from pathlib import PurePosixPath

from app.schemas.finding import Layer
from app.schemas.source import Language, SourceFile

#: Directory names that place a file in a layer regardless of content.
_PATH_MARKERS: tuple[tuple[Layer, frozenset[str]], ...] = (
    (
        Layer.FRONTEND,
        frozenset(
            {
                "frontend",
                "client",
                "components",
                "ui",
                "pages",
                "views",
                "screens",
                "hooks",
                "styles",
                "public",
                "static",
            }
        ),
    ),
    (
        Layer.BACKEND,
        frozenset(
            {
                "backend",
                "server",
                "api",
                "routes",
                "routers",
                "controllers",
                "services",
                "handlers",
                "endpoints",
                "middleware",
                "usecases",
                "domain",
            }
        ),
    ),
    (
        Layer.DATABASE,
        frozenset(
            {
                "db",
                "database",
                "models",
                "entities",
                "migrations",
                "migration",
                "schema",
                "schemas",
                "repositories",
                "repository",
                "dao",
                "queries",
                "prisma",
                "alembic",
            }
        ),
    ),
    (
        Layer.CONFIG_INFRA,
        frozenset(
            {
                "config",
                "configs",
                "settings",
                "deploy",
                "deployment",
                "infra",
                "infrastructure",
                "terraform",
                "helm",
                "charts",
                "k8s",
                "kubernetes",
                ".github",
                ".circleci",
                "nginx",
                "docker",
            }
        ),
    ),
)

#: Filenames that are configuration wherever they sit.
_CONFIG_FILENAMES = frozenset(
    {
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "nginx.conf",
        "makefile",
        "procfile",
        ".env",
        ".npmrc",
        "vercel.json",
        "netlify.toml",
    }
)

_LANGUAGE_LAYER: dict[Language, Layer] = {
    Language.TSX: Layer.FRONTEND,
    Language.JSX: Layer.FRONTEND,
    Language.CSS: Layer.FRONTEND,
    Language.HTML: Layer.FRONTEND,
    Language.SQL: Layer.DATABASE,
    Language.DOCKERFILE: Layer.CONFIG_INFRA,
    Language.YAML: Layer.CONFIG_INFRA,
    Language.SHELL: Layer.CONFIG_INFRA,
}

#: Content signals, checked when the path is not decisive.
_CONTENT_SIGNALS: tuple[tuple[Layer, re.Pattern[str]], ...] = (
    (
        Layer.FRONTEND,
        re.compile(
            r"""(?x)
            \bfrom\s+['"]react['"] | \bimport\s+React\b | \buseState\s*\( |
            \buseEffect\s*\( | \bdocument\.(getElementById|querySelector|write) |
            \bwindow\. | \blocalStorage\b | \bdangerouslySetInnerHTML\b |
            \bfrom\s+['"]vue['"] | \bfrom\s+['"]svelte['"] | \bnext/(link|router)\b
            """
        ),
    ),
    (
        Layer.BACKEND,
        re.compile(
            r"""(?x)
            \bfrom\s+fastapi\b | \bimport\s+flask\b | \bfrom\s+flask\b |
            \bfrom\s+django\b | \bimport\s+django\b |
            \bfrom\s+['"]express['"] | \brequire\(\s*['"]express['"] |
            \bfrom\s+['"]@nestjs/ | \b@(app|router)\.(get|post|put|delete|patch)\b |
            \bapp\.(get|post|put|delete|patch)\s*\( | \bAPIRouter\s*\( |
            \bhttp\.createServer\b
            """
        ),
    ),
    (
        Layer.DATABASE,
        re.compile(
            r"""(?x)
            \bimport\s+sqlite3\b | \bfrom\s+sqlalchemy\b | \bimport\s+psycopg2?\b |
            \bfrom\s+pymongo\b | \bimport\s+pymongo\b | \bfrom\s+beanie\b |
            \bfrom\s+['"](mysql2?|pg|mongoose|prisma|typeorm|knex|sequelize)['"] |
            \b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE)\b |
            \bALTER\s+TABLE\b |
            \b\.(query|execute|executemany|aggregate|find_one|insert_one)\s*\( |
            \bdeclarative_base\b | \bmodels\.Model\b
            """
        ),
    ),
    (
        Layer.CONFIG_INFRA,
        re.compile(
            r"""(?x)
            ^\s*FROM\s+\S+ | ^\s*(ENV|EXPOSE|ENTRYPOINT|CMD)\s | \bALLOWED_HOSTS\b |
            \bCORSMiddleware\b | \ballow_origins\b | \bDEBUG\s*=\s*True\b
            """,
            re.MULTILINE,
        ),
    ),
)


def classify(file: SourceFile) -> list[Layer]:
    """Return every layer that applies to `file`, most specific first."""
    layers: list[Layer] = []

    def add(layer: Layer) -> None:
        if layer not in layers:
            layers.append(layer)

    posix = PurePosixPath(file.path)
    parts = {part.lower() for part in posix.parts[:-1]}
    name = posix.name.lower()

    if name in _CONFIG_FILENAMES or name.startswith((".env", "dockerfile")):
        add(Layer.CONFIG_INFRA)

    for layer, markers in _PATH_MARKERS:
        if parts & markers:
            add(layer)

    language_layer = _LANGUAGE_LAYER.get(file.language)
    if language_layer is not None:
        add(language_layer)

    # Content signals refine rather than replace the path verdict: a file in
    # `api/` that also talks to the database belongs to both agents.
    for layer, pattern in _CONTENT_SIGNALS:
        if pattern.search(file.content):
            add(layer)

    if not layers:
        add(Layer.GENERIC)
    return layers


def partition(files: list[SourceFile]) -> dict[Layer, list[SourceFile]]:
    """Group files by layer, annotating each file with its layers."""
    grouped: dict[Layer, list[SourceFile]] = {}
    for file in files:
        layers = classify(file)
        file.layers = [layer.value for layer in layers]
        for layer in layers:
            grouped.setdefault(layer, []).append(file)
    return grouped

"""Check that imported third-party packages actually exist.

Addresses the failure mode the brief calls *hallucination in code*: a model
confidently importing a library that was never published. It applies to the
reviewed code too - a dependency that does not exist is a defect whoever wrote
it.

Standard-library and first-party modules are excluded, and a registry we cannot
reach means "unknown", never "does not exist". A false accusation of
hallucination would be worse than the miss.
"""

import asyncio
import logging
import re
import sys
from pathlib import PurePosixPath

import httpx

from app.schemas.source import Language, SourceFile

logger = logging.getLogger(__name__)

REGISTRY_TIMEOUT_SECONDS = 6

_PYTHON_IMPORT = re.compile(
    r"^\s*(?:from\s+([A-Za-z_][\w]*)|import\s+([A-Za-z_][\w]*))", re.MULTILINE
)
_JS_IMPORT = re.compile(
    r"""(?:from\s+|require\(\s*|import\(\s*)['"]([^'"]+)['"]""",
)

#: Import name -> distribution name, where the two differ.
_PYTHON_ALIASES = {
    "yaml": "PyYAML",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "jwt": "PyJWT",
    "dateutil": "python-dateutil",
    "attr": "attrs",
    "OpenSSL": "pyOpenSSL",
    "serial": "pyserial",
    "psycopg2": "psycopg2-binary",
    "google": "google-api-python-client",
}

_NODE_BUILTINS = frozenset(
    {
        "assert",
        "buffer",
        "child_process",
        "cluster",
        "console",
        "crypto",
        "dgram",
        "dns",
        "events",
        "fs",
        "http",
        "http2",
        "https",
        "module",
        "net",
        "os",
        "path",
        "perf_hooks",
        "process",
        "querystring",
        "readline",
        "stream",
        "string_decoder",
        "timers",
        "tls",
        "tty",
        "url",
        "util",
        "v8",
        "vm",
        "worker_threads",
        "zlib",
    }
)

#: Cache across a process run; the registries do not change mid-review.
_known: dict[tuple[str, str], bool | None] = {}


def extract_python_imports(content: str) -> set[str]:
    names = set()
    for from_module, import_module in _PYTHON_IMPORT.findall(content):
        name = from_module or import_module
        if name and name not in sys.stdlib_module_names:
            names.add(name)
    return names


def extract_js_imports(content: str) -> set[str]:
    names = set()
    for specifier in _JS_IMPORT.findall(content):
        if specifier.startswith((".", "/", "#")):
            continue  # relative or subpath import, not a package
        bare = specifier.removeprefix("node:")
        if bare in _NODE_BUILTINS:
            continue
        parts = bare.split("/")
        # Scoped packages keep two segments: @scope/name.
        names.add("/".join(parts[:2]) if bare.startswith("@") else parts[0])
    return names


def _local_module_names(files: list[SourceFile]) -> set[str]:
    """Top-level module and package names defined by the submission itself."""
    local: set[str] = set()
    for file in files:
        parts = PurePosixPath(file.path).parts
        if parts:
            local.add(PurePosixPath(parts[0]).stem)
        local.add(PurePosixPath(file.path).stem)
    return local


async def _exists(client: httpx.AsyncClient, ecosystem: str, name: str) -> bool | None:
    """True/False if the registry answered, None if it could not be reached."""
    cached = _known.get((ecosystem, name))
    if (ecosystem, name) in _known:
        return cached

    url = (
        f"https://pypi.org/pypi/{name}/json"
        if ecosystem == "pypi"
        else f"https://registry.npmjs.org/{name}"
    )
    try:
        response = await client.get(url, follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.info("Registry %s unreachable for %s: %s", ecosystem, name, exc)
        return None

    if response.status_code == 404:
        result: bool | None = False
    elif response.is_success:
        result = True
    else:
        result = None

    _known[(ecosystem, name)] = result
    return result


async def find_unknown_packages(
    files: list[SourceFile],
) -> dict[str, list[tuple[str, str]]]:
    """Map file path -> [(package, ecosystem)] for packages no registry knows.

    An unreachable registry yields an empty result rather than a false alarm.
    """
    local = _local_module_names(files)
    wanted: dict[str, set[tuple[str, str]]] = {}

    for file in files:
        if file.language is Language.PYTHON:
            names = {
                _PYTHON_ALIASES.get(name, name)
                for name in extract_python_imports(file.content)
                if name not in local
            }
            ecosystem = "pypi"
        elif file.language in {
            Language.TYPESCRIPT,
            Language.TSX,
            Language.JAVASCRIPT,
            Language.JSX,
        }:
            names = {n for n in extract_js_imports(file.content) if n not in local}
            ecosystem = "npm"
        else:
            continue

        if names:
            wanted[file.path] = {(name, ecosystem) for name in names}

    if not wanted:
        return {}

    unique = sorted({item for items in wanted.values() for item in items})
    async with httpx.AsyncClient(timeout=REGISTRY_TIMEOUT_SECONDS) as client:
        verdicts = await asyncio.gather(
            *(_exists(client, ecosystem, name) for name, ecosystem in unique)
        )

    missing = {
        item for item, verdict in zip(unique, verdicts, strict=True) if verdict is False
    }
    if not missing:
        return {}

    return {
        path: sorted(items & missing)
        for path, items in wanted.items()
        if items & missing
    }

"""Benchmark harness for the Code Review Agent.

Measures Detection Rate, False Positive Rate, Fix Accuracy and Latency across
models and across three configurations (static-only / LLM-only / hybrid), using
the labeled fixtures in ``samples/`` as the gold set.

The harness lives outside ``backend/`` but drives ``app.*`` directly, so importing
this package puts the backend source on ``sys.path``. It talks to the compiled
LangGraph with no database, exactly like the tests do. Run it with the backend
uv environment::

    uv run --project backend python -m benchmarks.run --help
"""

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

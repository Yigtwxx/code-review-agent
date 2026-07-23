"""Review endpoints, with the graph stubbed so no model is needed."""

import io
import zipfile
from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.agents.state import PatchResult
from app.db.models import Review, ReviewStatus
from app.schemas.finding import Finding, Layer, Lens, Origin, Severity
from app.services import reviews as service

VULNERABLE = 'import os\nAPI_KEY = "sk_live_abcdef0123456789xyz"\nprint(API_KEY)\n'


class StubGraph:
    """Stands in for the LangGraph pipeline; records what it was asked to do."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def ainvoke(self, state: dict, config: dict | None = None) -> dict:
        self.calls.append(state)
        files = state["files"]
        return {
            "files": files,
            "findings": [
                Finding(
                    file_path=files[0].path,
                    line_start=2,
                    line_end=2,
                    severity=Severity.CRITICAL,
                    category="hardcoded-secret",
                    title="Hardcoded API key",
                    explanation="Kaynak koda gömülü kimlik bilgisi.",
                    suggested_fix='API_KEY = os.environ["API_KEY"]',
                    origin=Origin.HYBRID,
                    tool="bandit",
                    rule_id="B105",
                    agent="BackendAgent",
                    lens=Lens.SECURITY,
                    layer=Layer.BACKEND,
                    confidence=0.95,
                    corroborated_by=["bandit:B105"],
                )
            ],
            "patches": [
                PatchResult(
                    file_path=files[0].path,
                    refactored_code='import os\nAPI_KEY = os.environ["API_KEY"]\n',
                    unified_diff="--- a\n+++ b\n",
                    addresses_findings=1,
                    validated=True,
                    validation_output="ok",
                    notes="Secret ortam değişkenine taşındı.",
                )
            ],
            "risk_score": 25,
            "suppressed_low_confidence": 2,
        }


@pytest.fixture
def stub_graph(monkeypatch: pytest.MonkeyPatch) -> Iterator[StubGraph]:
    graph = StubGraph()
    monkeypatch.setattr(service, "review_graph", graph)
    yield graph


async def start_paste_review(client: AsyncClient, content: str = VULNERABLE) -> dict:
    response = await client.post(
        "/api/v1/reviews/paste", json={"filename": "app.py", "content": content}
    )
    assert response.status_code == 202, response.text
    return response.json()


async def test_paste_starts_a_review_and_runs_it(
    auth_client: AsyncClient, stub_graph: StubGraph
) -> None:
    review = await start_paste_review(auth_client)

    detail = await auth_client.get(f"/api/v1/reviews/{review['id']}")
    body = detail.json()

    assert body["status"] == ReviewStatus.COMPLETED
    assert body["risk_score"] == 25
    assert body["stats"]["total_findings"] == 1
    assert body["stats"]["suppressed_low_confidence"] == 2
    assert [f["path"] for f in body["files"]] == ["app.py"]
    assert body["files"][0]["finding_count"] == 1


async def test_findings_are_persisted_with_their_provenance(
    auth_client: AsyncClient, stub_graph: StubGraph
) -> None:
    review = await start_paste_review(auth_client)

    findings = (
        await auth_client.get(f"/api/v1/reviews/{review['id']}/findings")
    ).json()

    assert len(findings) == 1
    assert findings[0]["origin"] == "hybrid"
    assert findings[0]["corroborated_by"] == ["bandit:B105"]
    assert findings[0]["agent"] == "BackendAgent"
    assert findings[0]["severity"] == "critical"


async def test_finding_can_be_dismissed(
    auth_client: AsyncClient, stub_graph: StubGraph
) -> None:
    review = await start_paste_review(auth_client)
    (finding,) = (
        await auth_client.get(f"/api/v1/reviews/{review['id']}/findings")
    ).json()

    response = await auth_client.patch(
        f"/api/v1/reviews/{review['id']}/findings/{finding['id']}",
        json={"status": "dismissed"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"


async def test_refactored_files_download_as_a_zip(
    auth_client: AsyncClient, stub_graph: StubGraph
) -> None:
    review = await start_paste_review(auth_client)

    response = await auth_client.get(f"/api/v1/reviews/{review['id']}/download")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "app.py" in archive.namelist()
        assert b"os.environ" in archive.read("app.py")


async def test_file_content_is_retrievable(
    auth_client: AsyncClient, stub_graph: StubGraph
) -> None:
    review = await start_paste_review(auth_client)

    response = await auth_client.get(f"/api/v1/reviews/{review['id']}/files/app.py")

    assert response.status_code == 200
    assert response.json()["content"] == VULNERABLE


async def test_upload_accepts_a_zip_archive(
    auth_client: AsyncClient, stub_graph: StubGraph
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("src/app.py", VULNERABLE)

    response = await auth_client.post(
        "/api/v1/reviews/upload",
        files={"files": ("bundle.zip", buffer.getvalue(), "application/zip")},
    )

    assert response.status_code == 202, response.text
    assert stub_graph.calls
    assert stub_graph.calls[0]["files"][0].path == "src/app.py"


async def test_upload_without_reviewable_files_is_rejected(
    auth_client: AsyncClient, stub_graph: StubGraph
) -> None:
    response = await auth_client.post(
        "/api/v1/reviews/upload",
        files={"files": ("logo.png", b"\x89PNG\r\n", "image/png")},
    )

    assert response.status_code == 400


async def test_pull_request_url_must_be_a_github_pr(
    auth_client: AsyncClient, stub_graph: StubGraph
) -> None:
    response = await auth_client.post(
        "/api/v1/reviews/pull-request",
        json={"url": "https://example.com/not-a-pr"},
    )

    assert response.status_code == 400
    assert "pull request URL" in response.json()["detail"]


async def test_a_graph_failure_marks_the_review_failed(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Exploding:
        async def ainvoke(self, state, config=None):
            raise RuntimeError("model exploded")

    monkeypatch.setattr(service, "review_graph", Exploding())

    review = await start_paste_review(auth_client)
    body = (await auth_client.get(f"/api/v1/reviews/{review['id']}")).json()

    assert body["status"] == ReviewStatus.FAILED
    assert "model exploded" in body["error"]


async def test_reviews_are_listed_newest_first(
    auth_client: AsyncClient, stub_graph: StubGraph
) -> None:
    await start_paste_review(auth_client)
    await start_paste_review(auth_client)

    listed = (await auth_client.get("/api/v1/reviews")).json()

    assert len(listed) == 2
    assert listed[0]["created_at"] >= listed[1]["created_at"]


async def test_another_users_review_is_not_reachable(
    auth_client: AsyncClient, client: AsyncClient, stub_graph: StubGraph
) -> None:
    review = await start_paste_review(auth_client)

    registration = await client.post(
        "/api/v1/auth/register",
        json={"email": "mallory@example.com", "password": "another-strong-pass"},
    )
    intruder_token = registration.json()["access_token"]
    headers = {"Authorization": f"Bearer {intruder_token}"}

    for path in ("", "/findings", "/patches", "/files/app.py"):
        response = await client.get(
            f"/api/v1/reviews/{review['id']}{path}", headers=headers
        )
        assert response.status_code == 404, path

    assert (await client.get("/api/v1/reviews", headers=headers)).json() == []


async def test_deleting_a_review_removes_its_children(
    auth_client: AsyncClient, stub_graph: StubGraph
) -> None:
    review = await start_paste_review(auth_client)

    assert (
        await auth_client.delete(f"/api/v1/reviews/{review['id']}")
    ).status_code == 204
    assert (
        await auth_client.get(f"/api/v1/reviews/{review['id']}/findings")
    ).status_code == 404
    assert await Review.find_all().count() == 0


async def test_review_endpoints_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/reviews")).status_code == 401
    assert (
        await client.post(
            "/api/v1/reviews/paste", json={"filename": "a.py", "content": "x = 1"}
        )
    ).status_code == 401

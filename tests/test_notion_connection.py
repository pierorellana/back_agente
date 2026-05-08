from typing import Any

from fastapi.testclient import TestClient

from app.application.dtos.responses.general_response import GeneralResponse
from app.application.dtos.responses.notion_connection_response import NotionConnectionResponse
from app.main import app


class FakeNotionConnectionService:
    def verify_connection(self) -> GeneralResponse[NotionConnectionResponse]:
        return GeneralResponse(
            success=True,
            message="Notion connection is working",
            data=NotionConnectionResponse(
                connected=True,
                database_id="0d2ea5c2-bc95-4dff-b871-d7c4565887e9",
                database_title="Healthcare Copay Estimator Hackathon Notion DB Schema",
                data_source_id="11111111-1111-1111-1111-111111111111",
                data_source_name="Patients",
                data_source_count=1,
                properties=["Name"],
                sample_page_count=1,
                has_more_pages=False,
                notion_version="2026-03-11",
            ),
        )


def test_notion_connection_endpoint() -> None:
    from app.api.deps import get_notion_connection_service

    def override_service() -> Any:
        return FakeNotionConnectionService()

    app.dependency_overrides[get_notion_connection_service] = override_service
    client = TestClient(app)

    response = client.get("/api/notion/connection")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["connected"] is True
    assert body["data"]["data_source_id"] == "11111111-1111-1111-1111-111111111111"

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.application.dtos.responses.general_response import GeneralResponse
from app.application.services.insurance_catalog_service import _notion_page_to_record
from app.main import app


class FakeInsuranceCatalogService:
    def list_providers(self) -> GeneralResponse[list[dict[str, Any]]]:
        return _fake_catalog_response(
            "Insurance providers loaded",
            [{"provider_id": "prov_001", "provider_name": "Demo Provider"}],
        )

    def list_plans(self) -> GeneralResponse[list[dict[str, Any]]]:
        return _fake_catalog_response(
            "Insurance plans loaded",
            [{"plan_id": "plan_001", "plan_name": "Demo Plan"}],
        )

    def list_users(self) -> GeneralResponse[list[dict[str, Any]]]:
        return _fake_catalog_response("Users loaded", [{"user_id": "user_001"}])

    def list_specialties(self) -> GeneralResponse[list[dict[str, Any]]]:
        return _fake_catalog_response("Specialties loaded", [{"specialty_id": "spec_001"}])

    def list_hospitals(self) -> GeneralResponse[list[dict[str, Any]]]:
        return _fake_catalog_response("Hospitals loaded", [{"hospital_id": "hosp_001"}])

    def list_symptoms(self) -> GeneralResponse[list[dict[str, Any]]]:
        return _fake_catalog_response("Symptoms loaded", [{"symptom_id": "symp_001"}])

    def list_hospital_specialties(self) -> GeneralResponse[list[dict[str, Any]]]:
        return _fake_catalog_response(
            "Hospital specialties loaded",
            [{"record_name": "Hospital specialty demo"}],
        )

    def list_symptom_specialty_map(self) -> GeneralResponse[list[dict[str, Any]]]:
        return _fake_catalog_response(
            "Symptom specialty map loaded",
            [{"map_id": "map_001", "Name": "Symptom to specialty demo"}],
        )

    def list_insurance_network(self) -> GeneralResponse[list[dict[str, Any]]]:
        return _fake_catalog_response(
            "Insurance network loaded",
            [{"network_id": "network_001", "Name": "Insurance network demo"}],
        )

    def list_emergency_keywords(self) -> GeneralResponse[list[dict[str, Any]]]:
        return _fake_catalog_response(
            "Emergency keywords loaded",
            [{"emergency_keyword_id": "emg_001", "phrase": "chest pain"}],
        )


def test_list_insurance_providers_endpoint() -> None:
    from app.api.deps import get_insurance_catalog_service

    def override_service() -> Any:
        return FakeInsuranceCatalogService()

    app.dependency_overrides[get_insurance_catalog_service] = override_service
    client = TestClient(app)

    response = client.get("/api/insurance-providers")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == [{"provider_id": "prov_001", "provider_name": "Demo Provider"}]
    assert "items" not in body["data"][0]


def test_list_insurance_plans_endpoint() -> None:
    from app.api.deps import get_insurance_catalog_service

    def override_service() -> Any:
        return FakeInsuranceCatalogService()

    app.dependency_overrides[get_insurance_catalog_service] = override_service
    client = TestClient(app)

    response = client.get("/api/insurance-plans")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == [{"plan_id": "plan_001", "plan_name": "Demo Plan"}]
    assert "items" not in body["data"][0]


@pytest.mark.parametrize(
    ("path", "expected_item"),
    [
        ("/api/users", {"user_id": "user_001"}),
        ("/api/specialties", {"specialty_id": "spec_001"}),
        ("/api/hospitals", {"hospital_id": "hosp_001"}),
        ("/api/symptoms", {"symptom_id": "symp_001"}),
        ("/api/hospital-specialties", {"record_name": "Hospital specialty demo"}),
        (
            "/api/symptom-specialty-map",
            {"map_id": "map_001", "Name": "Symptom to specialty demo"},
        ),
        (
            "/api/insurance-network",
            {"network_id": "network_001", "Name": "Insurance network demo"},
        ),
        (
            "/api/emergency-keywords",
            {"emergency_keyword_id": "emg_001", "phrase": "chest pain"},
        ),
    ],
)
def test_list_catalog_endpoints(path: str, expected_item: dict[str, Any]) -> None:
    from app.api.deps import get_insurance_catalog_service

    def override_service() -> Any:
        return FakeInsuranceCatalogService()

    app.dependency_overrides[get_insurance_catalog_service] = override_service
    client = TestClient(app)

    response = client.get(path)

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == [expected_item]
    assert "items" not in body["data"][0]


def test_notion_page_to_record_hides_internal_metadata() -> None:
    record = _notion_page_to_record(
        {
            "id": "page-id",
            "created_time": "2026-05-08T03:53:00.000Z",
            "last_edited_time": "2026-05-08T04:04:00.000Z",
            "archived": False,
            "properties": {
                "created_at": {
                    "type": "created_time",
                    "created_time": "2026-05-08T03:53:00.000Z",
                },
                "provider_id": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "prov_bluecare"}],
                },
                "provider_name": {
                    "type": "title",
                    "title": [{"plain_text": "BlueCare Health"}],
                },
            },
        }
    )

    assert record == {
        "provider_id": "prov_bluecare",
        "provider_name": "BlueCare Health",
    }


def _fake_catalog_response(
    message: str,
    data: list[dict[str, Any]],
) -> GeneralResponse[list[dict[str, Any]]]:
    return GeneralResponse(
        success=True,
        message=message,
        data=data,
    )

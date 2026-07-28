from __future__ import annotations

from app.core import classifier
from app.core.taxonomy import TAXONOMY


def test_taxonomy_endpoint_is_canonical(auth_client):
    response = auth_client.get("/api/v1/taxonomy")
    assert response.status_code == 200
    payload = response.json()
    assert payload["categories"] == TAXONOMY
    assert payload["category_names"] == list(TAXONOMY)
    assert "Bank Charges" in payload["categories"]["FINANCIAL OBLIGATIONS"]["subcategories"]


def test_classifier_uses_taxonomy_module_object():
    assert classifier.TAXONOMY is TAXONOMY


def test_api_errors_have_standard_shape(auth_client):
    response = auth_client.get("/api/v1/transactions/not-a-real-id")
    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "HTTP_404"
    assert payload["message"] == "Transaction not found"
    assert payload["hint"] is None
    assert payload["retriable"] is False

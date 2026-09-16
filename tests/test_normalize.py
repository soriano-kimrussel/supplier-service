from app.services import SupplierIngestionService

normalize = SupplierIngestionService.normalize


def test_maps_upstream_field_names():
    values = normalize({"id": 42, "company_name": " ACME ", "country_code": "de"})

    assert values["external_id"] == "42"
    assert values["name"] == "ACME"
    assert values["country"] == "DE"


def test_falls_back_to_name_and_defaults_status():
    values = normalize({"id": "SUP-9", "name": "Fallback Ltd"})

    assert values["name"] == "Fallback Ltd"
    assert values["status"] == "active"


def test_unknown_country_becomes_null_rather_than_garbage():
    assert normalize({"id": "1", "country": "Atlantis"})["country"] is None
    assert normalize({"id": "1", "country": ""})["country"] is None
    assert normalize({"id": "1", "country": None})["country"] is None


def test_keeps_the_raw_payload_for_debugging():
    raw = {"id": "1", "company_name": "ACME", "extra": {"vat": "NL123"}}

    assert normalize(raw)["source_payload"] == raw

import httpx

from tests.conftest import StubDirectory


async def test_ingest_normalises_and_stores_the_supplier(
    client: httpx.AsyncClient, directory: StubDirectory
):
    response = await client.post("/api/v1/ingestion/suppliers/SUP-1")

    assert response.status_code == 202
    body = response.json()
    assert body["created"] is True
    assert body["enrichment_job_id"] is not None
    assert body["supplier"]["name"] == "Northwind Foods"  # whitespace stripped
    assert body["supplier"]["country"] == "NL"  # "Netherlands" mapped to a code
    assert body["supplier"]["status"] == "active"  # lower-cased
    assert directory.calls == ["SUP-1"]


async def test_re_ingesting_updates_instead_of_duplicating(
    client: httpx.AsyncClient, directory: StubDirectory
):
    first = (await client.post("/api/v1/ingestion/suppliers/SUP-1")).json()

    directory.records["SUP-1"]["company_name"] = "Northwind Foods BV"
    second = (await client.post("/api/v1/ingestion/suppliers/SUP-1")).json()

    assert second["created"] is False
    assert second["supplier"]["id"] == first["supplier"]["id"]
    assert second["supplier"]["name"] == "Northwind Foods BV"
    assert second["enrichment_job_id"] != first["enrichment_job_id"]

    page = (await client.get("/api/v1/suppliers")).json()
    assert page["total"] == 1


async def test_supplier_unknown_upstream_returns_404(client: httpx.AsyncClient):
    response = await client.post("/api/v1/ingestion/suppliers/NOPE")

    assert response.status_code == 404


async def test_directory_outage_returns_502(
    client: httpx.AsyncClient, directory: StubDirectory
):
    directory.unavailable = True

    response = await client.post("/api/v1/ingestion/suppliers/SUP-1")

    assert response.status_code == 502

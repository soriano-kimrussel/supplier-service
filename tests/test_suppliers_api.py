import httpx


async def test_create_supplier_returns_201_and_the_stored_row(client: httpx.AsyncClient):
    response = await client.post(
        "/api/v1/suppliers",
        json={"name": "Northwind Foods", "external_id": "SUP-1", "country": "nl"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["external_id"] == "SUP-1"
    assert body["country"] == "NL"
    assert body["enrichment_status"] == "pending"
    assert body["id"] > 0


async def test_duplicate_external_id_is_rejected_with_409(client: httpx.AsyncClient):
    payload = {"name": "Northwind Foods", "external_id": "SUP-1"}
    assert (await client.post("/api/v1/suppliers", json=payload)).status_code == 201

    response = await client.post("/api/v1/suppliers", json=payload)

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_blank_name_is_rejected_before_it_reaches_the_service(
    client: httpx.AsyncClient,
):
    response = await client.post(
        "/api/v1/suppliers", json={"name": "   ", "external_id": "SUP-2"}
    )

    assert response.status_code == 422


async def test_unknown_supplier_returns_404(client: httpx.AsyncClient):
    response = await client.get("/api/v1/suppliers/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Supplier 999 not found"


async def test_list_paginates_and_filters_by_country(client: httpx.AsyncClient):
    for index, country in enumerate(["NL", "NL", "DE"]):
        await client.post(
            "/api/v1/suppliers",
            json={
                "name": f"Supplier {index}",
                "external_id": f"SUP-{index}",
                "country": country,
            },
        )

    page = (await client.get("/api/v1/suppliers", params={"limit": 1})).json()
    assert page["total"] == 3
    assert len(page["items"]) == 1

    dutch = (await client.get("/api/v1/suppliers", params={"country": "nl"})).json()
    assert dutch["total"] == 2
    assert {item["country"] for item in dutch["items"]} == {"NL"}


async def test_health_and_readiness(client: httpx.AsyncClient):
    assert (await client.get("/health")).json() == {"status": "ok"}

    ready = await client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] in ("AI Voice Form Builder", "AI Voice Form Assistant")
    assert data["database"] == "healthy"
    assert "ai_mode" in data

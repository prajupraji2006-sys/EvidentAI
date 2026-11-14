from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main, security


class FakeQuery:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.filters = []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class FakeAuth:
    def get_user(self, token):
        if token != "valid-test-token":
            raise ValueError("invalid token")
        return SimpleNamespace(user=SimpleNamespace(id="user-123"))


class FakeClient:
    def __init__(self):
        self.query = FakeQuery([])
        self.auth = FakeAuth()

    def table(self, _name):
        return self.query


def test_health_is_public_and_evidence_requires_authentication():
    client = TestClient(main.app)
    assert client.get("/api/health").status_code == 200
    response = client.get("/api/evidence")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication is required."


def test_valid_session_is_checked_and_incidents_are_scoped_to_user(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(security, "get_supabase_client", lambda: fake)
    monkeypatch.setattr(main, "get_supabase_client", lambda: fake)
    response = TestClient(main.app).get("/api/cases", headers={"Authorization": "Bearer valid-test-token"})
    assert response.status_code == 200
    assert response.json() == {"cases": []}
    assert ("owner_id", "user-123") in fake.query.filters


def test_invalid_session_returns_401(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(security, "get_supabase_client", lambda: fake)
    response = TestClient(main.app).get("/api/cases", headers={"Authorization": "Bearer expired-token"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


def test_profile_bootstrap_uses_authenticated_id_and_server_role(monkeypatch):
    class ProfileQuery:
        def __init__(self):
            self.created = None

        def select(self, *_args):
            return self

        def eq(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def insert(self, row):
            self.created = row
            return self

        def execute(self):
            return SimpleNamespace(data=[self.created] if self.created else [])

    query = ProfileQuery()
    fake = SimpleNamespace(table=lambda _name: query)
    monkeypatch.setattr(main, "get_supabase_client", lambda: fake)
    result = main.bootstrap_profile({"id": "auth-user-id"})
    assert result["created"] is True
    assert query.created["id"] == "auth-user-id"
    assert query.created["role"] == "investigator"


def test_timeline_and_graph_use_real_scoped_analysis(monkeypatch):
    main.app.dependency_overrides[security.authenticated_user] = lambda: {"id": "user-123"}
    monkeypatch.setattr(main, "list_evidence_records", lambda _user: [{
        "evidence_id": "e-1", "original_filename": "message.txt",
        "analysis": {
            "people": ["Asha"], "locations": ["Pune"], "dates": ["2026-11-02"],
            "events": [
                {"date_or_time": "2026-11-03", "description": "Later event"},
                {"date_or_time": "2026-11-01", "description": "Earlier event"},
            ],
        },
    }])
    try:
        client = TestClient(main.app)
        timeline = client.get("/api/timeline").json()["events"]
        assert [event["description"] for event in timeline] == ["Earlier event", "Later event"]
        graph = client.get("/api/graph").json()
        assert {node["label"] for node in graph["nodes"]} >= {"Asha", "Pune", "message.txt"}
        assert all(edge["evidence_id"] == "e-1" for edge in graph["edges"])
    finally:
        main.app.dependency_overrides.pop(security.authenticated_user, None)

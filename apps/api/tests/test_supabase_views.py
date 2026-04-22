"""
Tests for the Supabase read-only integration.

Covers:
  - supabase_client._fetch table allowlist enforcement
  - supabase_client helper functions (mocked httpx)
  - /kama-net/* router endpoints via FastAPI TestClient
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from fastapi.testclient import TestClient


# ── supabase_client unit tests ────────────────────────────────────────────────

class TestAllowedTables:
    """supabase_client._fetch rejects tables outside ALLOWED_TABLES."""

    @pytest.mark.asyncio
    async def test_blocked_table_raises(self):
        import supabase_client as sb
        with pytest.raises(ValueError, match="not in the allowed read list"):
            await sb._fetch("app_secrets")

    @pytest.mark.asyncio
    async def test_allowed_tables_accepted(self):
        """All four allowed tables should not raise a ValueError on the name check."""
        import supabase_client as sb

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(sb, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            for table in ["app_fm_documents", "app_projects", "app_customers", "app_solar_bss"]:
                result = await sb._fetch(table)
                assert result == []


class TestFetchPagination:
    """_fetch enforces a max limit of 500."""

    @pytest.mark.asyncio
    async def test_limit_capped_at_500(self):
        import supabase_client as sb

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(sb, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            await sb._fetch("app_customers", limit=9999)
            call_kwargs = mock_client.get.call_args
            params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1]
            assert params["limit"] == "500"


class TestHelperFunctions:
    """list_* helpers pass correct filters."""

    @pytest.mark.asyncio
    async def test_list_customers_status_filter(self):
        import supabase_client as sb

        mock_response = MagicMock()
        mock_response.json.return_value = [{"id": "1", "status": "active"}]
        mock_response.raise_for_status = MagicMock()

        with patch.object(sb, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await sb.list_customers(status="active")
            assert len(result) == 1
            params = mock_client.get.call_args[1]["params"]
            assert params["status"] == "eq.active"

    @pytest.mark.asyncio
    async def test_list_fm_documents_project_filter(self):
        import supabase_client as sb

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(sb, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            await sb.list_fm_documents(project_id="proj-abc")
            params = mock_client.get.call_args[1]["params"]
            assert params["project_id"] == "eq.proj-abc"

    @pytest.mark.asyncio
    async def test_list_solar_bss_customer_filter(self):
        import supabase_client as sb

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(sb, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            await sb.list_solar_bss(customer_id="cust-xyz")
            params = mock_client.get.call_args[1]["params"]
            assert params["customer_id"] == "eq.cust-xyz"


# ── Router / endpoint tests ───────────────────────────────────────────────────

@pytest.fixture
def client_no_key():
    """TestClient with Supabase anon key intentionally empty."""
    from config import Settings
    import supabase_client as sb

    with patch("config.settings", Settings(supabase_anon_key="")):
        # Patch the check inside routers too
        with patch("routers.supabase_views.settings") as mock_settings:
            mock_settings.supabase_anon_key = ""
            from main import app
            with TestClient(app, raise_server_exceptions=False) as c:
                yield c


@pytest.fixture
def client_with_key():
    """TestClient with a fake Supabase anon key, supabase_client fully mocked."""
    from config import Settings
    import supabase_client as sb

    fake_rows = [{"id": "row1"}, {"id": "row2"}]

    async def mock_list(*args, **kwargs):
        return fake_rows

    with patch.object(sb, "list_customers", side_effect=mock_list), \
         patch.object(sb, "list_projects", side_effect=mock_list), \
         patch.object(sb, "list_fm_documents", side_effect=mock_list), \
         patch.object(sb, "list_solar_bss", side_effect=mock_list):
        with patch("routers.supabase_views.settings") as mock_settings:
            mock_settings.supabase_anon_key = "fake-anon-key"
            from main import app
            with TestClient(app) as c:
                yield c


class TestRouterNotConfigured:
    def test_customers_503_when_no_key(self, client_no_key):
        resp = client_no_key.get("/kama-net/customers")
        assert resp.status_code == 503

    def test_projects_503_when_no_key(self, client_no_key):
        resp = client_no_key.get("/kama-net/projects")
        assert resp.status_code == 503

    def test_solar_bss_503_when_no_key(self, client_no_key):
        resp = client_no_key.get("/kama-net/solar-bss")
        assert resp.status_code == 503

    def test_dashboard_summary_503_when_no_key(self, client_no_key):
        resp = client_no_key.get("/kama-net/dashboard-summary")
        assert resp.status_code == 503


class TestRouterWithKey:
    def test_customers_returns_paginated(self, client_with_key):
        resp = client_with_key.get("/kama-net/customers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_returned"] == 2
        assert len(body["items"]) == 2

    def test_projects_returns_paginated(self, client_with_key):
        resp = client_with_key.get("/kama-net/projects")
        assert resp.status_code == 200
        assert resp.json()["total_returned"] == 2

    def test_solar_bss_returns_paginated(self, client_with_key):
        resp = client_with_key.get("/kama-net/solar-bss")
        assert resp.status_code == 200
        assert resp.json()["total_returned"] == 2

    def test_project_documents_returns_paginated(self, client_with_key):
        resp = client_with_key.get("/kama-net/projects/proj-abc/documents")
        assert resp.status_code == 200
        assert resp.json()["total_returned"] == 2

    def test_customers_offset_propagated(self, client_with_key):
        resp = client_with_key.get("/kama-net/customers?offset=10&limit=5")
        assert resp.status_code == 200
        assert resp.json()["offset"] == 10

    def test_dashboard_summary_returns_counts(self, client_with_key):
        resp = client_with_key.get("/kama-net/dashboard-summary")
        assert resp.status_code == 200
        body = resp.json()
        assert "customer_count" in body
        assert "project_count" in body
        assert "solar_bss_count" in body
        assert "document_count" in body


class TestRouterHTTPErrors:
    def test_502_on_supabase_http_error(self):
        import supabase_client as sb

        async def raise_http(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.text = "Unauthorized"
            raise httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)

        with patch.object(sb, "list_customers", side_effect=raise_http):
            with patch("routers.supabase_views.settings") as mock_settings:
                mock_settings.supabase_anon_key = "fake-key"
                from main import app
                with TestClient(app, raise_server_exceptions=False) as c:
                    resp = c.get("/kama-net/customers")
                    assert resp.status_code == 502

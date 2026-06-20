import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from crypto_news_aggregator.bugops.clients.railway import RailwayClient


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.RAILWAY_API_TOKEN = "test-token-123"
    settings.RAILWAY_PROJECT_ID = "proj-abc123"
    settings.RAILWAY_SERVICE_NAME_FASTAPI = "fastapi"
    settings.RAILWAY_SERVICE_NAME_CELERY_WORKER = "celery-worker"
    settings.RAILWAY_SERVICE_NAME_CELERY_SCHEDULER = "celery-scheduler"
    return settings


@pytest.fixture
def railway_client(mock_settings):
    return RailwayClient(mock_settings)


class TestGraphQL:
    @pytest.mark.asyncio
    async def test_graphql_sends_correct_auth_header(self, railway_client):
        with patch("crypto_news_aggregator.bugops.clients.railway.httpx.AsyncClient") as mock_client_ctx:
            mock_response = AsyncMock()
            mock_response.json.return_value = {"data": {"test": "result"}}
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_ctx.return_value.__aenter__.return_value = mock_client

            await railway_client._graphql("query { test }", {})

            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Bearer test-token-123"
            assert call_kwargs["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_graphql_returns_data_on_success(self, railway_client):
        with patch("crypto_news_aggregator.bugops.clients.railway.httpx.AsyncClient") as mock_client_ctx:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {"project": {"id": "123"}},
            }
            mock_response.raise_for_status.return_value = None
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_ctx.return_value.__aenter__.return_value = mock_client

            result = await railway_client._graphql("query { project }", {})

            assert result == {"project": {"id": "123"}}

    @pytest.mark.asyncio
    async def test_graphql_returns_none_on_http_401(self, railway_client):
        with patch("crypto_news_aggregator.bugops.clients.railway.httpx.AsyncClient") as mock_client_ctx:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401", request=MagicMock(), response=mock_response
            )
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_ctx.return_value.__aenter__.return_value = mock_client

            result = await railway_client._graphql("query { test }", {})

            assert result is None

    @pytest.mark.asyncio
    async def test_graphql_returns_none_on_timeout(self, railway_client):
        with patch("crypto_news_aggregator.bugops.clients.railway.httpx.AsyncClient") as mock_client_ctx:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("Timeout")
            mock_client_ctx.return_value.__aenter__.return_value = mock_client

            result = await railway_client._graphql("query { test }", {})

            assert result is None

    @pytest.mark.asyncio
    async def test_graphql_returns_none_on_json_parse_error(self, railway_client):
        with patch("crypto_news_aggregator.bugops.clients.railway.httpx.AsyncClient") as mock_client_ctx:
            mock_response = AsyncMock()
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_ctx.return_value.__aenter__.return_value = mock_client

            result = await railway_client._graphql("query { test }", {})

            assert result is None

    @pytest.mark.asyncio
    async def test_graphql_returns_none_on_graphql_error(self, railway_client):
        with patch("crypto_news_aggregator.bugops.clients.railway.httpx.AsyncClient") as mock_client_ctx:
            mock_response = AsyncMock()
            mock_response.json.return_value = {
                "errors": [{"message": "Invalid query"}]
            }
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_ctx.return_value.__aenter__.return_value = mock_client

            result = await railway_client._graphql("query { bad }", {})

            assert result is None


class TestGetActiveDeploymentId:
    @pytest.mark.asyncio
    async def test_returns_cached_value_on_second_call(self, railway_client):
        with patch.object(railway_client, "_graphql") as mock_graphql:
            mock_graphql.return_value = {
                "project": {
                    "services": {
                        "edges": [
                            {
                                "node": {
                                    "id": "svc-123",
                                    "name": "fastapi",
                                }
                            }
                        ]
                    }
                },
                "deployments": {
                    "edges": [
                        {
                            "node": {
                                "id": "dep-456",
                                "status": "SUCCESS",
                                "createdAt": "2026-06-20T12:00:00Z",
                                "updatedAt": "2026-06-20T12:05:00Z",
                            }
                        }
                    ]
                },
            }

            result1 = await railway_client.get_active_deployment_id("fastapi")
            result2 = await railway_client.get_active_deployment_id("fastapi")

            assert result1 == "dep-456"
            assert result2 == "dep-456"
            assert mock_graphql.call_count == 2  # First for service lookup, second for deployment lookup

    @pytest.mark.asyncio
    async def test_returns_none_when_service_not_found(self, railway_client):
        with patch.object(railway_client, "_graphql") as mock_graphql:
            mock_graphql.return_value = {
                "project": {
                    "services": {
                        "edges": [
                            {
                                "node": {
                                    "id": "svc-123",
                                    "name": "other-service",
                                }
                            }
                        ]
                    }
                }
            }

            result = await railway_client.get_active_deployment_id("fastapi")

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_api_unavailable(self, railway_client):
        with patch.object(railway_client, "_graphql") as mock_graphql:
            mock_graphql.return_value = None

            result = await railway_client.get_active_deployment_id("fastapi")

            assert result is None

    @pytest.mark.asyncio
    async def test_uses_service_name_map(self, railway_client):
        with patch.object(railway_client, "_graphql") as mock_graphql:
            mock_graphql.return_value = {
                "project": {
                    "services": {
                        "edges": [
                            {
                                "node": {
                                    "id": "svc-123",
                                    "name": "celery-worker",  # Railway name (mapped)
                                }
                            }
                        ]
                    }
                },
                "deployments": {
                    "edges": [
                        {
                            "node": {
                                "id": "dep-456",
                                "status": "SUCCESS",
                                "createdAt": "2026-06-20T12:00:00Z",
                                "updatedAt": "2026-06-20T12:05:00Z",
                            }
                        }
                    ]
                },
            }

            result = await railway_client.get_active_deployment_id("celery_worker")

            assert result == "dep-456"
            # First GraphQL call should use the mapped name
            first_call_query = mock_graphql.call_args_list[0][0][0]
            assert "GetServices" in first_call_query

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_service_name(self, railway_client):
        result = await railway_client.get_active_deployment_id("unknown_service")
        assert result is None


class TestGetRecentDeployments:
    @pytest.mark.asyncio
    async def test_filters_by_since_datetime(self, railway_client):
        since = datetime(2026, 6, 20, 10, 0, 0, tzinfo=timezone.utc)

        with patch.object(railway_client, "_graphql") as mock_graphql:
            mock_graphql.return_value = {
                "project": {
                    "services": {
                        "edges": [
                            {
                                "node": {
                                    "id": "svc-123",
                                    "name": "fastapi",
                                }
                            }
                        ]
                    }
                },
                "deployments": {
                    "edges": [
                        {
                            "node": {
                                "id": "dep-1",
                                "status": "SUCCESS",
                                "createdAt": "2026-06-20T11:00:00Z",
                                "updatedAt": "2026-06-20T11:05:00Z",
                            }
                        },
                        {
                            "node": {
                                "id": "dep-2",
                                "status": "SUCCESS",
                                "createdAt": "2026-06-20T09:00:00Z",  # Before 'since'
                                "updatedAt": "2026-06-20T09:05:00Z",
                            }
                        },
                    ]
                },
            }

            result = await railway_client.get_recent_deployments("fastapi", since)

            assert len(result) == 1
            assert result[0]["deployment_id"] == "dep-1"

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_api_error(self, railway_client):
        since = datetime(2026, 6, 20, 10, 0, 0, tzinfo=timezone.utc)

        with patch.object(railway_client, "_graphql") as mock_graphql:
            mock_graphql.return_value = None

            result = await railway_client.get_recent_deployments("fastapi", since)

            assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_unknown_service(self, railway_client):
        since = datetime(2026, 6, 20, 10, 0, 0, tzinfo=timezone.utc)

        result = await railway_client.get_recent_deployments("unknown_service", since)

        assert result == []

    @pytest.mark.asyncio
    async def test_deployment_response_format(self, railway_client):
        since = datetime(2026, 6, 20, 10, 0, 0, tzinfo=timezone.utc)

        with patch.object(railway_client, "_graphql") as mock_graphql:
            mock_graphql.return_value = {
                "project": {
                    "services": {
                        "edges": [
                            {
                                "node": {
                                    "id": "svc-123",
                                    "name": "fastapi",
                                }
                            }
                        ]
                    }
                },
                "deployments": {
                    "edges": [
                        {
                            "node": {
                                "id": "dep-456",
                                "status": "SUCCESS",
                                "createdAt": "2026-06-20T11:00:00Z",
                                "updatedAt": "2026-06-20T11:05:00Z",
                            }
                        }
                    ]
                },
            }

            result = await railway_client.get_recent_deployments("fastapi", since)

            assert len(result) == 1
            dep = result[0]
            assert dep["deployment_id"] == "dep-456"
            assert dep["status"] == "SUCCESS"
            assert dep["created_at"] == "2026-06-20T11:00:00Z"
            assert dep["updated_at"] == "2026-06-20T11:05:00Z"
            assert dep["service"] == "fastapi"


class TestGetLogs:
    @pytest.mark.asyncio
    async def test_fetches_line_cap_plus_one(self, railway_client):
        with patch.object(
            railway_client, "get_active_deployment_id"
        ) as mock_get_dep_id:
            mock_get_dep_id.return_value = "dep-123"

            with patch.object(railway_client, "_graphql") as mock_graphql:
                mock_graphql.return_value = {
                    "deploymentLogs": [
                        {"message": "log line 1", "severity": "info", "timestamp": "2026-06-20T12:00:00Z"},
                    ]
                }

                start = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
                end = datetime(2026, 6, 20, 13, 0, 0, tzinfo=timezone.utc)
                await railway_client.get_logs("fastapi", start, end, line_cap=100)

                # Verify the limit was set to line_cap + 1
                call_args = mock_graphql.call_args_list[0]
                variables = call_args[0][1]
                assert variables["limit"] == 101

    @pytest.mark.asyncio
    async def test_returns_truncated_true_when_exceeded(self, railway_client):
        with patch.object(
            railway_client, "get_active_deployment_id"
        ) as mock_get_dep_id:
            mock_get_dep_id.return_value = "dep-123"

            with patch.object(railway_client, "_graphql") as mock_graphql:
                # Return exactly line_cap + 1 lines
                logs = [{"message": f"line {i}", "severity": "info", "timestamp": "2026-06-20T12:00:00Z"} for i in range(101)]
                mock_graphql.return_value = {"deploymentLogs": logs}

                start = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
                end = datetime(2026, 6, 20, 13, 0, 0, tzinfo=timezone.utc)
                result, was_truncated = await railway_client.get_logs("fastapi", start, end, line_cap=100)

                assert was_truncated is True
                assert len(result) == 100  # Only first 100

    @pytest.mark.asyncio
    async def test_returns_truncated_false_when_under_cap(self, railway_client):
        with patch.object(
            railway_client, "get_active_deployment_id"
        ) as mock_get_dep_id:
            mock_get_dep_id.return_value = "dep-123"

            with patch.object(railway_client, "_graphql") as mock_graphql:
                logs = [{"message": f"line {i}", "severity": "info", "timestamp": "2026-06-20T12:00:00Z"} for i in range(50)]
                mock_graphql.return_value = {"deploymentLogs": logs}

                start = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
                end = datetime(2026, 6, 20, 13, 0, 0, tzinfo=timezone.utc)
                result, was_truncated = await railway_client.get_logs("fastapi", start, end, line_cap=100)

                assert was_truncated is False
                assert len(result) == 50

    @pytest.mark.asyncio
    async def test_returns_empty_on_api_error(self, railway_client):
        with patch.object(
            railway_client, "get_active_deployment_id"
        ) as mock_get_dep_id:
            mock_get_dep_id.return_value = None

            start = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
            end = datetime(2026, 6, 20, 13, 0, 0, tzinfo=timezone.utc)
            result, was_truncated = await railway_client.get_logs("fastapi", start, end, line_cap=100)

            assert result == []
            assert was_truncated is False

    @pytest.mark.asyncio
    async def test_returns_empty_on_graphql_error(self, railway_client):
        with patch.object(
            railway_client, "get_active_deployment_id"
        ) as mock_get_dep_id:
            mock_get_dep_id.return_value = "dep-123"

            with patch.object(railway_client, "_graphql") as mock_graphql:
                mock_graphql.return_value = None

                start = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
                end = datetime(2026, 6, 20, 13, 0, 0, tzinfo=timezone.utc)
                result, was_truncated = await railway_client.get_logs("fastapi", start, end, line_cap=100)

                assert result == []
                assert was_truncated is False

    @pytest.mark.asyncio
    async def test_extracts_message_field_correctly(self, railway_client):
        with patch.object(
            railway_client, "get_active_deployment_id"
        ) as mock_get_dep_id:
            mock_get_dep_id.return_value = "dep-123"

            with patch.object(railway_client, "_graphql") as mock_graphql:
                mock_graphql.return_value = {
                    "deploymentLogs": [
                        {"message": "error occurred", "severity": "error", "timestamp": "2026-06-20T12:00:00Z"},
                        {"message": "request completed", "severity": "info", "timestamp": "2026-06-20T12:01:00Z"},
                    ]
                }

                start = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
                end = datetime(2026, 6, 20, 13, 0, 0, tzinfo=timezone.utc)
                result, was_truncated = await railway_client.get_logs("fastapi", start, end, line_cap=100)

                assert result == ["error occurred", "request completed"]
                assert was_truncated is False

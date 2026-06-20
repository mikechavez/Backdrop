import httpx
import logging
from datetime import datetime
from typing import Optional
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class RailwayClient:
    """
    Railway GraphQL API client.
    Authenticates via RAILWAY_API_TOKEN.
    Service names resolved to deployment IDs for log and deployment queries.
    """

    GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"

    def __init__(self, settings: BaseSettings):
        self.api_token = settings.RAILWAY_API_TOKEN
        self.project_id = settings.RAILWAY_PROJECT_ID
        self.service_name_map = {
            "fastapi": settings.RAILWAY_SERVICE_NAME_FASTAPI,
            "celery_worker": settings.RAILWAY_SERVICE_NAME_CELERY_WORKER,
            "celery_scheduler": settings.RAILWAY_SERVICE_NAME_CELERY_SCHEDULER,
        }
        self._deployment_id_cache: dict[str, str] = {}

    async def get_active_deployment_id(self, service_name: str) -> Optional[str]:
        """
        Resolve internal service name to active Railway deployment ID.
        Cached per client instance.
        Returns None if service not found or API unavailable.
        """
        if service_name in self._deployment_id_cache:
            return self._deployment_id_cache[service_name]

        railway_service_name = self.service_name_map.get(service_name)
        if not railway_service_name:
            logger.warning(f"Service name '{service_name}' not in mapping")
            return None

        query = """
        query GetServices($projectId: String!) {
          project(id: $projectId) {
            services {
              edges {
                node {
                  id
                  name
                }
              }
            }
          }
        }
        """
        variables = {"projectId": self.project_id}

        result = await self._graphql(query, variables)
        if not result:
            return None

        try:
            services = result.get("project", {}).get("services", {}).get("edges", [])
            service_id = None
            for edge in services:
                node = edge.get("node", {})
                if node.get("name") == railway_service_name:
                    service_id = node.get("id")
                    break

            if not service_id:
                logger.warning(
                    f"Service '{railway_service_name}' not found in Railway project"
                )
                return None

            # Now get active deployment for this service
            deployment_query = """
            query GetActiveDeployment($serviceId: String!) {
              deployments(
                first: 1
                input: { serviceId: $serviceId }
                orderBy: { field: CREATED_AT, direction: DESC }
              ) {
                edges {
                  node {
                    id
                    status
                    createdAt
                    updatedAt
                  }
                }
              }
            }
            """
            deployment_vars = {"serviceId": service_id}
            deployment_result = await self._graphql(deployment_query, deployment_vars)

            if not deployment_result:
                return None

            deployments = (
                deployment_result.get("deployments", {}).get("edges", [])
            )
            if deployments:
                deployment_id = deployments[0].get("node", {}).get("id")
                if deployment_id:
                    self._deployment_id_cache[service_name] = deployment_id
                    return deployment_id

            logger.warning(
                f"No active deployment found for service '{railway_service_name}'"
            )
            return None

        except (KeyError, TypeError, AttributeError) as e:
            logger.error(f"Error parsing Railway service response: {e}")
            return None

    async def get_recent_deployments(
        self,
        service_name: str,
        since: datetime,
    ) -> list[dict]:
        """
        Fetch deployments for a service created at or after `since`.
        Returns list of dicts:
          {"deployment_id": str, "status": str, "created_at": str, "updated_at": str, "service": service_name}
        Returns empty list on API error — caller records as unavailable.
        """
        railway_service_name = self.service_name_map.get(service_name)
        if not railway_service_name:
            logger.warning(f"Service name '{service_name}' not in mapping")
            return []

        # First get the service ID
        query = """
        query GetServices($projectId: String!) {
          project(id: $projectId) {
            services {
              edges {
                node {
                  id
                  name
                }
              }
            }
          }
        }
        """
        variables = {"projectId": self.project_id}

        result = await self._graphql(query, variables)
        if not result:
            return []

        try:
            services = result.get("project", {}).get("services", {}).get("edges", [])
            service_id = None
            for edge in services:
                node = edge.get("node", {})
                if node.get("name") == railway_service_name:
                    service_id = node.get("id")
                    break

            if not service_id:
                return []

            # Now get deployments
            deployment_query = """
            query GetDeployments($serviceId: String!) {
              deployments(
                first: 50
                input: { serviceId: $serviceId }
                orderBy: { field: CREATED_AT, direction: DESC }
              ) {
                edges {
                  node {
                    id
                    status
                    createdAt
                    updatedAt
                  }
                }
              }
            }
            """
            deployment_vars = {"serviceId": service_id}
            deployment_result = await self._graphql(
                deployment_query, deployment_vars
            )

            if not deployment_result:
                return []

            deployments = []
            for edge in deployment_result.get("deployments", {}).get("edges", []):
                node = edge.get("node", {})
                created_at_str = node.get("createdAt", "")
                try:
                    created_at = datetime.fromisoformat(
                        created_at_str.replace("Z", "+00:00")
                    )
                    if created_at >= since:
                        deployments.append(
                            {
                                "deployment_id": node.get("id"),
                                "status": node.get("status"),
                                "created_at": created_at_str,
                                "updated_at": node.get("updatedAt"),
                                "service": service_name,
                            }
                        )
                except (ValueError, AttributeError):
                    continue

            return deployments

        except (KeyError, TypeError, AttributeError) as e:
            logger.error(f"Error parsing Railway deployments response: {e}")
            return []

    async def get_logs(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        line_cap: int,
    ) -> tuple[list[str], bool]:
        """
        Fetch log lines for a service within time window.

        Fetches line_cap + 1 lines from Railway.
        If len(result) > line_cap: truncated=True, store only line_cap lines.
        If len(result) <= line_cap: truncated=False, store all lines.

        Returns (log_lines, was_truncated).
        Returns ([], False) on API error — caller records as unavailable.
        """
        deployment_id = await self.get_active_deployment_id(service_name)
        if not deployment_id:
            return [], False

        query = """
        query GetDeploymentLogs(
          $deploymentId: String!
          $startDate: DateTime
          $endDate: DateTime
          $limit: Int
        ) {
          deploymentLogs(
            deploymentId: $deploymentId
            startDate: $startDate
            endDate: $endDate
            limit: $limit
            filter: ""
          ) {
            timestamp
            message
            severity
          }
        }
        """
        variables = {
            "deploymentId": deployment_id,
            "startDate": start_time.isoformat(),
            "endDate": end_time.isoformat(),
            "limit": line_cap + 1,
        }

        result = await self._graphql(query, variables)
        if not result:
            return [], False

        try:
            logs = result.get("deploymentLogs", [])
            log_lines = [log.get("message", "") for log in logs if log.get("message")]

            was_truncated = len(log_lines) > line_cap
            if was_truncated:
                return log_lines[:line_cap], True
            return log_lines, False

        except (KeyError, TypeError, AttributeError) as e:
            logger.error(f"Error parsing Railway logs response: {e}")
            return [], False

    async def _graphql(self, query: str, variables: dict) -> Optional[dict]:
        """
        Execute a GraphQL query against Railway API.
        Returns parsed response["data"] or None on any error.
        Handles: auth, timeout (10s default), HTTP errors, JSON parse errors.
        Logs errors at error level. Never raises.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()

                # Check for GraphQL errors
                if "errors" in data:
                    logger.error(
                        f"GraphQL error from Railway: {data.get('errors')}"
                    )
                    return None

                return data.get("data")

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Railway API: {e.response.status_code} {e}")
            return None
        except httpx.TimeoutException:
            logger.error("Timeout connecting to Railway API")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error from Railway API: {e}")
            return None
        except ValueError as e:
            logger.error(f"JSON parse error from Railway API: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Railway client: {e}")
            return None

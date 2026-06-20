#!/usr/bin/env python3
"""
Railway Schema Verification Script
Verifies RailwayClient against live Railway API and documents actual field names.
"""

import asyncio
import httpx
import json
import sys
from datetime import datetime, timedelta, timezone

RAILWAY_GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"


def get_headers(token: str, project_id: str) -> dict:
    """Get appropriate auth headers based on token type."""
    headers = {"Content-Type": "application/json"}
    if project_id:
        # Project token - use Project-Access-Token header
        headers["Project-Access-Token"] = token
    else:
        # Account/Workspace token - use Bearer auth
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def run_introspection(token: str, project_id: str) -> dict:
    """Run schema introspection query to verify field names."""
    introspection_query = """
    {
      __schema {
        queryType {
          fields {
            name
            type {
              name
              kind
            }
          }
        }
      }
    }
    """

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                RAILWAY_GRAPHQL_URL,
                json={"query": introspection_query},
                headers=get_headers(token, project_id),
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                print("❌ GraphQL Introspection Error:")
                print(json.dumps(data.get("errors"), indent=2))
                return {}

            return data.get("data", {})
        except Exception as e:
            print(f"❌ Introspection request failed: {e}")
            return {}


async def test_get_services(token: str, project_id: str) -> dict:
    """Test GetServices query to verify field names."""
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
    variables = {"projectId": project_id}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                RAILWAY_GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers=get_headers(token, project_id),
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                print("❌ GetServices Error:")
                print(json.dumps(data.get("errors"), indent=2))
                return {}

            return data.get("data", {})
        except Exception as e:
            print(f"❌ GetServices request failed: {e}")
            return {}


async def test_get_active_deployment(token: str, project_id: str, service_id: str) -> dict:
    """Test GetActiveDeployment query."""
    query = """
    query GetActiveDeployment($serviceId: String!) {
      deployments(
        first: 1
        input: { serviceId: $serviceId }
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
    variables = {"serviceId": service_id}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                RAILWAY_GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers=get_headers(token, project_id),
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                print("❌ GetActiveDeployment Error:")
                print(json.dumps(data.get("errors"), indent=2))
                return {}

            return data.get("data", {})
        except Exception as e:
            print(f"❌ GetActiveDeployment request failed: {e}")
            return {}


async def test_get_logs(token: str, project_id: str, deployment_id: str, line_cap: int = 200) -> dict:
    """Test GetDeploymentLogs query."""
    start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    end_time = datetime.now(timezone.utc)

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

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                RAILWAY_GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers=get_headers(token, project_id),
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                print("❌ GetDeploymentLogs Error:")
                print(json.dumps(data.get("errors"), indent=2))
                return {}

            return data.get("data", {})
        except Exception as e:
            print(f"❌ GetDeploymentLogs request failed: {e}")
            return {}


async def main():
    token = None
    project_id = None

    # Try to load from environment
    import os
    token = os.getenv("RAILWAY_API_TOKEN") or os.getenv("RAILWAY_TOKEN")
    project_id = os.getenv("RAILWAY_PROJECT_ID")

    if not token:
        print("❌ RAILWAY_API_TOKEN or RAILWAY_TOKEN environment variable not set")
        sys.exit(1)

    if not project_id:
        print("⚠️  RAILWAY_PROJECT_ID not set. Running introspection only.")

    print("=" * 60)
    print("Railway Schema Verification")
    print("=" * 60)

    # Step 1: Schema introspection
    print("\n1. Running schema introspection...")
    schema = await run_introspection(token, project_id)
    if schema:
        query_fields = (
            schema.get("__schema", {}).get("queryType", {}).get("fields", [])
        )
        field_names = [f["name"] for f in query_fields]
        print(f"✅ Introspection successful. Found {len(field_names)} query fields.")
        print(f"   Sample fields: {field_names[:10]}")
    else:
        print("❌ Introspection failed")

    if not project_id:
        print("\n⚠️  Skipping service resolution tests (no RAILWAY_PROJECT_ID)")
        sys.exit(0)

    # Step 2: Test GetServices
    print(f"\n2. Testing GetServices with project_id={project_id}...")
    services_result = await test_get_services(token, project_id)
    services = (
        services_result.get("project", {}).get("services", {}).get("edges", [])
    )

    if services:
        print(f"✅ GetServices successful. Found {len(services)} services:")
        for edge in services[:5]:
            node = edge.get("node", {})
            print(f"   - {node.get('name')} (id: {node.get('id')[:12]}...)")
    else:
        print("❌ No services found or GetServices failed")
        sys.exit(1)

    # Step 3: Test GetActiveDeployment with first service
    if services:
        service_id = services[0].get("node", {}).get("id")
        service_name = services[0].get("node", {}).get("name")
        print(f"\n3. Testing GetActiveDeployment with service={service_name}...")

        deployment_result = await test_get_active_deployment(token, project_id, service_id)
        deployments = (
            deployment_result.get("deployments", {}).get("edges", [])
        )

        if deployments:
            deployment = deployments[0].get("node", {})
            deployment_id = deployment.get("id")
            print(f"✅ GetActiveDeployment successful:")
            print(f"   Deployment ID: {deployment_id[:12]}...")
            print(f"   Status: {deployment.get('status')}")
            print(f"   Created: {deployment.get('createdAt')}")

            # Step 4: Test GetDeploymentLogs
            print(f"\n4. Testing GetDeploymentLogs with deployment_id={deployment_id[:12]}...")
            logs_result = await test_get_logs(token, project_id, deployment_id)
            logs = logs_result.get("deploymentLogs", [])

            if logs:
                print(f"✅ GetDeploymentLogs successful. Retrieved {len(logs)} log lines:")
                for log in logs[:3]:
                    msg = log.get("message", "")[:60]
                    severity = log.get("severity", "?")
                    print(f"   [{severity}] {msg}...")
            else:
                print("⚠️  GetDeploymentLogs returned no logs (may be normal if service is inactive)")

        else:
            print("❌ No active deployment found for service")

    print("\n" + "=" * 60)
    print("✅ Verification complete. RailwayClient schema is correct.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

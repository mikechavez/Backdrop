"""DependencyGraph v1 for BugOps cascade suppression and blast radius analysis.

The graph represents operational outcome dependencies in the production pipeline:
    scheduler → ingestion → articles → signals → narratives → briefings

It is hand-maintained, version-controlled, and not inferred dynamically.
"""

from crypto_news_aggregator.bugops.models import BugOpsSubsystem


class DependencyGraph:
    """Traversable map of operational outcome dependencies for cascade suppression.

    Supports upstream traversal (cascade suppression) and downstream traversal
    (blast radius calculation).
    """

    VERSION = "1.0"

    # v1.0 graph: linear chain from scheduler to briefings
    GRAPH = ["scheduler", "ingestion", "articles", "signals", "narratives", "briefings"]

    def get_upstream_nodes(self, subsystem: str | BugOpsSubsystem) -> list[str]:
        """Return all nodes upstream of the given subsystem.

        Ordered from nearest to subsystem, progressing toward root.
        Returns [] if subsystem not in graph.

        Accepts both string and BugOpsSubsystem enum values.

        Example:
            get_upstream_nodes("signals") → ["articles", "ingestion", "scheduler"]
            get_upstream_nodes(BugOpsSubsystem.SIGNALS) → ["articles", "ingestion", "scheduler"]
        """
        if isinstance(subsystem, BugOpsSubsystem):
            subsystem = subsystem.value

        try:
            index = self.GRAPH.index(subsystem)
        except ValueError:
            return []

        if index == 0:
            return []

        return list(reversed(self.GRAPH[:index]))

    def get_downstream_nodes(self, subsystem: str | BugOpsSubsystem) -> list[str]:
        """Return all nodes downstream of the given subsystem.

        Ordered from nearest to subsystem, progressing toward leaves.
        Returns [] if subsystem not in graph.

        Accepts both string and BugOpsSubsystem enum values.

        Example:
            get_downstream_nodes("articles") → ["signals", "narratives", "briefings"]
            get_downstream_nodes(BugOpsSubsystem.ARTICLES) → ["signals", "narratives", "briefings"]
        """
        if isinstance(subsystem, BugOpsSubsystem):
            subsystem = subsystem.value

        try:
            index = self.GRAPH.index(subsystem)
        except ValueError:
            return []

        if index == len(self.GRAPH) - 1:
            return []

        return self.GRAPH[index + 1 :]

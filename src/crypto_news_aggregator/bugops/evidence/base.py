"""Protocol definition for evidence collectors."""

from typing import Protocol
from ..models import BugCase, EvidenceReferenceAllocator
from ..store import BugOpsStore


class EvidenceCollectorBase(Protocol):
    """Protocol for individual evidence collectors.

    Each collector is responsible for collecting one evidence section
    and writing it to the Evidence Pack via store.update_evidence_pack_section().
    """

    collector_name: str

    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        """
        Collect evidence and write section to Evidence Pack.

        Must call store.update_evidence_pack_section() with collected data.
        Use ref_allocator.next_ref() to get globally unique evidence reference IDs.
        Must NOT raise — catch exceptions internally and record in collection_errors.

        Args:
            bugcase: The BugCase being investigated
            pack_id: The Evidence Pack ID to write to
            store: BugOpsStore instance for persisting evidence
            ref_allocator: EvidenceReferenceAllocator for collision-free reference IDs
        """
        ...

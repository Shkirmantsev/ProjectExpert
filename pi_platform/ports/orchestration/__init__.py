"""Phase 5 orchestration ports for the v0.8 Project Intelligence
Platform.

Covers architecture sections §34 (Query Orchestrator), §35
(Small Local LLM), §47 (Capability Discovery), §52 (Task
Context Bundles) and the §33 retrieval-first escalation
policy the orchestrator encodes.

The Phase 5 orchestration ports compose the Phase 4 retrieval
subsystem (:mod:`pi_platform.ports.retrieval`) and feed the
Phase 6 MCP server.
"""

from __future__ import annotations

from pi_platform.ports.orchestration.capability_discovery import (
    CapabilityDescriptor,
    CapabilityDiscoveryPort,
    CapabilityDiscoveryError,
    CapabilityFeatures,
)
from pi_platform.ports.orchestration.local_llm import (
    LocalLLMPort,
    LocalLLMError,
)
from pi_platform.ports.orchestration.query_orchestrator import (
    OrchestrationLevel,
    OrchestrationResult,
    QueryOrchestratorError,
    QueryOrchestratorPort,
)
from pi_platform.ports.orchestration.task_context import (
    TaskContextBuilderPort,
    TaskContextBuilderError,
    TaskContextBundle,
)


__all__ = [
    "CapabilityDescriptor",
    "CapabilityDiscoveryError",
    "CapabilityDiscoveryPort",
    "CapabilityFeatures",
    "LocalLLMError",
    "LocalLLMPort",
    "OrchestrationLevel",
    "OrchestrationResult",
    "QueryOrchestratorError",
    "QueryOrchestratorPort",
    "TaskContextBuilderError",
    "TaskContextBuilderPort",
    "TaskContextBundle",
]
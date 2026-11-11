"""Fixed query corpus shared by launcher and UI backend comparisons."""
BENCHMARK_TEXTS = (
    "warehouse pallet packing process for the genesys line",
    "TCP retry implementation in the order service",
    "how does the refund approval workflow work",
    "database migration script for the billing schema",
    "kubernetes deployment of the packaging service",
    "HTTP client timeouts and circuit breaker configuration",
)


# This small fixed query workload must never stand in for repository document
# indexing. Version and prompt participate in the evidence compatibility key.
QUERY_WORKLOAD_VERSION = "prompted-query-corpus/v1"


def query_workload_identity():
    import hashlib
    import json
    return hashlib.sha256(json.dumps({
        "version": QUERY_WORKLOAD_VERSION,
        "texts": BENCHMARK_TEXTS,
        "prompt": "task: search result | query: ",
        "batch_size": 1,
    }, sort_keys=True).encode()).hexdigest()

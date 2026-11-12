"""Resource entitlement arithmetic and a shared bounded CPU token pool."""
from contextlib import contextmanager
import math
import threading


def effective_cpu_capacity(*limits):
    positive = [float(value) for value in limits if value is not None and value > 0]
    return min(positive) if positive else 1.0


def cpu_worker_budget(capacity, *, target_percent=80, requested=None,
                      memory_budget=None, worker_peak=None, inner_threads=1):
    if not 0 < target_percent <= 100 or inner_threads < 1:
        raise ValueError("invalid CPU target or inner thread count")
    budget = max(1, math.floor(capacity * target_percent / 100))
    workers = budget // inner_threads
    if requested is not None:
        if int(requested) < 1:
            raise ValueError("worker count must be positive")
        workers = min(workers, int(requested))
    if memory_budget is not None and worker_peak is not None:
        if worker_peak <= 0 or memory_budget < worker_peak:
            return 0
        workers = min(workers, int(memory_budget // worker_peak))
    return workers


class ResourceTokenPool:
    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("token capacity must be positive")
        self.capacity = int(capacity)
        self._available = self.capacity
        self._condition = threading.Condition()

    @contextmanager
    def acquire(self, cost=1):
        if not 1 <= cost <= self.capacity:
            raise ValueError("resource cost exceeds scheduling envelope")
        with self._condition:
            self._condition.wait_for(lambda: self._available >= cost)
            self._available -= cost
        try:
            yield
        finally:
            with self._condition:
                self._available += cost
                self._condition.notify_all()

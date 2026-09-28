"""EF5 job concurrency (dependency free, so it is testable without the
pipeline's download stack).

Precedence: EF5_MAX_WORKERS environment variable > config ``ef5_max_workers``
> CPUs this process may use.
"""

import os


def _usable_cpus() -> int:
    """CPUs this process may actually use (container aware).

    os.cpu_count() reports the host, not a container's CPU limit, so a
    small task on a big host would start far too many EF5 jobs. Take the
    smallest of the host count, the scheduler affinity mask, and the cgroup
    v2 CPU quota when one is set.
    """
    n = os.cpu_count() or 4
    try:
        n = min(n, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        pass
    try:
        with open("/sys/fs/cgroup/cpu.max") as fh:
            quota, period = fh.read().split()[:2]
        if quota != "max":
            n = min(n, max(1, int(int(quota) // int(period))))
    except (OSError, ValueError):
        pass
    return max(1, n)


def _ef5_phase_workers(n_jobs: int, config=None) -> int:
    """Cap concurrent EF5 jobs (1 = fully sequential).

    Precedence: EF5_MAX_WORKERS environment variable (set per deployment,
    e.g. per AWS task size) > config ``ef5_max_workers`` > usable CPUs.
    Each EF5 job holds its grids in memory, so the CPU fallback can run a
    small host out of memory: keep an explicit value in the config.
    """
    n_jobs = max(1, int(n_jobs or 1))
    for raw in (
        os.environ.get("EF5_MAX_WORKERS", "").strip(),
        getattr(config, "ef5_max_workers", None) if config is not None else None,
    ):
        if raw is None or raw == "":
            continue
        try:
            w = int(raw)
        except (TypeError, ValueError):
            continue
        if w > 0:
            return max(1, min(n_jobs, w))
    return min(n_jobs, _usable_cpus())

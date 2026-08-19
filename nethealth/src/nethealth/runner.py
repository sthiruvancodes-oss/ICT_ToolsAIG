from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import perf_counter

from nethealth.models import RunSummary, SuiteConfig
from nethealth.probes import run_probe


def run_suite(config: SuiteConfig, jobs: int = 8) -> RunSummary:
    started_at = datetime.now(timezone.utc)
    t0 = perf_counter()
    workers = max(1, jobs)
    if workers == 1 or len(config.checks) <= 1:
        results = tuple(
            run_probe(spec, config.timeout_seconds, config.warn_tls_days)
            for spec in config.checks
        )
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(config.checks))) as pool:
            futures = [
                pool.submit(run_probe, spec, config.timeout_seconds, config.warn_tls_days)
                for spec in config.checks
            ]
            results = tuple(future.result() for future in futures)
    return RunSummary(
        name=config.name,
        started_at=started_at,
        duration_ms=(perf_counter() - t0) * 1000,
        results=results,
    )

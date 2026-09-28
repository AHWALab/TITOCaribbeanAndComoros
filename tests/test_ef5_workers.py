"""EF5 concurrency: EF5_MAX_WORKERS env > config ef5_max_workers > usable CPUs."""

from types import SimpleNamespace

from tito_utils.ef5.jobs import workers
from tito_utils.ef5.jobs.workers import _ef5_phase_workers


def test_env_overrides_config(monkeypatch):
    monkeypatch.setenv("EF5_MAX_WORKERS", "3")
    assert _ef5_phase_workers(50, SimpleNamespace(ef5_max_workers=12)) == 3


def test_config_used_without_env(monkeypatch):
    monkeypatch.delenv("EF5_MAX_WORKERS", raising=False)
    assert _ef5_phase_workers(50, SimpleNamespace(ef5_max_workers=12)) == 12


def test_never_more_workers_than_jobs(monkeypatch):
    monkeypatch.setenv("EF5_MAX_WORKERS", "64")
    assert _ef5_phase_workers(5, None) == 5


def test_bad_or_empty_values_fall_through(monkeypatch):
    monkeypatch.setenv("EF5_MAX_WORKERS", "  ")
    assert _ef5_phase_workers(50, SimpleNamespace(ef5_max_workers=2)) == 2
    monkeypatch.setenv("EF5_MAX_WORKERS", "abc")
    assert _ef5_phase_workers(50, SimpleNamespace(ef5_max_workers=2)) == 2
    monkeypatch.setenv("EF5_MAX_WORKERS", "0")
    assert _ef5_phase_workers(50, SimpleNamespace(ef5_max_workers=2)) == 2


def test_none_falls_back_to_usable_cpus(monkeypatch):
    monkeypatch.delenv("EF5_MAX_WORKERS", raising=False)
    monkeypatch.setattr(workers, "_usable_cpus", lambda: 6)
    assert _ef5_phase_workers(50, SimpleNamespace(ef5_max_workers=None)) == 6
    assert _ef5_phase_workers(4, SimpleNamespace(ef5_max_workers=None)) == 4

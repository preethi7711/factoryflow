from collections.abc import Iterator

import pytest

from app.core.db import SessionLocal
from tests.invariants import ledger_problems


@pytest.fixture(autouse=True)
def _ledger_stays_healthy() -> Iterator[None]:
    """After every integration test, the committed ledger must still pass reconcile and have
    no orphans. Tests that corrupt it on purpose do so in a rolled-back session."""
    yield
    with SessionLocal() as session:
        assert ledger_problems(session) == []

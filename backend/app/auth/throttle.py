"""Progressive failed-login delay.

In-memory and process-local; fine for single-admin deployments.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class _State:
    failures: int = 0
    last_failure_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# Single admin user, but key by remote address for safety.
_states: dict[str, _State] = {}


def _delay_for(failures: int) -> float:
    # 1–2 no delay; 3–5: 5s; 6–9: 30s; 10+: 5min
    if failures < 3:
        return 0.0
    if failures < 6:
        return 5.0
    if failures < 10:
        return 30.0
    return 300.0


async def await_delay(key: str) -> None:
    state = _states.get(key)
    if state is None:
        return
    delay = _delay_for(state.failures)
    if delay <= 0:
        return
    elapsed = time.monotonic() - state.last_failure_at
    remaining = delay - elapsed
    if remaining > 0:
        await asyncio.sleep(remaining)


def record_failure(key: str) -> None:
    state = _states.setdefault(key, _State())
    state.failures += 1
    state.last_failure_at = time.monotonic()


def reset(key: str) -> None:
    _states.pop(key, None)


def reset_all() -> None:
    _states.clear()

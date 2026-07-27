from __future__ import annotations

import math

from sqlalchemy import select

from agents.constants import ALL_AGENTS
from database import async_session
from models.novel import TokenUsage
from services.novel_constants import DEFAULT_WATCHDOG_TIMEOUT_SECONDS, MIN_WATCHDOG_P95_SECONDS


async def compute_watchdog_p95() -> dict[str, float]:
    async with async_session() as db:
        result = await db.execute(select(TokenUsage.agent_name, TokenUsage.duration))
        usages = result.all()

    by_agent: dict[str, list[float]] = {}
    for agent_name, duration in usages:
        if agent_name is None:
            continue
        by_agent.setdefault(agent_name, []).append(duration or 0.0)

    p95_by_agent = {
        agent_name: compute_p95_seconds(durations)
        for agent_name, durations in by_agent.items()
    }

    for default_agent in ALL_AGENTS:
        p95_by_agent.setdefault(default_agent, float(DEFAULT_WATCHDOG_TIMEOUT_SECONDS))

    return p95_by_agent


def compute_p95_seconds(durations: list[float]) -> float:
    if not durations:
        return float(DEFAULT_WATCHDOG_TIMEOUT_SECONDS)

    durations_sorted = sorted(durations)
    position = (len(durations_sorted) - 1) * 0.95
    floor_index = math.floor(position)
    ceiling_index = math.ceil(position)
    if floor_index == ceiling_index:
        p95 = durations_sorted[int(position)]
    else:
        p95 = (
            durations_sorted[int(floor_index)] * (ceiling_index - position)
            + durations_sorted[int(ceiling_index)] * (position - floor_index)
        )
    return max(MIN_WATCHDOG_P95_SECONDS, round(p95, 2))

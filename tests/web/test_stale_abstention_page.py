"""A stale-signal abstention, as the agent actually records it, reads as abstained."""
from __future__ import annotations

from tests.agent.test_stale_abstain import _ctx

from fantasy_gm.agent.graph import LineupGraphAgent


def test_sigstale06_the_history_shows_the_stale_abstention_and_why(client, store, tmp_path):
    record = LineupGraphAgent(checkpoint_path=tmp_path / "g.db").precheck(
        _ctx(projections_available=False))
    store.save(record)

    history = client.get("/history").text
    page = client.get(f"/decisions/{record.id}").text

    # SIGSTALE-06 THEN it reads as abstained
    assert ">abstained</span>" in history
    assert ">truncated</span>" not in history
    # SIGSTALE-06 AND the memo names the stale signal
    assert "projections: missing" in page

"""Local web dashboard for Fantasy GM.

A control surface over the existing CLI commands: see the team and the league,
start an agent run and watch it work, then approve and execute a lineup.

Per D-017 this layer contains **no analytics**. Every number on the page comes
from `core/`, `adapters/`, `agent/`, `execute/`, or `db/`; `web/` only presents
and orchestrates them.
"""
from fantasy_gm.web.app import create_app

__all__ = ["create_app"]

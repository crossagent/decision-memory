import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from .memorize import (
    save_control_note,
    save_learning_note,
    save_model_note,
    save_perception_note,
    save_simulation_note,
)
from .recall import (
    get_backlinks,
    get_linked_chain,
    read_agent_memory_note,
    search_agent_memory_notes,
)


mcp = FastMCP("InvestmentAgentMemoryServer")


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
def save_model(
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "draft",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write stable world models, self constraints, priors, or learned rules.

    The model module is the root of the external memory system: it stores
    durable beliefs about the world, personal constraints, risk limits, and
    prediction rules that have survived learning.
    """
    path = save_model_note(kind, title, body, tags, links, status, properties)
    return dumps({"path": path, "module": "model"})


@mcp.tool()
def save_simulation(
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "pending_validation",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write predictions, hypotheses, probability work, scenarios, or backtests.

    Simulation stores forward-looking memory: predictions, scenarios, and
    internal trial runs before commitment.
    """
    path = save_simulation_note(kind, title, body, tags, links, status, properties)
    return dumps({"path": path, "module": "simulation"})


@mcp.tool()
def save_control(
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "active",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write action governance: plans, policies, decisions, executions, or non-actions.

    Control stores action governance: choosing, suppressing, waiting,
    executing, or stopping under model constraints.
    """
    path = save_control_note(kind, title, body, tags, links, status, properties)
    return dumps({"path": path, "module": "control"})


@mcp.tool()
def save_perception(
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "observed",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write external facts, market data, filings, transcripts, and realized outcomes.

    Perception is for sensor agents. It records what happened without final
    attribution or trade authorization.
    """
    path = save_perception_note(kind, title, body, tags, links, status, properties)
    return dumps({"path": path, "module": "perception"})


@mcp.tool()
def save_learning(
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "reviewed",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write validation, scoring, attribution, calibration, and lessons.

    Learning compares simulation/control with perception, then decides whether
    the model should change.
    """
    path = save_learning_note(kind, title, body, tags, links, status, properties)
    return dumps({"path": path, "module": "learning"})


@mcp.tool()
def read_note(note_ref: str) -> str:
    """Read an agent-memory note by path, title, filename stem, or Obsidian wiki-link."""
    return dumps(read_agent_memory_note(note_ref))


@mcp.tool()
def search_notes(
    query: str | None = None,
    module: str | None = None,
    tags: list[str] | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> str:
    """Search agent-memory using text plus Obsidian-style metadata filters."""
    return dumps(search_agent_memory_notes(query, module, tags, kind, status, limit))


@mcp.tool()
def backlinks(note_ref: str) -> str:
    """Return notes that link to the given agent-memory note."""
    return dumps(get_backlinks(note_ref))


@mcp.tool()
def linked_chain(note_ref: str, depth: int = 3) -> str:
    """Walk forward Obsidian wiki-links from a note and return a chain graph."""
    return dumps(get_linked_chain(note_ref, depth))


if __name__ == "__main__":
    mcp.run()

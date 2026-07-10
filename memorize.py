import os
import uuid
from datetime import datetime
from typing import Any

from .common import (
    AGENT_MEMORY_ROOT,
    format_front_matter,
    normalize_links,
    normalize_module,
    normalize_tags,
    parse_front_matter,
    resolve_path,
    sanitize_filename,
    sanitize_tag,
)


def write_vault_file(relative_path: str, metadata: dict[str, Any], body: str) -> str:
    """Compile front matter and write to disk."""
    full_path = resolve_path(relative_path)
    today = datetime.now().strftime("%Y-%m-%d")
    existing_metadata: dict[str, Any] = {}
    if os.path.isfile(full_path):
        with open(full_path, encoding="utf-8") as file:
            existing_metadata, _ = parse_front_matter(file.read())
    metadata.setdefault("id", existing_metadata.get("id") or f"mem-{uuid.uuid4().hex}")
    metadata.setdefault("created", existing_metadata.get("created") or today)
    metadata["updated"] = today
    formatted_content = format_front_matter(metadata, body)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as file:
        file.write(formatted_content)
    return relative_path.replace("\\", "/")


def append_links_section(body: str, links: list[str]) -> str:
    if not links:
        return body
    lines = [body.rstrip(), "", "## 认知链路"]
    lines.extend(f"- {link}" for link in links)
    return "\n".join(lines) + "\n"


def save_agent_memory_note(
    module: str,
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "draft",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write one note into the strict five-module agent-memory vault (Encoding & Storing)."""
    module = normalize_module(module)
    kind = sanitize_tag(kind or "note")
    title = title.strip() or "untitled"
    links = normalize_links(links)

    metadata = dict(properties or {})
    metadata["module"] = module
    metadata["kind"] = kind
    metadata["status"] = status
    metadata["title"] = title
    metadata["tags"] = normalize_tags(
        [f"agent-memory/{module}", f"{module}/{kind}", *(tags or [])]
    )
    if links:
        metadata["links"] = links

    filename = (
        f"{AGENT_MEMORY_ROOT}/{module}/"
        f"{sanitize_filename(kind.replace('/', '-'))}_{sanitize_filename(title)}.md"
    )
    return write_vault_file(filename, metadata, append_links_section(body, links))


def save_model_note(
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "draft",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write stable world models, self constraints, priors, or learned rules."""
    return save_agent_memory_note(
        "model", kind, title, body, tags, links, status, properties
    )


def save_simulation_note(
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "pending_validation",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write predictions, hypotheses, probability work, scenarios, or backtests."""
    return save_agent_memory_note(
        "simulation", kind, title, body, tags, links, status, properties
    )


def save_control_note(
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "active",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write action governance: plans, policies, decisions, executions, or non-actions."""
    return save_agent_memory_note(
        "control", kind, title, body, tags, links, status, properties
    )


def save_perception_note(
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "observed",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write external facts, market data, filings, transcripts, and realized outcomes."""
    return save_agent_memory_note(
        "perception", kind, title, body, tags, links, status, properties
    )


def save_learning_note(
    kind: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    status: str = "reviewed",
    properties: dict[str, Any] | None = None,
) -> str:
    """Write validation, scoring, attribution, calibration, and lessons."""
    return save_agent_memory_note(
        "learning", kind, title, body, tags, links, status, properties
    )

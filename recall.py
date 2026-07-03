import os
from collections import deque
from typing import Any

from .common import (
    AGENT_MEMORY_MODULES,
    AGENT_MEMORY_ROOT,
    BASE_DIR,
    WIKI_LINK_RE,
    normalize_module,
    normalize_tags,
    parse_front_matter,
    resolve_agent_memory_path,
    resolve_path,
    sanitize_tag,
)


def agent_memory_note_paths(module: str | None = None) -> list[str]:
    """Return all Markdown notes under the agent-memory vault."""
    if module is not None:
        roots = [resolve_path(f"{AGENT_MEMORY_ROOT}/{normalize_module(module)}")]
    else:
        roots = [
            resolve_path(f"{AGENT_MEMORY_ROOT}/{item}")
            for item in AGENT_MEMORY_MODULES
        ]

    paths: list[str] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if filename.lower().endswith(".md"):
                    full_path = os.path.join(dirpath, filename)
                    paths.append(os.path.relpath(full_path, BASE_DIR).replace("\\", "/"))
    return sorted(paths)


def extract_links(metadata: dict[str, Any], body: str) -> list[str]:
    """Extract Obsidian wiki-link targets from front matter and Markdown body."""
    links: list[str] = []
    for link in metadata.get("links", []) or []:
        target = str(link)
        if target.startswith("[[") and target.endswith("]]"):
            target = target[2:-2]
        target = target.split("|", 1)[0].split("#", 1)[0].strip()
        if target and target not in links:
            links.append(target)
    for match in WIKI_LINK_RE.findall(body):
        target = match.split("|", 1)[0].split("#", 1)[0].strip()
        if target and target not in links:
            links.append(target)
    return links


def load_note(path: str) -> dict[str, Any]:
    """Load an agent-memory note by relative path."""
    full_path = resolve_agent_memory_path(path)
    with open(full_path, encoding="utf-8") as file:
        content = file.read()
    metadata, body = parse_front_matter(content)
    rel_path = os.path.relpath(full_path, BASE_DIR).replace("\\", "/")
    return {
        "path": rel_path,
        "title": metadata.get("title") or os.path.splitext(os.path.basename(rel_path))[0],
        "module": metadata.get("module"),
        "kind": metadata.get("kind"),
        "status": metadata.get("status"),
        "tags": metadata.get("tags", []),
        "links": extract_links(metadata, body),
        "metadata": metadata,
        "body": body.strip(),
    }


def note_keys(path: str, metadata: dict[str, Any] | None = None) -> set[str]:
    """Return identifiers that can resolve to this note."""
    normalized = path.replace("\\", "/")
    without_ext = normalized[:-3] if normalized.lower().endswith(".md") else normalized
    keys = {
        normalized.lower(),
        without_ext.lower(),
        os.path.basename(without_ext).lower(),
    }
    if metadata:
        title = str(metadata.get("title") or "").strip().lower()
        if title:
            keys.add(title)
    return keys


def resolve_note_ref(note_ref: str) -> str:
    """Resolve a path, filename stem, title, or wiki-link target to an agent-memory note path."""
    target = note_ref.strip()
    if target.startswith("[[") and target.endswith("]]"):
        target = target[2:-2].split("|", 1)[0].split("#", 1)[0]
    target = target.replace("\\", "/").strip("/")
    if not target:
        raise FileNotFoundError("Empty note reference")

    direct_candidates = [target]
    if not target.startswith(f"{AGENT_MEMORY_ROOT}/"):
        direct_candidates.append(f"{AGENT_MEMORY_ROOT}/{target}")
    for candidate in direct_candidates:
        if not candidate.lower().endswith(".md"):
            candidate = f"{candidate}.md"
        full_path = resolve_path(candidate)
        if os.path.isfile(full_path):
            return os.path.relpath(full_path, BASE_DIR).replace("\\", "/")

    lowered = target.lower()
    for path in agent_memory_note_paths():
        full_path = resolve_path(path)
        with open(full_path, encoding="utf-8") as file:
            metadata, _ = parse_front_matter(file.read())
        if lowered in note_keys(path, metadata):
            return path

    raise FileNotFoundError(f"Agent-memory note not found: {note_ref}")


def read_agent_memory_note(note_ref: str) -> dict[str, Any]:
    """Read an agent-memory note by any identifier."""
    return load_note(resolve_note_ref(note_ref))


def search_agent_memory_notes(
    query: str | None = None,
    module: str | None = None,
    tags: list[str] | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search notes by text and metadata filters (Recalling & Awaking)."""
    required_tags = set(normalize_tags(tags))
    query_text = (query or "").lower().strip()
    kind_filter = sanitize_tag(kind) if kind else None
    status_filter = status.lower().strip() if status else None

    results: list[dict[str, Any]] = []
    for path in agent_memory_note_paths(module):
        note = load_note(path)
        note_tags = set(normalize_tags(note["tags"]))
        if required_tags and not required_tags.issubset(note_tags):
            continue
        if kind_filter and sanitize_tag(str(note["kind"])) != kind_filter:
            continue
        if status_filter and str(note["status"]).lower() != status_filter:
            continue
        haystack = "\n".join(
            [
                note["path"],
                str(note["title"]),
                str(note["kind"]),
                " ".join(note["tags"]),
                note["body"],
            ]
        ).lower()
        if query_text and query_text not in haystack:
            continue
        results.append(
            {
                "path": note["path"],
                "title": note["title"],
                "module": note["module"],
                "kind": note["kind"],
                "status": note["status"],
                "tags": note["tags"],
                "links": note["links"],
            }
        )
        if len(results) >= max(1, limit):
            break
    return results


def get_backlinks(note_ref: str) -> list[dict[str, Any]]:
    """Return notes that link to the target note."""
    target_path = resolve_note_ref(note_ref)
    target_note = load_note(target_path)
    target_keys = note_keys(target_path, target_note["metadata"])
    backlinks: list[dict[str, Any]] = []

    for path in agent_memory_note_paths():
        if path == target_path:
            continue
        note = load_note(path)
        linked = False
        for link in note["links"]:
            try:
                linked_path = resolve_note_ref(link)
                linked_note = load_note(linked_path)
                linked = bool(note_keys(linked_path, linked_note["metadata"]) & target_keys)
            except FileNotFoundError:
                linked = link.strip().lower() in target_keys
            if linked:
                backlinks.append(
                    {
                        "path": note["path"],
                        "title": note["title"],
                        "module": note["module"],
                        "kind": note["kind"],
                        "status": note["status"],
                        "tags": note["tags"],
                    }
                )
                break
    return backlinks


def get_linked_chain(note_ref: str, depth: int = 3) -> dict[str, Any]:
    """Walk forward wiki-links from a note and return a local graph."""
    root = resolve_note_ref(note_ref)
    max_depth = max(0, min(depth, 5))
    queue: deque[tuple[str, int]] = deque([(root, 0)])
    seen: set[str] = set()
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []

    while queue:
        path, current_depth = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        note = load_note(path)
        nodes[path] = {
            "path": note["path"],
            "title": note["title"],
            "module": note["module"],
            "kind": note["kind"],
            "status": note["status"],
            "tags": note["tags"],
        }
        if current_depth >= max_depth:
            continue
        for link in note["links"]:
            try:
                linked_path = resolve_note_ref(link)
            except FileNotFoundError:
                continue
            edges.append({"from": path, "to": linked_path, "relation": "links_to"})
            if linked_path not in seen:
                queue.append((linked_path, current_depth + 1))

    return {"root": root, "nodes": list(nodes.values()), "edges": edges}

import os
import re
from collections import deque
from datetime import datetime
from typing import Any

from .policy import validate_safe_write


BASE_DIR = os.path.abspath(os.environ.get("MEMORY_VAULT_PATH", os.path.join(os.path.dirname(__file__), "..")))
AGENT_MEMORY_ROOT = "agent-memory"
AGENT_MEMORY_MODULES = ("model", "simulation", "control", "perception", "learning")
WIKI_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")


def resolve_path(relative_path: str) -> str:
    """Safely resolve a path inside the investment workspace."""
    resolved = os.path.abspath(os.path.join(BASE_DIR, relative_path))
    if os.path.commonpath([BASE_DIR, resolved]) != BASE_DIR:
        raise PermissionError(
            f"Access Denied: Attempted to escape workspace root: {relative_path}"
        )
    return resolved


def resolve_agent_memory_path(relative_path: str) -> str:
    """Resolve a path that must live under the agent-memory vault root."""
    normalized = relative_path.replace("\\", "/").lstrip("/")
    if not normalized.startswith(f"{AGENT_MEMORY_ROOT}/"):
        normalized = f"{AGENT_MEMORY_ROOT}/{normalized}"
    resolved = resolve_path(normalized)
    agent_memory_root = resolve_path(AGENT_MEMORY_ROOT)
    if os.path.commonpath([agent_memory_root, resolved]) != agent_memory_root:
        raise PermissionError(
            f"Access Denied: Attempted to escape agent-memory root: {relative_path}"
        )
    return resolved


def parse_front_matter(content: str) -> tuple[dict[str, Any], str]:
    """Parse a small Obsidian YAML front matter subset."""
    content = content.removeprefix("\ufeff")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        return {}, content

    yaml_text, body = match.groups()
    metadata: dict[str, Any] = {}
    current_list_key: str | None = None

    for raw_line in yaml_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("-") and current_list_key:
            item = line[1:].strip().strip('"').strip("'")
            metadata.setdefault(current_list_key, []).append(item)
            continue

        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val == "":
                current_list_key = key
                metadata[key] = []
            else:
                current_list_key = None
                if val.lower() == "true":
                    metadata[key] = True
                elif val.lower() == "false":
                    metadata[key] = False
                else:
                    metadata[key] = val

    return metadata, body


def format_front_matter(metadata: dict[str, Any], body: str) -> str:
    """Format metadata and Markdown body as an Obsidian note."""
    yaml_lines = ["---"]
    for key, val in metadata.items():
        if isinstance(val, list):
            yaml_lines.append(f"{key}:")
            for item in val:
                escaped = str(item).replace('"', '\\"')
                yaml_lines.append(f'  - "{escaped}"')
        elif isinstance(val, bool):
            yaml_lines.append(f"{key}: {str(val).lower()}")
        else:
            text = str(val).replace('"', '\\"')
            yaml_lines.append(f'{key}: "{text}"')
    yaml_lines.append("---")
    return "\n".join(yaml_lines) + "\n\n" + body.lstrip()


def sanitize_filename(value: str) -> str:
    """Return a Windows-safe readable Markdown filename stem."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("._ ")
    return cleaned or "untitled"


def sanitize_tag(value: str) -> str:
    """Return an Obsidian-friendly tag without a leading #."""
    cleaned = str(value).strip().replace("\\", "/")
    cleaned = re.sub(r"^#+", "", cleaned)
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = re.sub(r"[^0-9A-Za-z_\-/\u4e00-\u9fff]+", "-", cleaned)
    cleaned = re.sub(r"/+", "/", cleaned).strip("/-").lower()
    return cleaned


def normalize_tags(tags: list[str] | None) -> list[str]:
    """Normalize tags while preserving first-seen order."""
    normalized: list[str] = []
    for tag in tags or []:
        cleaned = sanitize_tag(tag)
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def normalize_links(links: list[str] | None) -> list[str]:
    """Normalize link targets into Obsidian wiki-link strings."""
    normalized: list[str] = []
    for raw in links or []:
        link = str(raw).strip()
        if not link:
            continue
        if not (link.startswith("[[") and link.endswith("]]")):
            target = link
        else:
            target = link[2:-2]
        target = target.replace("\\", "/").strip("/")
        if target.startswith(f"{AGENT_MEMORY_ROOT}/"):
            target = target[len(AGENT_MEMORY_ROOT) + 1 :]
        link = f"[[{target}]]"
        if link not in normalized:
            normalized.append(link)
    return normalized


def normalize_module(module: str) -> str:
    module = module.strip().lower()
    if module not in AGENT_MEMORY_MODULES:
        raise ValueError(
            f"Invalid agent-memory module: {module}. "
            f"Must be one of {AGENT_MEMORY_MODULES}"
        )
    return module


def write_vault_file(relative_path: str, metadata: dict[str, Any], body: str) -> str:
    """Compile front matter, validate safety, and write to disk."""
    full_path = resolve_path(relative_path)
    today = datetime.now().strftime("%Y-%m-%d")
    metadata.setdefault("created", today)
    metadata["updated"] = today
    formatted_content = format_front_matter(metadata, body)
    validate_safe_write(full_path, formatted_content)
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
    """Write one note into the strict five-module agent-memory vault."""
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
    return save_agent_memory_note(
        "learning", kind, title, body, tags, links, status, properties
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


def read_agent_memory_note(note_ref: str) -> dict[str, Any]:
    """Read an agent-memory note and return parsed metadata, tags, links, and body."""
    return load_note(resolve_note_ref(note_ref))


def search_agent_memory_notes(
    query: str | None = None,
    module: str | None = None,
    tags: list[str] | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search notes by text plus Obsidian-style metadata filters."""
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
    """Walk forward wiki-links from a note and return a small graph."""
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

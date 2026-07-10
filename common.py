import os
import re
import uuid
from typing import Any

BASE_DIR = os.path.abspath(
    os.environ.get("MEMORY_VAULT_PATH", os.path.join(os.path.dirname(__file__), ".."))
)
AGENT_MEMORY_ROOT = "agent-memory"
AGENT_MEMORY_MODULES = ("model", "simulation", "control", "perception", "learning")
WIKI_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
LEGACY_NOTE_NAMESPACE = uuid.UUID("4dd0ce1b-c672-47ae-8746-49fd98555781")


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


def note_id_for(path: str, metadata: dict[str, Any] | None = None) -> str:
    """Return a durable note ID, with a deterministic fallback for legacy notes."""
    explicit_id = str((metadata or {}).get("id") or "").strip()
    if explicit_id:
        return explicit_id
    normalized_path = path.replace("\\", "/").strip("/").lower()
    return f"legacy-{uuid.uuid5(LEGACY_NOTE_NAMESPACE, normalized_path).hex}"

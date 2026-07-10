import hashlib
import json
import math
import os
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .common import (
    AGENT_MEMORY_MODULES,
    AGENT_MEMORY_ROOT,
    BASE_DIR,
    WIKI_LINK_RE,
    normalize_module,
    normalize_tags,
    note_id_for,
    parse_front_matter,
    resolve_path,
    sanitize_tag,
)

DEFAULT_HALF_LIFE_DAYS = 30.0
SECONDS_PER_DAY = 86_400.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    node_pk INTEGER PRIMARY KEY,
    note_id TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    module TEXT,
    kind TEXT,
    status TEXT,
    tags_json TEXT NOT NULL,
    links_json TEXT NOT NULL,
    body TEXT NOT NULL,
    search_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    indexed_at REAL NOT NULL,
    deleted_at REAL
);

CREATE TABLE IF NOT EXISTS note_tags (
    node_pk INTEGER NOT NULL REFERENCES notes(node_pk),
    tag TEXT NOT NULL,
    PRIMARY KEY (node_pk, tag)
);

CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    started_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS attention_reads (
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id),
    note_id TEXT NOT NULL REFERENCES notes(note_id) ON UPDATE CASCADE,
    read_at REAL NOT NULL,
    read_order INTEGER NOT NULL,
    PRIMARY KEY (episode_id, note_id)
);

CREATE TABLE IF NOT EXISTS note_activation (
    note_id TEXT NOT NULL REFERENCES notes(note_id) ON UPDATE CASCADE,
    weight REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (note_id)
);

CREATE TABLE IF NOT EXISTS note_note_edges (
    note_a_id TEXT NOT NULL REFERENCES notes(note_id) ON UPDATE CASCADE,
    note_b_id TEXT NOT NULL REFERENCES notes(note_id) ON UPDATE CASCADE,
    weight REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (note_a_id, note_b_id)
);

CREATE TRIGGER IF NOT EXISTS reinforce_note_after_read
AFTER INSERT ON attention_reads
BEGIN
    INSERT INTO note_activation (note_id, weight, updated_at)
    VALUES (NEW.note_id, 1.0, NEW.read_at)
    ON CONFLICT(note_id) DO UPDATE SET
        weight = decay(
            note_activation.weight,
            note_activation.updated_at,
            excluded.updated_at
        ) + 1.0,
        updated_at = excluded.updated_at;
END;

CREATE TRIGGER IF NOT EXISTS reinforce_coactivation_after_read
AFTER INSERT ON attention_reads
BEGIN
    INSERT INTO note_note_edges (note_a_id, note_b_id, weight, updated_at)
    SELECT
        MIN(previous.note_id, NEW.note_id),
        MAX(previous.note_id, NEW.note_id),
        1.0,
        NEW.read_at
    FROM attention_reads previous
    WHERE previous.episode_id = NEW.episode_id
      AND previous.note_id <> NEW.note_id
    ON CONFLICT(note_a_id, note_b_id) DO UPDATE SET
        weight = decay(
            note_note_edges.weight,
            note_note_edges.updated_at,
            excluded.updated_at
        ) + 1.0,
        updated_at = excluded.updated_at;
END;

CREATE INDEX IF NOT EXISTS idx_notes_path ON notes(path);
CREATE INDEX IF NOT EXISTS idx_note_tags_tag ON note_tags(tag, node_pk);
CREATE INDEX IF NOT EXISTS idx_attention_reads_node
    ON attention_reads(note_id, read_at);
CREATE INDEX IF NOT EXISTS idx_attention_reads_episode_order
    ON attention_reads(episode_id, read_order);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    node_pk UNINDEXED,
    title,
    path,
    tags,
    body,
    tokenize='trigram'
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_terms_fts USING fts5(
    node_pk UNINDEXED,
    title,
    path,
    tags,
    body,
    tokenize='unicode61 remove_diacritics 2'
);
"""


def index_path() -> str:
    configured = os.environ.get("MEMORY_INDEX_PATH")
    return os.path.abspath(
        configured or os.path.join(BASE_DIR, ".memory-mcp", "memory.sqlite3")
    )


def decayed_weight(weight: float, updated_at: float, now: float) -> float:
    age_seconds = max(0.0, float(now) - float(updated_at))
    half_life_seconds = DEFAULT_HALF_LIFE_DAYS * SECONDS_PER_DAY
    return float(weight) * 2.0 ** (-age_seconds / half_life_seconds)


def connect_index() -> sqlite3.Connection:
    path = index_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    connection = sqlite3.connect(path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.create_function("decay", 3, decayed_weight, deterministic=True)
    connection.executescript(SCHEMA)
    return connection


@contextmanager
def open_index() -> Iterator[sqlite3.Connection]:
    connection = connect_index()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _memory_note_paths() -> list[str]:
    paths: list[str] = []
    for module in AGENT_MEMORY_MODULES:
        root = resolve_path(f"{AGENT_MEMORY_ROOT}/{module}")
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if filename.lower().endswith(".md"):
                    full_path = os.path.join(dirpath, filename)
                    paths.append(
                        os.path.relpath(full_path, BASE_DIR).replace("\\", "/")
                    )
    return sorted(paths)


def _extract_links(metadata: dict[str, Any], body: str) -> list[str]:
    links: list[str] = []
    for raw_link in metadata.get("links", []) or []:
        target = str(raw_link).strip()
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


def _upsert_note(connection: sqlite3.Connection, path: str) -> dict[str, Any]:
    full_path = resolve_path(path)
    with open(full_path, encoding="utf-8") as file:
        content = file.read()
    metadata, body = parse_front_matter(content)
    stat = os.stat(full_path)
    normalized_path = os.path.relpath(full_path, BASE_DIR).replace("\\", "/")
    note_id = note_id_for(normalized_path, metadata)
    title = str(
        metadata.get("title")
        or os.path.splitext(os.path.basename(normalized_path))[0]
    )
    module = str(metadata.get("module") or "") or None
    kind = str(metadata.get("kind") or "") or None
    status = str(metadata.get("status") or "") or None
    tags = normalize_tags(metadata.get("tags", []))
    links = _extract_links(metadata, body)
    search_text = "\n".join(
        [normalized_path, title, kind or "", " ".join(tags), body]
    )
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    indexed_at = time.time()

    connection.execute(
        """
        UPDATE notes
        SET note_id = ?
        WHERE path = ?
          AND note_id <> ?
          AND NOT EXISTS (SELECT 1 FROM notes WHERE note_id = ?)
        """,
        (note_id, normalized_path, note_id, note_id),
    )
    connection.execute(
        """
        INSERT INTO notes (
            note_id, path, title, module, kind, status, tags_json, links_json,
            body, search_text, content_hash, mtime_ns, size, indexed_at, deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(note_id) DO UPDATE SET
            path = excluded.path,
            title = excluded.title,
            module = excluded.module,
            kind = excluded.kind,
            status = excluded.status,
            tags_json = excluded.tags_json,
            links_json = excluded.links_json,
            body = excluded.body,
            search_text = excluded.search_text,
            content_hash = excluded.content_hash,
            mtime_ns = excluded.mtime_ns,
            size = excluded.size,
            indexed_at = excluded.indexed_at,
            deleted_at = NULL
        """,
        (
            note_id,
            normalized_path,
            title,
            module,
            kind,
            status,
            json.dumps(tags, ensure_ascii=False),
            json.dumps(links, ensure_ascii=False),
            body.strip(),
            search_text,
            content_hash,
            stat.st_mtime_ns,
            stat.st_size,
            indexed_at,
        ),
    )
    row = connection.execute(
        "SELECT node_pk FROM notes WHERE note_id = ?", (note_id,)
    ).fetchone()
    node_pk = int(row["node_pk"])
    connection.execute("DELETE FROM note_tags WHERE node_pk = ?", (node_pk,))
    connection.executemany(
        "INSERT INTO note_tags (node_pk, tag) VALUES (?, ?)",
        [(node_pk, tag) for tag in tags],
    )
    connection.execute("DELETE FROM notes_fts WHERE node_pk = ?", (node_pk,))
    connection.execute("DELETE FROM notes_terms_fts WHERE node_pk = ?", (node_pk,))
    connection.execute(
        "INSERT INTO notes_fts (node_pk, title, path, tags, body) VALUES (?, ?, ?, ?, ?)",
        (node_pk, title, normalized_path, " ".join(tags), body.strip()),
    )
    connection.execute(
        "INSERT INTO notes_terms_fts "
        "(node_pk, title, path, tags, body) VALUES (?, ?, ?, ?, ?)",
        (node_pk, title, normalized_path, " ".join(tags), body.strip()),
    )
    return {"node_pk": node_pk, "note_id": note_id, "path": normalized_path}


def index_note(path: str) -> dict[str, Any]:
    with open_index() as connection:
        return _upsert_note(connection, path)


def sync_memory_index() -> dict[str, int]:
    paths = _memory_note_paths()
    indexed = 0
    skipped = 0
    with open_index() as connection:
        connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS seen_paths (path TEXT PRIMARY KEY)"
        )
        connection.execute("DELETE FROM seen_paths")
        connection.executemany(
            "INSERT INTO seen_paths (path) VALUES (?)", [(path,) for path in paths]
        )
        for path in paths:
            full_path = resolve_path(path)
            stat = os.stat(full_path)
            existing = connection.execute(
                "SELECT mtime_ns, size, deleted_at FROM notes WHERE path = ?",
                (path,),
            ).fetchone()
            if (
                existing
                and int(existing["mtime_ns"]) == stat.st_mtime_ns
                and int(existing["size"]) == stat.st_size
                and existing["deleted_at"] is None
            ):
                skipped += 1
                continue
            _upsert_note(connection, path)
            indexed += 1

        now = time.time()
        deleted = connection.execute(
            """
            UPDATE notes
            SET deleted_at = ?
            WHERE deleted_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM seen_paths WHERE seen_paths.path = notes.path)
            """,
            (now,),
        ).rowcount
        connection.execute(
            "DELETE FROM notes_fts WHERE node_pk IN "
            "(SELECT node_pk FROM notes WHERE deleted_at IS NOT NULL)"
        )
        connection.execute(
            "DELETE FROM notes_terms_fts WHERE node_pk IN "
            "(SELECT node_pk FROM notes WHERE deleted_at IS NOT NULL)"
        )
    return {
        "found": len(paths),
        "indexed": indexed,
        "skipped": skipped,
        "deleted": deleted,
    }


def begin_episode(query_text: str) -> dict[str, Any]:
    episode_id = f"episode-{uuid.uuid4().hex}"
    started_at = time.time()
    with open_index() as connection:
        connection.execute(
            "INSERT INTO episodes "
            "(episode_id, query_text, started_at) VALUES (?, ?, ?)",
            (episode_id, query_text.strip(), started_at),
        )
    return {
        "episode_id": episode_id,
        "query_text": query_text.strip(),
        "started_at": started_at,
    }


def record_read(
    episode_id: str,
    path: str,
    observed_at: float | None = None,
) -> dict[str, Any]:
    indexed_note = index_note(path)
    event_time = float(observed_at or time.time())
    with open_index() as connection:
        next_order = int(
            connection.execute(
                "SELECT COALESCE(MAX(read_order), 0) + 1 AS next_order "
                "FROM attention_reads WHERE episode_id = ?",
                (episode_id,),
            ).fetchone()["next_order"]
        )
        inserted = connection.execute(
            """
            INSERT OR IGNORE INTO attention_reads (
                episode_id, note_id, read_at, read_order
            ) VALUES (?, ?, ?, ?)
            """,
            (
                episode_id,
                indexed_note["note_id"],
                event_time,
                next_order,
            ),
        ).rowcount
    return {
        "episode_id": episode_id,
        "note_id": indexed_note["note_id"],
        "path": indexed_note["path"],
        "recorded": bool(inserted),
    }


def rebuild_preference_edges() -> dict[str, int]:
    now = time.time()
    with open_index() as connection:
        connection.execute("DELETE FROM note_activation")
        connection.execute("DELETE FROM note_note_edges")
        connection.execute(
            """
            INSERT INTO note_activation (note_id, weight, updated_at)
            SELECT
                reads.note_id,
                SUM(decay(1.0, reads.read_at, ?)),
                ?
            FROM attention_reads reads
            GROUP BY reads.note_id
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO note_note_edges (note_a_id, note_b_id, weight, updated_at)
            SELECT
                MIN(earlier.note_id, later.note_id),
                MAX(earlier.note_id, later.note_id),
                SUM(decay(1.0, later.read_at, ?)),
                ?
            FROM attention_reads earlier
            JOIN attention_reads later
              ON later.episode_id = earlier.episode_id
             AND later.read_order > earlier.read_order
            GROUP BY
                MIN(earlier.note_id, later.note_id),
                MAX(earlier.note_id, later.note_id)
            """,
            (now, now),
        )
        event_count = int(
            connection.execute("SELECT COUNT(*) FROM attention_reads").fetchone()[0]
        )
        activated_notes = int(
            connection.execute(
                "SELECT COUNT(*) FROM note_activation"
            ).fetchone()[0]
        )
        note_edges = int(
            connection.execute("SELECT COUNT(*) FROM note_note_edges").fetchone()[0]
        )
    return {
        "events": event_count,
        "activated_notes": activated_notes,
        "note_edges": note_edges,
    }


def _search_conditions(
    module: str | None,
    tags: list[str] | None,
    kind: str | None,
    status: str | None,
) -> tuple[list[str], list[Any]]:
    conditions = ["n.deleted_at IS NULL"]
    parameters: list[Any] = []
    if module:
        conditions.append("n.module = ?")
        parameters.append(normalize_module(module))
    if kind:
        conditions.append("LOWER(n.kind) = ?")
        parameters.append(sanitize_tag(kind))
    if status:
        conditions.append("LOWER(n.status) = ?")
        parameters.append(status.strip().lower())
    for tag in normalize_tags(tags):
        conditions.append(
            "EXISTS (SELECT 1 FROM note_tags nt "
            "WHERE nt.node_pk = n.node_pk AND nt.tag = ?)"
        )
        parameters.append(tag)
    return conditions, parameters


def _result_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["note_id"]),
        "path": str(row["path"]),
        "title": str(row["title"]),
        "module": row["module"],
        "kind": row["kind"],
        "status": row["status"],
        "tags": json.loads(str(row["tags_json"])),
        "links": json.loads(str(row["links_json"])),
    }


def search_notes_index(
    query: str | None = None,
    module: str | None = None,
    tags: list[str] | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query_text = (query or "").strip()
    conditions, parameters = _search_conditions(module, tags, kind, status)
    with open_index() as connection:
        if len(query_text) >= 3:
            phrase = '"' + query_text.replace('"', '""') + '"'
            sql = f"""
                SELECT n.*, bm25(notes_fts) AS raw_rank
                FROM notes_fts
                JOIN notes n ON n.node_pk = notes_fts.node_pk
                WHERE notes_fts MATCH ? AND {' AND '.join(conditions)}
                ORDER BY raw_rank, n.path
                LIMIT ? OFFSET ?
            """
            rows = connection.execute(
                sql, [phrase, *parameters, max(1, limit), max(0, offset)]
            ).fetchall()
            match_mode = "fts-trigram"
        elif query_text and query_text.isascii():
            phrase = '"' + query_text.replace('"', '""') + '"'
            sql = f"""
                SELECT n.*, bm25(notes_terms_fts) AS raw_rank
                FROM notes_terms_fts
                JOIN notes n ON n.node_pk = notes_terms_fts.node_pk
                WHERE notes_terms_fts MATCH ? AND {' AND '.join(conditions)}
                ORDER BY raw_rank, n.path
                LIMIT ? OFFSET ?
            """
            rows = connection.execute(
                sql, [phrase, *parameters, max(1, limit), max(0, offset)]
            ).fetchall()
            match_mode = "fts-token"
        else:
            text_condition = ""
            text_parameters: list[Any] = []
            if query_text:
                text_condition = " AND INSTR(LOWER(n.search_text), LOWER(?)) > 0"
                text_parameters.append(query_text)
            sql = f"""
                SELECT n.*, 0.0 AS raw_rank
                FROM notes n
                WHERE {' AND '.join(conditions)}{text_condition}
                ORDER BY n.path
                LIMIT ? OFFSET ?
            """
            rows = connection.execute(
                sql,
                [
                    *parameters,
                    *text_parameters,
                    max(1, limit),
                    max(0, offset),
                ],
            ).fetchall()
            match_mode = "substring" if query_text else "metadata"

    results: list[dict[str, Any]] = []
    for position, row in enumerate(rows, start=max(0, offset) + 1):
        result = _result_from_row(row)
        result["search_rank"] = position
        result["search_score"] = 1.0 / position
        result["match_mode"] = match_mode
        results.append(result)
    return results


def recall_notes_index(
    episode_id: str,
    limit: int = 7,
) -> list[dict[str, Any]]:
    now = time.time()
    with open_index() as connection:
        episode = connection.execute(
            "SELECT query_text FROM episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
    if episode is None:
        raise ValueError(f"Unknown episode_id: {episode_id}")
    query_text = str(episode["query_text"])

    query_seeds: dict[str, float] = {}
    if query_text:
        text_candidates = search_notes_index(
            query=query_text, limit=max(100, max(1, limit) * 20)
        )
        query_seeds = {
            str(item["id"]): float(item["search_score"])
            for item in text_candidates
        }

    with open_index() as connection:
        current_note_ids = [
            str(row["note_id"])
            for row in connection.execute(
                "SELECT note_id FROM attention_reads WHERE episode_id = ?",
                (episode_id,),
            )
        ]
        
        # Merge query matches and episode read notes into a single seed set
        seeds: dict[str, float] = {}
        for note_id, energy in query_seeds.items():
            seeds[note_id] = max(seeds.get(note_id, 0.0), energy)
        for note_id in current_note_ids:
            seeds[note_id] = max(seeds.get(note_id, 0.0), 1.0)

        # Spreading activation (Graph Expansion) along co-activation edges
        coactivation_spread: dict[str, float] = {}
        if seeds:
            placeholders = ",".join("?" for _ in seeds)
            sql = f"""
                SELECT
                    edge.note_b_id AS neighbor_id,
                    edge.note_a_id AS seed_id,
                    decay(edge.weight, edge.updated_at, ?) AS edge_weight
                FROM note_note_edges edge
                WHERE edge.note_a_id IN ({placeholders})
                UNION ALL
                SELECT
                    edge.note_a_id AS neighbor_id,
                    edge.note_b_id AS seed_id,
                    decay(edge.weight, edge.updated_at, ?) AS edge_weight
                FROM note_note_edges edge
                WHERE edge.note_b_id IN ({placeholders})
            """
            params = [now, *seeds.keys(), now, *seeds.keys()]
            co_rows = connection.execute(sql, params).fetchall()
            for row in co_rows:
                neighbor_id = str(row["neighbor_id"])
                seed_id = str(row["seed_id"])
                seed_energy = seeds.get(seed_id, 0.0)
                edge_weight = float(row["edge_weight"])
                # Energy contribution = seed_stimulus * ln(1 + decayed_edge_weight)
                spread_contrib = seed_energy * math.log1p(edge_weight)
                coactivation_spread[neighbor_id] = coactivation_spread.get(neighbor_id, 0.0) + spread_contrib

        # Get general prior activation (recency/frequency)
        activation_rows = connection.execute(
            """
            SELECT note_id, decay(weight, updated_at, ?) AS weight
            FROM note_activation
            """,
            (now,),
        ).fetchall()
        activation_components = {
            str(row["note_id"]): float(row["weight"])
            for row in activation_rows
        }

        # Build final candidate pool (excluding notes already read in the current episode)
        candidate_note_ids = (
            set(query_seeds)
            | set(activation_components)
            | set(coactivation_spread)
        ) - set(current_note_ids)

        if not candidate_note_ids:
            return []
        
        placeholders = ",".join("?" for _ in candidate_note_ids)
        note_rows = connection.execute(
            f"""
            SELECT * FROM notes
            WHERE deleted_at IS NULL AND note_id IN ({placeholders})
            """,
            list(candidate_note_ids),
        ).fetchall()

    results: list[dict[str, Any]] = []
    for row in note_rows:
        note_id = str(row["note_id"])
        direct_energy = query_seeds.get(note_id, 0.0)
        activation_weight = activation_components.get(note_id, 0.0)
        spread_energy = coactivation_spread.get(note_id, 0.0)
        
        # recall_score = P(i) + E_direct(i) + E_spread(i)
        recall_score = (
            math.log1p(activation_weight)
            + direct_energy
            + spread_energy
        )
        
        result = _result_from_row(row)
        result.update(
            {
                "recall_score": recall_score,
                "direct_stimulus": direct_energy,
                "base_activation": activation_weight,
                "spread_activation": spread_energy,
            }
        )
        results.append(result)
        
    results.sort(key=lambda item: (-item["recall_score"], item["path"]))
    return results[: max(1, limit)]


def public_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in result.items() if not key.startswith("_")}
        for result in results
    ]

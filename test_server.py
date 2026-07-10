import os
import tempfile
import time
import unittest
import uuid

from mcp_server.common import parse_front_matter, resolve_path
from mcp_server.index import (
    begin_episode,
    open_index,
    rebuild_preference_edges,
    record_read,
    sync_memory_index,
)
from mcp_server.memorize import save_model_note, save_simulation_note
from mcp_server.recall import (
    get_backlinks,
    get_linked_chain,
    read_agent_memory_note,
    recall_agent_memory_notes,
    search_agent_memory_notes,
)


class TestInvestmentAgentMemoryServer(unittest.TestCase):
    def setUp(self) -> None:
        self.created_paths: list[str] = []
        self.index_directory = tempfile.TemporaryDirectory()
        self.previous_index_path = os.environ.get("MEMORY_INDEX_PATH")
        os.environ["MEMORY_INDEX_PATH"] = os.path.join(
            self.index_directory.name, "memory.sqlite3"
        )

    def tearDown(self) -> None:
        for path in self.created_paths:
            full_path = resolve_path(path)
            if os.path.exists(full_path):
                os.remove(full_path)
        if self.previous_index_path is None:
            os.environ.pop("MEMORY_INDEX_PATH", None)
        else:
            os.environ["MEMORY_INDEX_PATH"] = self.previous_index_path
        self.index_directory.cleanup()

    def remember(self, path: str) -> str:
        self.created_paths.append(path)
        return path

    def test_agent_memory_write_search_backlink_and_chain(self) -> None:
        unique = uuid.uuid4().hex[:8]
        model_path = self.remember(
            save_model_note(
                "rule",
                f"Unit Test Model {unique}",
                "# Unit Test Model\n\nStable rule.",
                tags=["test/unit", "ticker/GOOG"],
                status="accepted",
            )
        )
        simulation_path = self.remember(
            save_simulation_note(
                "prediction",
                f"Unit Test Simulation {unique}",
                "# Unit Test Simulation\n\nPrediction body.",
                tags=["test/unit", "ticker/GOOG"],
                links=[model_path.removesuffix(".md")],
            )
        )

        full_model_path = resolve_path(model_path)
        self.assertTrue(os.path.exists(full_model_path))
        with open(full_model_path, encoding="utf-8") as file:
            metadata, body = parse_front_matter(file.read())
        self.assertEqual(metadata["module"], "model")
        self.assertTrue(metadata["id"].startswith("mem-"))
        self.assertIn("agent-memory/model", metadata["tags"])
        self.assertIn("Stable rule", body)

        note = read_agent_memory_note(f"Unit Test Simulation {unique}")
        self.assertEqual(note["path"], simulation_path)
        self.assertEqual(note["module"], "simulation")

        results = search_agent_memory_notes(
            tags=["test/unit", "ticker/GOOG"], module="simulation"
        )
        self.assertTrue(any(item["path"] == simulation_path for item in results))

        backlinks = get_backlinks(model_path)
        self.assertTrue(any(item["path"] == simulation_path for item in backlinks))

        chain = get_linked_chain(simulation_path, depth=1)
        self.assertTrue(
            any(
                edge["from"] == simulation_path and edge["to"] == model_path
                for edge in chain["edges"]
            )
        )

    def test_note_id_and_created_date_survive_an_update(self) -> None:
        unique = uuid.uuid4().hex[:8]
        path = self.remember(
            save_model_note(
                "rule",
                f"Stable Identity {unique}",
                "First version.",
                properties={"created": "2001-02-03"},
            )
        )
        with open(resolve_path(path), encoding="utf-8") as file:
            first_metadata, _ = parse_front_matter(file.read())

        self.remember(
            save_model_note(
                "rule",
                f"Stable Identity {unique}",
                "Second version.",
            )
        )
        with open(resolve_path(path), encoding="utf-8") as file:
            second_metadata, second_body = parse_front_matter(file.read())

        self.assertEqual(second_metadata["id"], first_metadata["id"])
        self.assertEqual(second_metadata["created"], "2001-02-03")
        self.assertIn("Second version", second_body)

    def test_attention_schema_contains_only_atomic_records(self) -> None:
        sync_memory_index()
        with open_index() as connection:
            tables = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            episode_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(episodes)")
            }
            read_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(attention_reads)")
            }
        self.assertNotIn("contexts", tables)
        self.assertNotIn("episode_contexts", tables)
        self.assertNotIn("context_note_edges", tables)
        self.assertNotIn("perspectives", tables)
        self.assertNotIn("perspective_note_edges", tables)
        self.assertIn("note_activation", tables)
        self.assertEqual(
            episode_columns,
            {"episode_id", "query_text", "started_at"},
        )
        self.assertEqual(
            read_columns,
            {"episode_id", "note_id", "read_at", "read_order"},
        )

    def test_recall_uses_the_index_without_scanning_the_vault(self) -> None:
        sync_memory_index()
        unique = uuid.uuid4().hex[:8]
        path = self.remember(
            save_model_note(
                "concept",
                f"Cold Index Node {unique}",
                "This external Markdown edit is not indexed yet.",
            )
        )
        episode = begin_episode(f"Cold Index Node {unique}")

        cold_recall = recall_agent_memory_notes(episode["episode_id"])
        self.assertNotIn(path, {item["path"] for item in cold_recall})

        searched = search_agent_memory_notes(
            query=f"Cold Index Node {unique}", limit=5
        )
        self.assertEqual(searched[0]["path"], path)
        warm_recall = recall_agent_memory_notes(episode["episode_id"])
        self.assertEqual(warm_recall[0]["path"], path)

    def test_read_events_shape_recall_but_never_search(self) -> None:
        unique = uuid.uuid4().hex[:8]
        alpha_path = self.remember(
            save_model_note(
                "concept",
                f"Preference Alpha {unique}",
                "Alpha attention node with Q7 as an exact token.",
                tags=[f"test/preference-{unique}"],
            )
        )
        beta_path = self.remember(
            save_model_note(
                "concept",
                f"Preference Beta {unique}",
                "Beta attention node.",
                tags=[f"test/preference-{unique}"],
            )
        )
        gamma_path = self.remember(
            save_model_note(
                "concept",
                f"Preference Gamma {unique}",
                "Gamma attention node with aq7b as an embedded substring.",
                tags=[f"test/preference-{unique}"],
            )
        )
        sync_memory_index()

        short_token_results = search_agent_memory_notes(query="Q7", limit=100)
        short_token_paths = {item["path"] for item in short_token_results}
        self.assertIn(alpha_path, short_token_paths)
        self.assertNotIn(gamma_path, short_token_paths)
        self.assertTrue(
            all(item["match_mode"] == "fts-token" for item in short_token_results)
        )

        first_episode = begin_episode("first attention path")
        observed_at = time.time()
        self.assertTrue(
            record_read(
                first_episode["episode_id"],
                alpha_path,
                observed_at,
            )["recorded"]
        )
        self.assertTrue(
            record_read(
                first_episode["episode_id"],
                beta_path,
                observed_at + 1,
            )["recorded"]
        )
        self.assertFalse(
            record_read(
                first_episode["episode_id"],
                beta_path,
                observed_at + 2,
            )["recorded"]
        )

        second_episode = begin_episode("current intuitive path")
        record_read(
            second_episode["episode_id"],
            alpha_path,
            observed_at + 3,
        )
        recalled = recall_agent_memory_notes(second_episode["episode_id"])
        self.assertEqual(recalled[0]["path"], beta_path)
        self.assertGreater(recalled[0]["base_activation"], 0)
        self.assertGreater(recalled[0]["spread_activation"], 0)

        searched = search_agent_memory_notes(
            query=f"Preference Gamma {unique}", limit=5
        )
        self.assertEqual(searched[0]["path"], gamma_path)
        self.assertNotIn("recall_score", searched[0])

        rebuilt = rebuild_preference_edges()
        self.assertEqual(rebuilt["events"], 3)
        recalled_after_rebuild = recall_agent_memory_notes(
            second_episode["episode_id"]
        )
        self.assertEqual(recalled_after_rebuild[0]["path"], beta_path)

    def test_move_and_delete_keep_attention_history_consistent(self) -> None:
        unique = uuid.uuid4().hex[:8]
        original_path = self.remember(
            save_model_note(
                "concept",
                f"Movable Attention Node {unique}",
                "This node will move and then disappear.",
            )
        )
        sync_memory_index()
        original_note = read_agent_memory_note(original_path)
        episode = begin_episode("move and delete")
        record_read(episode["episode_id"], original_path)

        moved_path = original_path.removesuffix(".md") + "_moved.md"
        os.replace(resolve_path(original_path), resolve_path(moved_path))
        self.remember(moved_path)
        sync_memory_index()
        moved_results = search_agent_memory_notes(
            query=f"Movable Attention Node {unique}", limit=5
        )
        self.assertEqual(moved_results[0]["id"], original_note["id"])
        self.assertEqual(moved_results[0]["path"], moved_path)

        os.remove(resolve_path(moved_path))
        sync_memory_index()
        deleted_results = search_agent_memory_notes(
            query=f"Movable Attention Node {unique}", limit=5
        )
        self.assertEqual(deleted_results, [])
        with open_index() as connection:
            event_count = connection.execute(
                "SELECT COUNT(*) FROM attention_reads"
            ).fetchone()[0]
            deleted_at = connection.execute(
                "SELECT deleted_at FROM notes WHERE note_id = ?",
                (original_note["id"],),
            ).fetchone()[0]
        self.assertEqual(event_count, 1)
        self.assertIsNotNone(deleted_at)


if __name__ == "__main__":
    unittest.main()

import os
import unittest
import uuid

from mcp_server.policy import scan_text_for_secrets, validate_safe_write
from mcp_server.vault import (
    get_backlinks,
    get_linked_chain,
    parse_front_matter,
    read_agent_memory_note,
    resolve_path,
    save_model_note,
    save_simulation_note,
    search_agent_memory_notes,
)


class TestInvestmentAgentMemoryServer(unittest.TestCase):
    def setUp(self) -> None:
        self.created_paths: list[str] = []

    def tearDown(self) -> None:
        for path in self.created_paths:
            full_path = resolve_path(path)
            if os.path.exists(full_path):
                os.remove(full_path)

    def remember(self, path: str) -> str:
        self.created_paths.append(path)
        return path

    def test_secret_scanner(self) -> None:
        self.assertTrue(scan_text_for_secrets("AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P67"))
        self.assertTrue(
            scan_text_for_secrets("sk-123456789012345678901234567890123456789012345678")
        )
        self.assertTrue(scan_text_for_secrets("password='mysecretpassword'"))
        self.assertEqual(scan_text_for_secrets("Normal text without keys."), [])

    def test_safe_write_validation(self) -> None:
        validate_safe_write("test.md", "This is clean.")
        with self.assertRaises(ValueError):
            validate_safe_write("test.md", "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P67")
        with self.assertRaises(ValueError):
            validate_safe_write("dangerous.py", "print('hello')")

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


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Chat data models, ChatStore, and chat service helper functions."""
import tempfile
import unittest
from pathlib import Path

from llama_data import ChatMessage, ChatSession, ChatStore, DataPaths, SystemPromptTemplate
from app.services.chat_service import build_openai_messages, encode_image_to_base64


class TestChatStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.paths = DataPaths(
            data_dir=Path(self.tmp_dir.name),
            config_path=Path(self.tmp_dir.name) / "config.json",
            profiles_path=Path(self.tmp_dir.name) / "profiles.json",
            library_path=Path(self.tmp_dir.name) / "library.json",
            cards_dir=Path(self.tmp_dir.name) / "cards",
            schema_cache_path=Path(self.tmp_dir.name) / "schema_cache.json",
            chat_sessions_path=Path(self.tmp_dir.name) / "chat_sessions.json",
            chat_templates_path=Path(self.tmp_dir.name) / "chat_templates.json",
        )
        self.store = ChatStore(self.paths)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_session_lifecycle(self):
        sessions = self.store.load_sessions()
        self.assertEqual(len(sessions), 0)

        session = ChatSession(id="sess-1", title="Test Session", system_prompt="Be helpful")
        msg = ChatMessage(id="msg-1", role="user", content="Hello world")
        session.messages.append(msg)

        self.store.upsert_session(session)

        loaded = self.store.load_sessions()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "sess-1")
        self.assertEqual(loaded[0].title, "Test Session")
        self.assertEqual(len(loaded[0].messages), 1)
        self.assertEqual(loaded[0].messages[0].content, "Hello world")

        # Delete session
        self.store.delete_session("sess-1")
        self.assertEqual(len(self.store.load_sessions()), 0)

    def test_system_prompt_templates(self):
        templates = self.store.load_templates()
        self.assertGreaterEqual(len(templates), 5)  # Built-ins present

        custom = SystemPromptTemplate(id="custom-1", name="Custom AI", prompt="You are Custom AI", is_builtin=False)
        self.store.upsert_template(custom)

        updated = self.store.load_templates()
        custom_found = [t for t in updated if t.id == "custom-1"]
        self.assertEqual(len(custom_found), 1)
        self.assertEqual(custom_found[0].prompt, "You are Custom AI")

    def test_build_openai_messages_vision(self):
        # Create dummy image file
        img_path = Path(self.tmp_dir.name) / "test.png"
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="red")
        img.save(img_path)

        msg = ChatMessage(id="m1", role="user", content="What is in this photo?", image_paths=[str(img_path)])
        openai_msgs = build_openai_messages([msg], system_prompt="Vision Assistant")

        self.assertEqual(len(openai_msgs), 2)  # System + User
        self.assertEqual(openai_msgs[0]["role"], "system")
        self.assertEqual(openai_msgs[1]["role"], "user")

        user_content = openai_msgs[1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertEqual(user_content[0]["type"], "text")
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertTrue(user_content[1]["image_url"]["url"].startswith("data:image/"))


if __name__ == "__main__":
    unittest.main()

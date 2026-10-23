import unittest

from app.services.llm_service import normalize_history_messages


class NormalizeHistoryMessagesTest(unittest.TestCase):
    def test_filters_invalid_entries_and_normalizes_content(self):
        raw_history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": 123},
            {"role": "user"},
            "bad-entry",
            None,
        ]

        normalized = normalize_history_messages(raw_history)

        self.assertEqual(normalized, [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "123"}])

    def test_returns_empty_list_for_none_or_empty(self):
        self.assertEqual(normalize_history_messages(None), [])
        self.assertEqual(normalize_history_messages([]), [])


if __name__ == "__main__":
    unittest.main()

"""Test dictation diff edge cases: Chinese punctuation, quotes, case, hyphens, whitespace."""
import unittest
from app.diff import compute_diff, tokenize


class TestDiffEdgeCases(unittest.TestCase):
    def test_chinese_punctuation_ignored(self):
        expected = "Hi Sarah, do you have a moment? I wanted to talk about the project."
        # User input with Chinese comma, question mark, and Chinese period
        user_input = "Hi Sarah， do you have a moment？ I wanted to talk about the project。"
        res = compute_diff(expected, user_input, ignore_punctuation=True)
        self.assertEqual(res["accuracy"], 100.0)
        self.assertTrue(all(t["type"] == "correct" for t in res["tokens"]))

    def test_chinese_quotes_and_brackets(self):
        expected = "He said we need a new approach and better solutions."
        user_input = "He said “we need a new approach” and 《better solutions》."
        res = compute_diff(expected, user_input, ignore_punctuation=True)
        self.assertEqual(res["accuracy"], 100.0)

    def test_curly_apostrophes(self):
        expected = "I don't think it's going to work, and we'll see."
        # User typed curly quotes ’ (U+2019) instead of ASCII '
        user_input = "I don’t think it’s going to work, and we’ll see."
        res = compute_diff(expected, user_input, ignore_punctuation=True)
        self.assertEqual(res["accuracy"], 100.0)

    def test_excessive_whitespace_and_tabs(self):
        expected = "Good morning everyone today we discuss urban planning."
        user_input = "   Good   morning \t everyone  \n  today   we \u3000 discuss   urban   planning.  "
        res = compute_diff(expected, user_input, ignore_punctuation=True)
        self.assertEqual(res["accuracy"], 100.0)

    def test_case_sensitivity_flag(self):
        expected = "The United States and European Union"
        user_input = "the united states and european union"
        # Case insensitive by default -> 100%
        res_insensitive = compute_diff(expected, user_input, case_sensitive=False)
        self.assertEqual(res_insensitive["accuracy"], 100.0)
        # Case sensitive -> low accuracy
        res_sensitive = compute_diff(expected, user_input, case_sensitive=True)
        self.assertLess(res_sensitive["accuracy"], 100.0)

    def test_partial_correct_classifications(self):
        expected = "The quick brown fox jumps over the lazy dog"
        # "quick" replaced by "fast" (wrong), "brown" missing, "red" extra
        user_input = "The fast fox jumps over the lazy dog red"
        res = compute_diff(expected, user_input)
        types = [t["type"] for t in res["tokens"]]
        self.assertIn("correct", types)
        self.assertIn("missing", types)
        self.assertIn("extra", types)
        self.assertGreater(res["accuracy"], 50.0)
        self.assertLess(res["accuracy"], 100.0)

    def test_completely_wrong_input(self):
        expected = "Artificial intelligence creates new opportunities"
        user_input = "Banana apple orange grape watermelon"
        res = compute_diff(expected, user_input)
        self.assertEqual(res["accuracy"], 0.0)
        self.assertEqual(res["correct_count"], 0)

    def test_empty_user_input(self):
        expected = "Welcome to the presentation."
        res = compute_diff(expected, "")
        self.assertEqual(res["accuracy"], 0.0)
        self.assertEqual(res["actual_count"], 0)
        self.assertTrue(all(t["type"] == "missing" for t in res["tokens"]))

    def test_empty_expected(self):
        res = compute_diff("", "Some words entered")
        self.assertEqual(res["accuracy"], 0.0)
        self.assertTrue(all(t["type"] == "extra" for t in res["tokens"]))

    def test_quoted_words_boundary_stripping(self):
        expected = "Please open the file"
        user_input = "Please open 'the' \"file\""
        res = compute_diff(expected, user_input, ignore_punctuation=True)
        self.assertEqual(res["accuracy"], 100.0)

    def test_hyphenated_words(self):
        expected = "This is a state-of-the-art solution."
        user_input = "This is a state-of-the-art solution."
        res = compute_diff(expected, user_input)
        self.assertEqual(res["accuracy"], 100.0)


if __name__ == "__main__":
    unittest.main()

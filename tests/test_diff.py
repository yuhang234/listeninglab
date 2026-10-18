import unittest
from app.diff import compute_diff, tokenize


class TestDiff(unittest.TestCase):
    def test_tokenize_basic(self):
        self.assertEqual(tokenize("Hello world!"), ["hello", "world"])

    def test_tokenize_preserve_case(self):
        self.assertEqual(tokenize("Hello World", case_sensitive=True), ["Hello", "World"])

    def test_perfect_match(self):
        r = compute_diff("Hello world", "Hello world")
        self.assertEqual(r["accuracy"], 100.0)
        self.assertEqual(len(r["tokens"]), 2)
        self.assertEqual(r["tokens"][0]["type"], "correct")

    def test_missing_word(self):
        r = compute_diff("Hello beautiful world", "Hello world")
        self.assertEqual(r["accuracy"], 66.7)  # 2 correct / 3 expected
        types = [t["type"] for t in r["tokens"]]
        self.assertIn("missing", types)

    def test_extra_word(self):
        r = compute_diff("Hello world", "Hello there world")
        self.assertEqual(r["accuracy"], 100.0)  # 2 correct / 2 expected
        types = [t["type"] for t in r["tokens"]]
        self.assertIn("extra", types)

    def test_wrong_word(self):
        r = compute_diff("Hello world", "Hello worlD")
        self.assertEqual(r["accuracy"], 100.0)  # case insensitive by default
        r2 = compute_diff("Hello world", "Hello worlD", case_sensitive=True)
        self.assertLess(r2["accuracy"], 100.0)

    def test_punctuation_ignored(self):
        r = compute_diff("Hello, world!", "Hello world")
        self.assertEqual(r["accuracy"], 100.0)

    def test_complex(self):
        r = compute_diff("The quick brown fox", "The quik brown fox jumps")
        self.assertGreater(r["accuracy"], 0)
        self.assertLess(r["accuracy"], 100)


if __name__ == "__main__":
    unittest.main()
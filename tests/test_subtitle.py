import unittest
from app.import_data import parse_subtitle


class TestSubtitle(unittest.TestCase):
    def test_srt_parsing(self):
        srt = """1
00:00:01,000 --> 00:00:05,000
Hello world

2
00:00:06,000 --> 00:00:10,000
Second sentence"""
        sentences = parse_subtitle(srt, "srt")
        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0]["english"], "Hello world")
        self.assertEqual(sentences[0]["start_time"], 1.0)
        self.assertEqual(sentences[0]["end_time"], 5.0)

    def test_lrc_parsing(self):
        lrc = """[00:01.50]Line one
[00:05.20]Line two
[00:08.00]Line three"""
        sentences = parse_subtitle(lrc, "lrc")
        self.assertEqual(len(sentences), 3)
        self.assertEqual(sentences[0]["english"], "Line one")
        self.assertAlmostEqual(sentences[0]["start_time"], 1.5)
        self.assertAlmostEqual(sentences[1]["start_time"], 5.2)

    def test_txt_parsing(self):
        txt = "First line\nSecond line\nThird line"
        sentences = parse_subtitle(txt, "txt")
        self.assertEqual(len(sentences), 3)
        self.assertEqual(sentences[1]["english"], "Second line")

    def test_empty(self):
        self.assertEqual(parse_subtitle("", "srt"), [])


if __name__ == "__main__":
    unittest.main()
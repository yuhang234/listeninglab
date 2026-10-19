"""Test subtitle parser validation with legal and illegal inputs (SRT, LRC, TXT)."""
import unittest
from app.import_data import parse_subtitle


class TestSubtitleValidation(unittest.TestCase):
    def test_legal_srt_with_varying_timestamps(self):
        srt = """1
00:00:01,200 --> 00:00:04,500
First line of text.

2
01:02:03.456 --> 01:02:07.890
Second line with dot separator.
"""
        sentences = parse_subtitle(srt, "srt")
        self.assertEqual(len(sentences), 2)
        self.assertAlmostEqual(sentences[0]["start_time"], 1.2)
        self.assertAlmostEqual(sentences[0]["end_time"], 4.5)
        self.assertEqual(sentences[0]["english"], "First line of text.")
        self.assertAlmostEqual(sentences[1]["start_time"], 3723.456)
        self.assertAlmostEqual(sentences[1]["end_time"], 3727.89)

    def test_legal_lrc(self):
        lrc = """[00:02.10]Hello world
[00:05.40]Second sentence
[00:09.00]Third sentence
"""
        sentences = parse_subtitle(lrc, "lrc")
        self.assertEqual(len(sentences), 3)
        self.assertAlmostEqual(sentences[0]["start_time"], 2.1)
        self.assertAlmostEqual(sentences[0]["end_time"], 5.4)
        self.assertEqual(sentences[0]["english"], "Hello world")

    def test_legal_txt(self):
        txt = "Line one\n\nLine two\nLine three\n"
        sentences = parse_subtitle(txt, "txt")
        self.assertEqual(len(sentences), 3)
        self.assertEqual(sentences[0]["english"], "Line one")
        self.assertEqual(sentences[1]["english"], "Line two")
        self.assertEqual(sentences[2]["english"], "Line three")

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(parse_subtitle("", "srt"), [])
        self.assertEqual(parse_subtitle("   \n\t ", "lrc"), [])
        self.assertEqual(parse_subtitle("", "txt"), [])

    def test_unsupported_format_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            parse_subtitle("Some content", "pdf")
        self.assertIn("不支持的字幕格式", str(ctx.exception))

    def test_malformed_srt_no_valid_blocks_raises_value_error(self):
        bad_srt = "This is a random text file pretending to be srt without timestamps."
        with self.assertRaises(ValueError) as ctx:
            parse_subtitle(bad_srt, "srt")
        self.assertIn("SRT 字幕格式无效", str(ctx.exception))

    def test_malformed_srt_invalid_time_raises_value_error(self):
        bad_time_srt = """1
00:invalid:time --> 00:00:05,000
Invalid time line
"""
        with self.assertRaises(ValueError) as ctx:
            parse_subtitle(bad_time_srt, "srt")
        self.assertIn("时间格式无效", str(ctx.exception))

    def test_malformed_lrc_no_timestamps_raises_value_error(self):
        bad_lrc = "Just text without brackets and numbers."
        with self.assertRaises(ValueError) as ctx:
            parse_subtitle(bad_lrc, "lrc")
        self.assertIn("LRC 歌词格式无效", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

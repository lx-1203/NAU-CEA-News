import unittest

from pipeline.outro import credit_cards, append_outro_timeline


class OutroTests(unittest.TestCase):
    def test_explicit_single_producer_and_default_deduplication(self):
        template = [{"label": "制片人", "lines": ["星迹 · Codex"]},
                    {"label": "参演人员", "lines": ["楠小禾 · 秾小序"]},
                    {"label": "片尾音乐", "lines": ["南京农业大学之歌"]}]
        self.assertEqual(credit_cards(template, "星迹", only=True)[0]["lines"], ["星迹"])
        self.assertEqual(credit_cards(template, "星迹")[0]["lines"], ["星迹 · Codex"])
        self.assertEqual(template[0]["lines"], ["星迹 · Codex"])

    def test_tail_captions_and_chapter_are_shifted_from_body_end(self):
        timeline = {"shots": [{"scene": 0, "start": 0, "end": 10}]}
        source = {"version": "1.4.1", "duration": 24.4, "lines": [
            {"text": "下期再见", "anchor": "xiaoXu", "start": .3, "end": 2.3}
        ]}
        tail = append_outro_timeline(timeline, source)
        self.assertEqual((tail["start"], tail["end"]), (10, 34.4))
        self.assertEqual((tail["lines"][0]["start"], tail["lines"][0]["end"]), (10.3, 12.3))
        self.assertEqual(timeline["outro"], tail)

    def test_rejects_a_duplicate_legacy_ending(self):
        timeline = {"shots": [{"scene": -2, "start": 8, "end": 10}]}
        with self.assertRaises(ValueError):
            append_outro_timeline(timeline, {"version": "1.4.1", "duration": 24.4, "lines": []})

import unittest

import app


class AdminCompetitionCatalogTests(unittest.TestCase):
    def test_only_catalogued_competitions_are_canonicalized(self):
        profiles = [
            {
                "name": "中国国际互联网+大学生创新创业大赛",
                "aliases": ["互联网+", "中国国际大学生创新大赛"],
            },
            {
                "name": "iCAN大学生创新创业大赛",
                "aliases": ["iCAN"],
            },
        ]

        self.assertEqual(
            app._canonical_record_competition("互联网+", profiles),
            "中国国际互联网+大学生创新创业大赛",
        )
        self.assertEqual(
            app._canonical_record_competition(" iCAN ", profiles),
            "iCAN大学生创新创业大赛",
        )
        self.assertIsNone(app._canonical_record_competition("正大杯", profiles))
        self.assertIsNone(app._canonical_record_competition("", profiles))


if __name__ == "__main__":
    unittest.main()

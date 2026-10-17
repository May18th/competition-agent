import unittest

from artifact_consistency import (check_artifact_consistency,
                                  check_generation_artifacts,
                                  extract_facts, issues_as_dicts)


class ArtifactConsistencyTests(unittest.TestCase):
    def test_reports_same_label_conflict_with_source_evidence(self):
        issues = check_artifact_consistency({
            "proposal": "准确率达到 90%，试点 30 桶，单桶成本 260 元。",
            "deck": "实测准确率 85%；试点30桶，单桶成本0.026万元。",
            "speech": "团队成员共 5 人。",
        })
        self.assertEqual([issue.label for issue in issues], ["accuracy"])
        self.assertEqual(issues[0].code, "fact_conflict")
        self.assertEqual({fact.source for fact in issues[0].facts}, {"proposal", "deck"})

    def test_normalises_currency_and_does_not_flag_equal_facts(self):
        self.assertEqual(check_artifact_consistency({
            "proposal": "单桶成本 260 元，年费 3000 元",
            "deck": "单桶成本0.026万元，年费 0.3 万元",
        }), [])

    def test_ignores_unlabelled_years_scores_and_section_numbers(self):
        text = "2026年，第3章，评委评分86分；团队名称未填写。"
        self.assertEqual(extract_facts(text), [])
        self.assertEqual(check_artifact_consistency({"proposal": text, "deck": "2025年，第4章，评分92分"}), [])

    def test_skips_ambiguous_source_with_multiple_values_for_one_label(self):
        self.assertEqual(check_artifact_consistency({
            "proposal": "目标准确率 95%，实测准确率 90%。",
            "deck": "准确率 90%。",
        }), [])

    def test_structured_issues_are_json_friendly(self):
        result = issues_as_dicts({"a": "已申请专利 1 项", "b": "已申请专利 2 项"})
        self.assertEqual(result[0]["label"], "patent_count")
        self.assertEqual(result[0]["facts"][0]["source"], "a")

    def test_generation_payload_checks_proposal_outline_and_speech(self):
        warnings = check_generation_artifacts({
            "proposal": "准确率 90%。",
            "ppt_outline": "准确率 90%。",
            "speech_script": "准确率 85%。",
        })
        self.assertEqual(len(warnings), 1)
        self.assertIn("申报书", warnings[0]["message"])
        self.assertIn("路演稿", warnings[0]["message"])


if __name__ == "__main__":
    unittest.main()

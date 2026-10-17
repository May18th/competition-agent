"""Conservative cross-artifact checks for explicitly labelled project facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Mapping


@dataclass(frozen=True)
class Fact:
    label: str
    value: float
    unit: str
    source: str
    excerpt: str


@dataclass(frozen=True)
class Issue:
    code: str
    label: str
    message: str
    facts: tuple[Fact, ...]

    def to_dict(self) -> dict:
        return {"code": self.code, "label": self.label, "message": self.message,
                "facts": [asdict(fact) for fact in self.facts]}


# Each pattern is deliberately label-led; arbitrary numerals are never facts.
_LABELS = (
    ("accuracy", r"(?:准确率|识别率|正确率)"),
    ("team_size", r"(?:团队人数|团队规模|团队共|团队由|团队成员(?:共|有)?|成员人数)"),
    ("pilot_count", r"试点(?:数量|规模|覆盖)?"),
    ("deployment_count", r"(?:部署(?:数量|规模)?|服务(?:用户|客户|学校|机构)?数|覆盖(?:用户|客户|学校|机构)?数)"),
    ("unit_cost", r"(?:单(?:桶|台|件)?成本|单位成本|制造成本)"),
    ("investment", r"(?:投入|投资|融资|预算|总成本)"),
    ("annual_fee", r"(?:年费|年度订阅费|年订阅费)"),
    ("patent_count", r"(?:专利(?:数量|共|有)?|已申请专利)"),
    ("duration", r"(?:项目周期|实施周期|研发周期|试点周期|历时)"),
)
_NUMBER = re.compile(r"(?<![\w.])([+-]?\d[\d,]*(?:\.\d+)?)\s*(万|亿|千|百)?\s*(元|万元|亿元|人|名|位|桶|台|件|项|所|家|周|个月|月|天|%|％|百分比)?")


def _normalise(number: str, magnitude: str | None, unit: str | None, label: str) -> tuple[float, str]:
    value = float(number.replace(",", ""))
    if magnitude:
        value *= {"百": 100, "千": 1_000, "万": 10_000, "亿": 100_000_000}[magnitude]
    normalized_unit = unit or ("%" if label == "accuracy" and "%" in number else "")
    if normalized_unit == "万元":
        value *= 10_000
        normalized_unit = "元"
    elif normalized_unit == "亿元":
        value *= 100_000_000
        normalized_unit = "元"
    elif normalized_unit in ("％", "百分比"):
        normalized_unit = "%"
    elif normalized_unit == "个月":
        normalized_unit = "月"
    return value, normalized_unit


def extract_facts(text: str, source: str = "") -> list[Fact]:
    """Extract explicitly labelled numeric facts from plain text or Markdown."""
    if not isinstance(text, str) or not text:
        return []
    facts: list[Fact] = []
    for label, pattern in _LABELS:
        for match in re.finditer(pattern, text):
            start, end = max(0, match.start() - 12), min(len(text), match.end() + 28)
            # Prefer a value following its label so adjacent labelled facts
            # cannot borrow one another's number.
            suffix = text[match.end():min(len(text), match.end() + 20)]
            number_match = _NUMBER.search(suffix)
            window = suffix
            if number_match is None:
                prefix = text[max(0, match.start() - 12):match.start()]
                number_match = list(_NUMBER.finditer(prefix))[-1] if _NUMBER.search(prefix) else None
                window = prefix
            if not number_match:
                continue
            raw_unit = number_match.group(3)
            # Accuracy is only comparable when expressed as a percentage.
            if label == "accuracy" and raw_unit not in ("%", "％", "百分比"):
                continue
            value, unit = _normalise(number_match.group(1), number_match.group(2), raw_unit, label)
            facts.append(Fact(label, value, unit, source, text[start:min(len(text), end + 12)].strip()))
    return facts


def check_artifact_consistency(artifacts: Mapping[str, str]) -> list[Issue]:
    """Report only differing values for the same labelled fact across sources."""
    by_source = {name: extract_facts(text, name) for name, text in artifacts.items()}
    issues: list[Issue] = []
    labels = sorted({fact.label for facts in by_source.values() for fact in facts})
    for label in labels:
        groups: dict[str, list[Fact]] = {}
        for source, facts in by_source.items():
            for fact in facts:
                if fact.label == label:
                    groups.setdefault(fact.unit, []).append(fact)
        for unit, facts in groups.items():
            sources = {fact.source for fact in facts}
            values = {fact.value for fact in facts}
            if len(sources) < 2 or len(values) < 2:
                continue
            # A source with multiple values for one label is ambiguous (e.g. actual
            # result plus target); avoid presenting that as a cross-file conflict.
            if any(len({fact.value for fact in facts if fact.source == source}) > 1
                   for source in sources):
                continue
            rendered = ", ".join(f"{fact.source}={fact.value:g}{unit}" for fact in facts)
            issues.append(Issue("fact_conflict", label, f"同一事实标签在不同产物中的数值不一致：{rendered}", tuple(facts)))
    return issues


def issues_as_dicts(artifacts: Mapping[str, str]) -> list[dict]:
    """JSON-friendly form of :func:`check_artifact_consistency`."""
    return [issue.to_dict() for issue in check_artifact_consistency(artifacts)]


def check_generation_artifacts(payload: Mapping[str, object]) -> list[dict]:
    """Compare the user-facing proposal, pitch outline, and speech script."""
    artifacts = {
        "申报书": payload.get("proposal") or "",
        "PPT大纲": payload.get("ppt_outline") or "",
        "路演稿": payload.get("speech_script") or "",
    }
    return issues_as_dicts({
        name: text for name, text in artifacts.items()
        if isinstance(text, str) and text.strip()
    })

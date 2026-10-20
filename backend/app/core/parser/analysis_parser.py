from __future__ import annotations
import re
from typing import List
from backend.app.schemas.analysis import KikenFactor

class AnalysisParser:
    """Parses AI output text (primarily Markdown) into structured data."""

    SECTION_KEYS = ("OVERALL", "SUMMARY", "RISKS", "SOLUTIONS", "ADDITIONAL")
    SECTION_MARKER_PATTERN = re.compile(r"\[SECTION:(OVERALL|SUMMARY|RISKS|SOLUTIONS|ADDITIONAL)\]")

    @staticmethod
    def parse_markdown_table(markdown: str) -> List[KikenFactor]:
        """
        Finds the risk summary table in Markdown and extracts it as a list of KikenFactor.
        Target format:
        | No | リスク項目 | 危険な理由 | 重大度 | 推奨対策 |
        | --- | --- | --- | --- | --- |
        | 1 | ... | ... | ... | ... |
        """
        factors = []
        lines = markdown.splitlines()
        table_started = False

        for line in lines:
            line = line.strip()
            if not line.startswith("|") or len(line.split("|")) < 6:
                continue

            # Skip header and separator rows
            if "リスク項目" in line or "---" in line:
                if "リスク項目" in line:
                    table_started = True
                continue

            if not table_started:
                continue

            # Parse data row
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 6:
                try:
                    no_str = parts[1].replace(".", "")
                    no = int(no_str) if no_str.isdigit() else 0

                    severity = parts[4]
                    if severity not in ["高", "中", "低"]:
                        severity = "不明"

                    factor = KikenFactor(
                        no=no,
                        item=parts[2],
                        reason=parts[3],
                        severity=severity,
                        measures=parts[5]
                    )
                    if factor.item and factor.reason and factor.measures:
                        factors.append(factor)
                except (ValueError, IndexError):
                    continue

        return factors

    @classmethod
    def parse_sections(cls, markdown: str) -> tuple[dict[str, str], list[str]]:
        """Split section markers with the same marker semantics as the UI parser."""
        normalized = markdown.strip()
        sections = {key: "" for key in cls.SECTION_KEYS}
        matches = list(cls.SECTION_MARKER_PATTERN.finditer(normalized))
        for index, match in enumerate(matches):
            key = match.group(1)
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            content = normalized[match.end():end].strip()
            if content:
                sections[key] = f"{sections[key]}\n\n{content}".strip()
        return sections, [match.group(1) for match in matches]

    @classmethod
    def validate_complete(cls, markdown: str) -> List[KikenFactor]:
        """Require the established five-section report before display or save."""
        if not markdown or not markdown.strip():
            raise ValueError("解析結果の本文が空です。再解析してください。")

        sections, marker_order = cls.parse_sections(markdown)
        if marker_order != list(cls.SECTION_KEYS):
            missing = [key for key in cls.SECTION_KEYS if key not in marker_order]
            detail = f"（不足: {', '.join(missing)}）" if missing else ""
            raise ValueError(f"解析結果の5セクション構成が完成していません{detail}。再解析してください。")
        empty = [key for key in cls.SECTION_KEYS if not sections[key].strip()]
        if empty:
            raise ValueError(f"解析結果のセクションが空です（{', '.join(empty)}）。再解析してください。")

        factors = cls.parse_markdown_table(markdown)
        if not factors:
            raise ValueError("解析結果から危険要因を1件以上抽出できませんでした。再解析してください。")
        if len(factors) > 5:
            raise ValueError("解析結果の危険要因が上限の5件を超えています。再解析してください。")
        return factors

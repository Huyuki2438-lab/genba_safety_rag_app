from __future__ import annotations
from typing import List
from backend.app.schemas.analysis import KikenFactor

class AnalysisParser:
    """Parses AI output text (primarily Markdown) into structured data."""

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

                    factors.append(KikenFactor(
                        no=no,
                        item=parts[2],
                        reason=parts[3],
                        severity=severity,
                        measures=parts[5]
                    ))
                except (ValueError, IndexError):
                    continue

        return factors

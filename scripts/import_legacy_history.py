r"""Import old local/NAS `history` folders into shared per-record JSON and NAS photos.

Example:
  python scripts/import_legacy_history.py C:\Users\user\AppData\Local\GenbaSafetyRAGApp\history \\\\server\share\KY写真解析\history
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.history_service import history_service


def main() -> int:
    parser = argparse.ArgumentParser(description="旧historyフォルダを共通履歴へ取り込みます")
    parser.add_argument("source", nargs="+", help="analysis_history.json を含む history フォルダ")
    args = parser.parse_args()
    for value in args.source:
        source = Path(value)
        imported, skipped = history_service.import_legacy_folder(source)
        print(f"{source}: imported={imported}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

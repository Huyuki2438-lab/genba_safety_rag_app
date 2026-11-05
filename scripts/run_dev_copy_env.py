"""開発用起動: コピー.env を明示的に読み込んで別ポートでAPIを起動する。通常起動(.env)には影響しない。
使い方: .venv\Scripts\python scripts\run_dev_copy_env.py [--port 8765]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from copy_env_loader import load_copy_env  # noqa: E402

port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
if port == 8000:
    raise SystemExit("8000番は既存サーバー用のため使用できません。")
print("loaded:", load_copy_env())  # 値は出力しない
import uvicorn  # noqa: E402

from main import create_app  # noqa: E402

uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")

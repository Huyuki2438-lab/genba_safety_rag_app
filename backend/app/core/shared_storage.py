"""Publish immutable files after flushing a same-directory temporary file."""
import os
import sys
import uuid
from pathlib import Path

class HistoryStorageUnavailable(RuntimeError):
    pass


def _is_network_path(root: Path) -> bool:
    text = str(root)
    if text.startswith("\\\\") or text.startswith("//"):
        return True
    if sys.platform == "win32" and root.drive:
        try:
            import ctypes
            DRIVE_REMOTE = 4
            return ctypes.windll.kernel32.GetDriveTypeW(root.drive + "\\") == DRIVE_REMOTE
        except Exception:
            return False
    return False


def _describe(root: Path) -> str:
    return "NAS(ネットワーク共有)" if _is_network_path(root) else "ローカルフォルダ"


def _guidance(root: Path) -> str:
    if _is_network_path(root):
        return "社内ネットワーク、NASの電源・共有名・接続・アクセス権限・空き容量を確認してください。"
    return "フォルダのパス・ドライブレターが正しいか、フォルダが存在しアクセス権限があるかを確認してください。"


def require_root(root: Path):
    kind = _describe(root)
    guidance = _guidance(root)
    try:
        if not root.is_dir():
            raise HistoryStorageUnavailable(f"{kind}が見つかりません（{root}）。{guidance}")
        with os.scandir(root) as entries:
            next(entries, None)
    except HistoryStorageUnavailable:
        raise
    except PermissionError:
        raise HistoryStorageUnavailable(f"{kind}への読み取り権限がありません（{root}）。{guidance}") from None
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise HistoryStorageUnavailable(f"{kind}に接続できません（{root}）。{guidance} 詳細: {detail}") from None


def check_writable(root: Path):
    """保存先に書き込み・削除ができるかを確認する(起動時チェック用)。"""
    kind = _describe(root)
    guidance = _guidance(root)
    probe = root / f".{uuid.uuid4().hex}.writetest"
    try:
        with probe.open("xb") as stream:
            stream.write(b"0")
    except PermissionError:
        raise HistoryStorageUnavailable(f"{kind}への書き込み権限がありません（{root}）。{guidance}") from None
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise HistoryStorageUnavailable(f"{kind}へ書き込めません（{root}）。{guidance} 詳細: {detail}") from None
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass


def publish(destination: Path, content: bytes):
    kind = _describe(destination.parent)
    guidance = _guidance(destination.parent)
    temporary = destination.parent / f".{uuid.uuid4().hex}.uploading"
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            raise FileExistsError()
        os.rename(temporary, destination)
        if destination.stat().st_size != len(content):
            raise OSError()
    except OSError as exc:
        detail = getattr(exc, "strerror", None) or str(exc)
        raise HistoryStorageUnavailable(f"{kind}へ保存できません（{destination.parent}）。{guidance} 詳細: {detail}") from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

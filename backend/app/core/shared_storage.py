"""Publish immutable files after flushing a same-directory temporary file."""
import os
import uuid
from pathlib import Path

class HistoryStorageUnavailable(RuntimeError):
    pass

def require_root(root: Path):
    try:
        if not root.is_dir():
            raise OSError()
        with os.scandir(root) as entries:
            next(entries, None)
    except OSError:
        raise HistoryStorageUnavailable("共有フォルダに接続できません。社内ネットワーク、NASの接続・権限・空き容量を確認してください。") from None

def publish(destination: Path, content: bytes):
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
    except OSError:
        raise HistoryStorageUnavailable("共有フォルダに接続できません。社内ネットワーク、NASの接続・権限・空き容量を確認してください。") from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

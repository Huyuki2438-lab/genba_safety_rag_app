"""Isolated SMB test; never touches application data or credentials."""
from pathlib import Path
import concurrent.futures
import json
import shutil
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.test_shared_storage import write_batch
from backend.app.repositories.history_repository import HistoryRepository
from backend.app.core.shared_storage import publish, HistoryStorageUnavailable

if __name__ == '__main__':
    share=Path(r'\\landisk-ee6245\disk1')
    root=share/('__KY_distribution_test_'+uuid.uuid4().hex)
    resolved=root.resolve()
    assert resolved.parent == share.resolve() and resolved.name.startswith('__KY_distribution_test_')
    root.mkdir()
    result={}
    try:
        data=root/'日本語 空白'/'data';data.mkdir(parents=True)
        repo=HistoryRepository(data,'001');repo.initialize_schema()
        started=time.monotonic()
        with concurrent.futures.ProcessPoolExecutor(2) as pool:
            counts=list(pool.map(write_batch,[str(data)]*2,[15,15]))
        result['concurrent_records']=sum(counts)
        result['read_from_other_process_repository']=len(HistoryRepository(data,'001').list())
        result['elapsed_seconds']=round(time.monotonic()-started,2)
        assert result['concurrent_records']==result['read_from_other_process_repository']==30
        publish(data/'images'/f'{uuid.uuid4()}.png',b'test fixture')
        publish(data/'reports'/f'{uuid.uuid4()}.pdf',b'test fixture')
        publish(data/'export'/f'{uuid.uuid4()}.zip',b'test fixture')
        result['uuid_assets']=True
        (data/'records'/'incomplete.uploading').write_text('{')
        (data/'records'/'broken.json').write_text('{')
        assert len(repo.list())==30
        result['incomplete_corrupt_ignored']=True
        records=data/'records';offline=data/'records-offline';records.rename(offline)
        try:
            repo.list()
            raise AssertionError('missing folder accepted')
        except HistoryStorageUnavailable:
            result['missing_folder_failure']=True
        offline.rename(records)
        assert len(repo.list())==30
        result['reconnect']=True
    finally:
        # Resolve again immediately before recursive removal and restrict to
        # this run's unique scratch folder directly under the known share.
        assert root.resolve()==resolved and resolved.parent==share.resolve()
        shutil.rmtree(resolved)
    out=Path(__file__).resolve().parents[1]/'tmp/real-nas-results.json'
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

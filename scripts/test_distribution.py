"""Portable EXE integration tests. Uses an isolated copy; never alters deployed config."""
import base64
import concurrent.futures
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid
import zlib
from pathlib import Path
from dotenv import dotenv_values
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tmp" / ("portable_test_" + uuid.uuid4().hex[:8])
BASE.mkdir(parents=True)
SHARED = BASE / "共有 日本語 空白" / "data"
for part in ("records", "images", "reports", "export"):
    (SHARED / part).mkdir(parents=True)
SOURCE = ROOT / "dist" / "02_各PCへ配置" / "KY安全管理"
KEY = dotenv_values(SOURCE / "secrets.env")["GEMINI_API_KEY"]
RESULTS = []
PROCESSES = []

def check(name, condition):
    if not condition:
        raise AssertionError(name)
    RESULTS.append(name)
    print("PASS:", name, flush=True)

def call(port, path, data=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body,
        headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            content = r.read()
            check_secret(content)
            return r.status, content, dict(r.headers)
    except urllib.error.HTTPError as e:
        content = e.read(); check_secret(content)
        return e.code, content, dict(e.headers)

def check_secret(content):
    if KEY.encode() in content:
        raise AssertionError("secret was present; value suppressed")

def png():
    def chunk(kind, content):
        return struct.pack('!I',len(content))+kind+content+struct.pack('!I', zlib.crc32(kind+content)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',64,64,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x88\xaa\xcc'*64)*64))+chunk(b'IEND',b'')

def rename_fixture(source, target):
    # Windows may briefly hold a photo handle after an HTTP image response.
    # Retry only a transient OS access denial; never overwrite a recreated root.
    deadline = time.monotonic() + 10
    while True:
        try:
            source.rename(target)
            return
        except PermissionError:
            if target.exists() or time.monotonic() >= deadline:
                raise
            time.sleep(0.1)

def launch(index):
    folder = BASE / f"PC-{index}"
    shutil.copytree(SOURCE, folder)
    (folder / "config.json").write_text(json.dumps({"project_id":"001","project_name":"テスト現場","data_root":str(SHARED)},ensure_ascii=False),encoding="utf-8")
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("PYTHON", "GEMINI", "VERTEX", "KY_")):
            env.pop(key)
    env.update(PATH=str(Path(os.environ['SystemRoot'])/'System32'), LOCALAPPDATA=str(BASE/f"local-{index}"),
               KY_NO_BROWSER="1", KY_CONTROL_PORT=str(53180+index), TEMP=str(BASE), TMP=str(BASE))
    process = subprocess.Popen([str(folder / "KY安全管理.exe")], cwd=folder, env=env,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    PROCESSES.append(process)
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        for log in (BASE/f"local-{index}"/"KY安全管理"/"logs").glob("*.log"):
            content=log.read_text(encoding="utf-8"); check_secret(content.encode())
            found=re.search(r"local port (\d+)",content)
            if found:
                return process, int(found.group(1)), folder, env
        if process.poll() is not None:
            raise AssertionError("EXE exited before startup")
        time.sleep(.25)
    raise AssertionError("EXE startup timeout")

if __name__ == "__main__":
    ports=[]
    try:
        first, a, folder, env = launch(1); ports.append(a)
        second, b, _, _ = launch(2); ports.append(b)
        check("two isolated EXEs start without Python/Node on PATH",call(a,"/")[0]==200 and call(b,"/")[0]==200)
        check("secrets.env enables primary AI target",json.loads(call(a,"/api/v1/settings")[1])["targets"][0]["enabled"])
        duplicate=subprocess.Popen([str(folder / "KY安全管理.exe")],cwd=folder,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
        check("duplicate launch exits",duplicate.wait(timeout=45)==0 and first.poll() is None)
        fixture=png(); (BASE/"fixture.png").write_bytes(fixture)
        payload={"imageName":"試験 写真.png","imageMimeType":"image/png","imageBase64":base64.b64encode(fixture).decode(),
                 "mode":"gemini_a","providerDisplayLabel":"KY","model":"test","markdown":"## 危険予知\n\n| 危険 | 重大度 | 対策 |\n| --- | --- | --- |\n| 重機接触 | 高 | 立入禁止・誘導員配置 |",
                 "siteName":"テスト現場","workContent":"掘削","mainRisk":"重機接触"}
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            saved=list(pool.map(lambda port: call(port,"/api/v1/history",payload), [a,b]))
        check("simultaneous saves succeed",all(r[0]==201 for r in saved))
        ids=[json.loads(r[1])["id"] for r in saved]
        check("UUID filenames do not collide",ids[0]!=ids[1] and len(list((SHARED/"records").rglob("*.json")))==2)
        check("PC B reads PC A history",ids[0] in [x['id'] for x in json.loads(call(b,"/api/v1/history")[1])['history']])
        check("shared photo readable",call(b,json.loads(saved[0][1])['imageUrl'])[0]==200)
        html='<h1>現場安全 危険分析レポート</h1><p>テスト現場　掘削作業</p><img width="160" src="data:image/png;base64,'+payload['imageBase64']+'"><table><tr><th>危険</th><th>重大度</th><th>対策</th></tr><tr><td>重機接触</td><td>高</td><td>立入禁止・誘導員配置</td></tr></table>'
        pdf=call(a,"/api/v1/pdf",{"record_id":ids[0],"context":{"title":"検証レポート","body_html":html}})
        check("PDF generated and saved to NAS folder",pdf[0]==200 and pdf[1].startswith(b'%PDF') and len(list((SHARED/'reports').rglob('*.pdf')))==1)
        (BASE/'verified.pdf').write_bytes(pdf[1])
        report_list=json.loads(call(b,f'/api/v1/history/{ids[0]}/reports')[1])['reports']
        check("PC B reads shared PDF",bool(report_list) and call(b,report_list[0]['url'])[0]==200)
        exported=call(b,f'/api/v1/history/{ids[0]}/export',{})
        check("export ZIP shared",exported[0]==200 and exported[1].startswith(b'PK') and len(list((SHARED/'export').glob('*.zip')))==1)
        (SHARED/'records'/'broken.json').write_text('{')
        (SHARED/'records'/'partial.uploading').write_text('{')
        check("corrupt and incomplete JSON skipped",len(json.loads(call(b,'/api/v1/history')[1])['history'])==2)
        old=SHARED.parent/'offline'; rename_fixture(SHARED, old)
        check("NAS disconnect reports failure",call(a,'/api/v1/history')[0]==503 and call(a,'/api/v1/history',payload)[0]==503)
        rename_fixture(old, SHARED)
        check("NAS reconnect works without restart",call(a,'/api/v1/history')[0]==200)
        photo=SHARED/'images'/json.loads(next((SHARED/'records').rglob('*.json')).read_text(encoding='utf-8'))['analysis']['photo_relative_path'] if False else next((SHARED/'images').rglob('*.png'))
        saved_photo=photo.read_bytes(); photo.unlink()
        check("missing photo does not hide history",len(json.loads(call(a,'/api/v1/history')[1])['history'])==2)
        photo.write_bytes(saved_photo)
        actual_pdf=next((SHARED/'reports').rglob('*.pdf')); actual_pdf.unlink()
        check("missing PDF is a readable error",call(b,report_list[0]['url'])[0]==404)
        actual_pdf.write_bytes(pdf[1])
        if '--live-ai' in sys.argv:
            ai={"target":"gemini_a","image_base64":payload['imageBase64'],"image_mime_type":"image/png"}
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                analyzed=list(pool.map(lambda port:call(port,'/api/v1/analyze',ai),[a,b]))
            check("two simultaneous real Gemini API calls",all(r[0]==200 and json.loads(r[1]).get('markdown') for r in analyzed))
        # Headless Edge fallback because the in-app Browser is unavailable.
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            try:
                page=browser.new_page(viewport={"width":1440,"height":1000})
                page.goto(f'http://127.0.0.1:{b}/')
                page.get_by_role('button',name='履歴',exact=True).click()
                page.get_by_role('button',name='検索',exact=True).click()
                page.get_by_role('cell',name='テスト現場',exact=True).first.wait_for()
                page.get_by_role('cell',name='テスト現場',exact=True).first.click()
                page.get_by_role('heading',name='履歴詳細',exact=True).wait_for()
                check('history table remains visible with detail open', page.locator('.history-table-wrap').evaluate('(e) => e.clientHeight') > 100)
                page.screenshot(path=str(BASE/'history.png'),full_page=True)
                page.get_by_role('button',name='KY作成画面で再表示',exact=True).click()
                page.get_by_role('button',name='履歴',exact=True).wait_for()
                check('history detail and reopen UI', '重機接触' in page.locator('body').inner_text())
                check_secret(page.content().encode())
                page.screenshot(path=str(BASE/'main.png'),full_page=True)
                with page.expect_download() as download:
                    page.get_by_role('button',name='PDFとして保存',exact=True).click()
                download.value.save_as(str(BASE/'ui-download.pdf'))
                check('PDF button downloads saved shared report', (BASE/'ui-download.pdf').read_bytes().startswith(b'%PDF'))
                ai_calls=[]
                def mock_ai(route):
                    ai_calls.append(1)
                    route.fulfill(json={"markdown": payload['markdown']})
                page.route('**/api/v1/analyze',mock_ai)
                page.locator('input[type=file]').set_input_files(str(BASE/'fixture.png'))
                page.route('**/api/v1/history', lambda route: route.fulfill(status=503, json={'detail':'共有フォルダに接続できません。'}))
                page.get_by_role('button',name='危険分析を開始',exact=True).click()
                page.get_by_role('button',name='分析結果の保存を再試行',exact=True).wait_for()
                check('failed save retains result and offers retry', '重機接触' in page.locator('body').inner_text())
                page.unroute('**/api/v1/history')
                with page.expect_response(lambda r: r.url.endswith('/api/v1/history') and r.request.method == 'POST' and r.status == 201):
                    page.get_by_role('button',name='分析結果の保存を再試行',exact=True).click()
                page.get_by_role('button',name='分析結果の保存を再試行',exact=True).wait_for(state='hidden')
                check('save retry succeeds without another AI call', len(ai_calls)==1 and len(json.loads(call(a,'/api/v1/history')[1])['history'])==3)

            finally:
                browser.close()
        old_data=ROOT/'dist/01_NASへ配置/KY安全管理/001_芝原改良工事/data'
        shutil.copytree(old_data,SHARED,dirs_exist_ok=True)
        legacy=json.loads(next((old_data/'records').rglob('*.json')).read_text(encoding='utf-8'))
        check('new EXE reads migrated existing history and PDF', call(a,f"/api/v1/history/{legacy['record_id']}")[0]==200 and len(json.loads(call(b,f"/api/v1/history/{legacy['record_id']}/reports")[1])['reports'])==1)
        for port in ports: check('shutdown response',call(port,'/api/v1/shutdown',{})[0]==200)
        check('both EXE processes exit',all(p.wait(timeout=110)==0 for p in PROCESSES))
        check('local ports closed',all(socket.socket().connect_ex(('127.0.0.1',port))!=0 for port in ports))
        import zipfile
        for archive in (SHARED/'export').glob('*.zip'):
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist(): check_secret(z.read(name))
        for path in BASE.rglob('*'):
            if path.is_file() and path.name != 'secrets.env' and path.suffix.lower() in {'.json','.log','.html','.js','.pdf','.zip'}:
                check_secret(path.read_bytes())
        check('no secret in logs/history/PDF/export/UI',True)
    finally:
        for port in ports:
            try: call(port, '/api/v1/shutdown', {})
            except OSError: pass
        for process in PROCESSES:
            if process.poll() is None:
                try: process.wait(timeout=110)
                except subprocess.TimeoutExpired:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
        (BASE/'test-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2),encoding='utf-8')
        print('ARTIFACTS:',BASE,flush=True)

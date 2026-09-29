"""End-to-end test of the first-run "data storage setup" wizard against the real
built EXE: no config.json -> wizard endpoints -> save -> restart -> second launch
picks up the new config.json automatically. Uses an isolated copy; never touches
the deployed dist/ config or real NAS.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import time
import re
import uuid
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dist" / "02_各PCへ配置" / "KY安全管理"
BASE = ROOT / "tmp" / ("first_run_test_" + uuid.uuid4().hex[:8])
RESULTS = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    RESULTS.append(name)
    print("PASS:", name, flush=True)


def call(port, path, data=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=body,
        headers={"Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def wait_for_port(local_appdata: Path, deadline_sec=60, after_ts=0.0):
    deadline = time.monotonic() + deadline_sec
    log_dir = local_appdata / "KY安全管理" / "logs"
    while time.monotonic() < deadline:
        if log_dir.is_dir():
            logs = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            for log in logs:
                if log.stat().st_mtime < after_ts:
                    continue
                content = log.read_text(encoding="utf-8")
                found = re.search(r"local port (\d+)", content)
                if found:
                    return int(found.group(1)), log
        time.sleep(0.3)
    raise AssertionError("timed out waiting for application startup log")


def main():
    if BASE.exists():
        shutil.rmtree(BASE)
    BASE.mkdir(parents=True)
    pc = BASE / "PC-1"
    shutil.copytree(SOURCE, pc)
    (pc / "config.json").unlink(missing_ok=True)  # simulate a truly first-run PC

    local_appdata = BASE / "local-1"
    data_dir = BASE / "chosen_data_root"
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("PYTHON", "GEMINI", "VERTEX", "KY_")):
            env.pop(key)
    env.update(
        PATH=str(Path(os.environ["SystemRoot"]) / "System32"),
        LOCALAPPDATA=str(local_appdata),
        KY_NO_BROWSER="1",
        KY_CONTROL_PORT="53199",
        TEMP=str(BASE), TMP=str(BASE),
    )

    process = subprocess.Popen(
        [str(pc / "KY安全管理.exe")], cwd=pc, env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        port, log_path = wait_for_port(local_appdata)
        check("first launch without config.json starts (no crash)", process.poll() is None)

        status_code, body = call(port, "/api/v1/setup/status")
        status = json.loads(body)
        check("status reports not configured on first launch", status_code == 200 and status["configured"] is False)

        # A nonexistent folder must fail validation with the exact required message.
        missing_code, missing_body = call(port, "/api/v1/setup/validate", {"path": str(BASE / "does_not_exist")})
        missing_msg = json.loads(missing_body)["message"]
        check(
            "validating a missing folder fails with required guidance message",
            missing_code == 200 and "保存先にアクセスできません" in missing_msg,
        )

        data_dir.mkdir(parents=True)
        ok_code, ok_body = call(port, "/api/v1/setup/validate", {"path": str(data_dir)})
        ok_msg = json.loads(ok_body)["message"]
        check(
            "validating an existing writable local folder succeeds with required message",
            ok_code == 200 and ok_msg.startswith("保存先への接続を確認しました。"),
        )

        save_code, save_body = call(
            port, "/api/v1/setup/save",
            {"path": str(data_dir), "project_id": "001", "project_name": "初期設定テスト現場"},
        )
        check("saving the chosen data root succeeds", save_code == 200 and json.loads(save_body)["ok"] is True)
        saved_config = json.loads((pc / "config.json").read_text(encoding="utf-8-sig"))
        check(
            "config.json now contains the chosen data_root without any manual JSON editing",
            saved_config["data_root"] == str(data_dir) and saved_config["storage_type"] == "local"
            and saved_config["project_id"] == "001" and saved_config["project_name"] == "初期設定テスト現場",
        )

        restart_ts = time.time()
        call(port, "/api/v1/setup/restart", {})
        call(port, "/api/v1/shutdown", {})
        process.wait(timeout=150)
        check("app restarts itself (old process exits) after setup completes", process.returncode == 0)

        new_port, new_log = wait_for_port(local_appdata, after_ts=restart_ts)
        check("a new process automatically relaunches after the restart request", new_log != log_path)

        status_code2, body2 = call(new_port, "/api/v1/setup/status")
        status2 = json.loads(body2)
        check(
            "second launch auto-loads the saved storage location and skips the wizard",
            status_code2 == 200 and status2["configured"] is True and status2["reachable"] is True
            and status2["data_root"] == str(data_dir),
        )

        # Sanity: normal history save/read works against the newly configured storage.
        payload = {
            "imageName": "test.png", "imageMimeType": "image/png",
            "imageBase64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
            "mode": "vertex", "providerDisplayLabel": "KY", "model": "test",
            "markdown": "危険：テスト\n対策：テスト", "siteName": "初期設定テスト", "workContent": "テスト", "mainRisk": "テスト",
        }
        save_hist_code, save_hist_body = call(new_port, "/api/v1/history", payload)
        check("history save works immediately after first-run setup", save_hist_code == 201)
        list_code, list_body = call(new_port, "/api/v1/history")
        check(
            "saved record is readable back from the newly chosen storage",
            list_code == 200 and len(json.loads(list_body)["history"]) == 1,
        )

        # Simulate the folder becoming unreachable (e.g. NAS disconnect) and verify
        # the app reports it without crashing, matching the "reachable" contract.
        (data_dir).rename(BASE / "moved_away")
        status_code3, body3 = call(new_port, "/api/v1/setup/status")
        status3 = json.loads(body3)
        check("disconnected storage is reported as unreachable, not a crash", status_code3 == 200 and status3["reachable"] is False)
        (BASE / "moved_away").rename(data_dir)
        status_code4, body4 = call(new_port, "/api/v1/setup/status")
        check("storage becomes reachable again once restored", json.loads(body4)["reachable"] is True)

        call(new_port, "/api/v1/shutdown", {})
        time.sleep(2)
    finally:
        if process.poll() is None:
            process.kill()

    print(f"ARTIFACTS: {BASE}")
    print(f"ALL {len(RESULTS)} CHECKS PASSED")


if __name__ == "__main__":
    main()

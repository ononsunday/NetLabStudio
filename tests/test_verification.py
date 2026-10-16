import json
import time

from netlab.verification import run_verification


def test_offline_verification_checks_real_loopback_and_cleanup(tmp_path):
    original=tmp_path/"keep.txt";original.write_text("user content",encoding="utf-8")
    started=time.monotonic()
    report=run_verification(tmp_path)
    assert report["ok"],report
    assert time.monotonic()-started<45
    assert report["scope"]=="loopback_only" and not report["external_network_used"]
    assert report["summary"]=={"passed":15,"failed":0,"skipped":0,"total":15}
    assert set(c["name"] for c in report["checks"])=={"TCP","UDP","HTTPS + trusted local CA","HTTP/2","HTTP/3","WebSocket","SSH pinned host key","DNS","DOH","DOT","STUN","PCAP original fields","Core network + event snapshot","CPU execution + snapshot","SQLite initialization + reopen"}
    assert all(report["cleanup"].values())
    assert list(tmp_path.iterdir())==[original]
    assert original.read_text(encoding="utf-8")=="user content"
    json.dumps(report)


def test_offline_verification_reports_failure_without_fake_success(tmp_path,monkeypatch):
    from netlab.services import servers
    monkeypatch.setattr(servers,"echo_client",lambda *args,**kwargs:{"ok":False,"error":"injected loopback failure"})
    report=run_verification(tmp_path)
    assert not report["ok"]
    assert report["summary"]["failed"]==2
    assert all(c["status"]=="failed" for c in report["checks"] if c["name"] in {"TCP","UDP"})
    assert all(report["cleanup"].values()) and not list(tmp_path.iterdir())

import hashlib
import os

import pytest

from netlab.services.security import crypto_demo,tls_handshake_model,vpn_demo
from netlab.services.programming import discover_c_compiler,templates,run_c,run_python
from netlab.services.servers import LocalServerManager
from netlab.services.diagnostics import tcp_probe


def test_actual_key_agreement_encryption_signature():
    output = crypto_demo("真实加密测试")
    assert output["kind"]=="measured"
    assert output["sha256"]==hashlib.sha256("真实加密测试".encode()).hexdigest()
    assert output["key_agreement"]["derived_keys_match"]
    assert output["encryption"]["decrypted"]=="真实加密测试"
    assert output["encryption"]["authenticated"]
    assert output["signature"]["verified"]


def test_modified_ciphertext_and_signature_rejected():
    output = crypto_demo("tamper evidence",tamper=True)
    assert not output["encryption"]["authenticated"]
    assert output["encryption"]["decrypted"] is None
    assert not output["signature"]["verified"]


def test_each_crypto_demo_has_fresh_nonce_and_key():
    first,second = crypto_demo(),crypto_demo()
    assert first["encryption"]["nonce"]!=second["encryption"]["nonce"]
    assert first["key_agreement"]["alice_public"]!=second["key_agreement"]["alice_public"]


def test_tls_resumption_changes_handshake_state():
    full = tls_handshake_model()
    resumed = tls_handshake_model(True)
    assert full["kind"]=="simulation"
    assert any(e["kind"]=="CERTIFICATE" for e in full["events"])
    assert not any(e["kind"]=="CERTIFICATE" for e in resumed["events"])
    assert resumed["events"][0]["data"]["psk"]


def test_vpn_split_routing_and_shared_events():
    routed = vpn_demo("10.1.2.3",["10.0.0.0/8","10.1.0.0/16"])
    assert routed["route"]=="10.1.0.0/16"
    assert routed["via_tunnel"]
    assert routed["outer"]["encrypted"]
    assert routed["encryption_authenticated"]
    assert "private lab message" not in routed["outer"]["payload"]
    assert all("id" in e and "packet_id" in e for e in routed["events"])
    direct = vpn_demo("192.0.2.10",["10.0.0.0/8"])
    assert not direct["via_tunnel"] and direct["outer"] is None
    full = vpn_demo("192.0.2.10",[],full_tunnel=True,encrypted=False)
    assert full["via_tunnel"]
    assert full["outer"]["payload"]=="private lab message"


def test_vpn_ipv6_and_input_validation():
    output = vpn_demo("2001:db8:1::2",["2001:db8::/32"],source="2001:db8::1",endpoint="2001:db8:ffff::1")
    assert output["via_tunnel"]
    with pytest.raises(ValueError): vpn_demo("bad ip")
    with pytest.raises(ValueError): vpn_demo(split_prefixes=["bad prefix"])


@pytest.mark.parametrize("example",[t for t in templates() if t["language"]=="c"],ids=lambda t:t["id"])
def test_c_examples_compile_and_communicate(example):
    if not discover_c_compiler():
        pytest.skip("C 编译器属于可选组件；此环境没有 GCC/Clang")
    output = run_c(example["code"])
    assert output["ok"],output
    assert output["returncode"]==0 and output["stdout"]


def test_servers_can_stop_and_restart():
    with LocalServerManager() as manager:
        server = manager.start("tcp")
        manager.stop_all()
        assert not manager.list()
        assert not tcp_probe(server["host"],server["port"],0.1)["ok"]
        assert manager.start("tcp")["ok"]


def test_concurrent_https_servers_share_valid_certificate():
    from concurrent.futures import ThreadPoolExecutor
    from netlab.services.diagnostics import tls_probe
    with LocalServerManager() as manager,ThreadPoolExecutor(max_workers=4) as pool:
        servers = list(pool.map(lambda _:manager.start("https"),range(4)))
        assert len({s["port"] for s in servers})==4
        results = list(pool.map(lambda s:tls_probe(s["host"],s["port"],2,s["cafile"]),servers))
        assert all(r["ok"] for r in results)
        assert len(manager.list())==4
        manager.stop_all()
        assert not manager.list()


def test_tls_slow_client_cannot_block_shutdown():
    import socket,time
    with LocalServerManager() as manager:
        server = manager.start("https")
        with socket.create_connection((server["host"],server["port"]),1) as slow:
            start = time.monotonic()
            manager.stop(server["id"])
            assert time.monotonic()-start<2


@pytest.mark.skipif(os.name!="nt",reason="Windows Job Object lifecycle")
def test_code_runner_terminates_descendant_processes():
    import psutil,time
    code = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); print(p.pid,flush=True); time.sleep(120)"
    # This checks descendant cleanup after a timeout, not interpreter startup
    # speed. Allow Windows process creation under concurrent packaging load.
    output = run_python(code,timeout=3)
    assert not output["ok"]
    child_pid = int(output["stdout"].strip())
    deadline = time.monotonic()+3
    while psutil.pid_exists(child_pid) and time.monotonic()<deadline:
        time.sleep(0.02)
    assert not psutil.pid_exists(child_pid)

from __future__ import annotations

import json
import socket
import time

import pytest

from netlab.services import diagnostics, packets, programming
from netlab.services.common import host, port, timeout, url
from netlab.services.servers import LocalServerManager, echo_client, file_client, chat_client
from netlab.services.modern import http3_probe, websocket_probe, ssh_probe, ssh_local_client
from netlab.services.p2p import stun_probe


@pytest.fixture
def manager():
    with LocalServerManager() as managed:
        yield managed


@pytest.mark.parametrize("target",["127.0.0.1","::1","localhost","例子.中国"])
def test_valid_hosts(target):
    assert host(target)


@pytest.mark.parametrize("target",["; dir","127.0.0.1 & calc.exe","-n","https://localhost/","bad\nname",""])
def test_reject_command_input(target):
    with pytest.raises(ValueError):
        host(target)
    assert not diagnostics.run_probe("tcp",target)["ok"]


def test_parameter_validation():
    for number in (0,65536):
        with pytest.raises(ValueError): port(number)
    for number in (-1,100):
        with pytest.raises(ValueError): timeout(number)
    with pytest.raises(ValueError): url("file:///C:/Windows")
    with pytest.raises(ValueError): url("https://user:password@localhost")
    with pytest.raises(ValueError): echo_client("tcp","127.0.0.1",1234,seconds=100)
    with pytest.raises(ValueError): echo_client("unknown","127.0.0.1",1234)
    with pytest.raises(ValueError): chat_client("127.0.0.1",1234,"x"*65536)


@pytest.mark.parametrize("kind",["tcp","udp"])
def test_real_echo(manager,kind):
    server = manager.start(kind)
    reply = echo_client(kind,server["host"],server["port"],"真实回环通信")
    assert reply["ok"]
    assert reply["details"]["matches"]
    assert manager.events()[0]["kind"]=="measured"
    manager.stop(server["id"])
    assert not manager.list()


def test_tcp_failure_is_evidence():
    with socket.socket() as unused:
        unused.bind(("127.0.0.1",0))
        reply = diagnostics.tcp_probe("127.0.0.1",unused.getsockname()[1],0.2)
    assert not reply["ok"]
    assert reply["error"] and reply["details"]=={}


def test_timeout_is_not_fake_success(manager):
    server = manager.start("chat")
    with socket.create_connection((server["host"],server["port"]),0.5) as connection:
        connection.settimeout(0.05)
        with pytest.raises(socket.timeout): connection.recv(10)


def test_local_http(manager):
    server = manager.start("http")
    reply = diagnostics.http_probe(server["url"],method="POST",body="中文请求")
    assert reply["ok"]
    details = reply["details"]
    assert details["status"]==200
    assert json.loads(details["body_preview"])["body"]=="中文请求"
    assert details["http_version"]=="HTTP/1.1"
    website = diagnostics.website_probe(server["url"])
    assert website["ok"]
    assert all(stage["kind"]=="measured" for stage in website["stages"])


def test_tls_trust_and_certificate(manager):
    server = manager.start("https")
    untrusted = diagnostics.tls_probe(server["host"],server["port"],1)
    assert not untrusted["ok"]
    trusted = diagnostics.tls_probe(server["host"],server["port"],1,server["cafile"])
    assert trusted["ok"]
    assert trusted["details"]["certificate_verified"]
    assert trusted["details"]["tls_version"] in {"TLSv1.2","TLSv1.3"}
    assert trusted["details"]["leaf_certificate_details"]["ip_addresses"]==["127.0.0.1","::1"]
    assert trusted["details"]["trust_context"]["source"]=="explicit_CA_pem"
    if trusted["details"]["verified_chain_available"]:
        assert trusted["details"]["verified_chain"][0]["subject"]==trusted["details"]["leaf_certificate_details"]["subject"]
    response = diagnostics.http_probe(server["url"],cafile=server["cafile"])
    assert response["ok"]
    assert response["details"]["status"]==200


def test_file_and_chat(manager):
    transfer = manager.start("file")
    reply = file_client(transfer["host"],transfer["port"],b"binary\0payload"*4096)
    assert reply["ok"] and reply["details"]["verified"]
    chat = manager.start("chat")
    reply = chat_client(chat["host"],chat["port"],"hello peers")
    assert reply["ok"] and reply["details"]["received"]=="hello peers"


def test_chat_broadcast_two_clients(manager):
    chat = manager.start("chat")
    with socket.create_connection((chat["host"],chat["port"]),2) as first, socket.create_connection((chat["host"],chat["port"]),2) as second:
        # Wait for both accepted connections rather than assume thread scheduling.
        server = manager._servers[chat["id"]]["server"]
        end = time.monotonic()+2
        while len(server.clients)<2 and time.monotonic()<end: time.sleep(0.01)
        first.sendall(b"one\n")
        assert first.recv(100)==b"one\n"
        assert second.recv(100)==b"one\n"


def test_loopback_scope(manager):
    with pytest.raises(ValueError): manager.start("tcp","0.0.0.0")
    with pytest.raises(ValueError): manager.start("http","192.0.2.1")


def test_dns_udp_fixture(manager):
    server = manager.start("dns")
    response = diagnostics.dns_probe("lab.local","A",1,server["host"],server["port"])
    assert response["ok"] and response["details"]["records"]==["127.0.0.1"]
    assert response["details"]["ttl"]==60
    response6 = diagnostics.dns_probe("lab.local","AAAA",1,server["host"],server["port"])
    assert response6["ok"] and response6["details"]["records"]==["::1"]
    service = diagnostics.dns_probe("_minecraft._tcp.lab.local","SRV",1,server["host"],server["port"])
    assert service["ok"] and "25565" in service["details"]["records"][0]
    failure = diagnostics.dns_probe("missing.local","A",1,server["host"],server["port"])
    assert not failure["ok"] and "NXDOMAIN" in failure["error"]


@pytest.mark.parametrize("mode",["doh","dot"])
def test_encrypted_dns_fixture(manager,mode):
    server = manager.start(mode)
    reply = diagnostics.encrypted_dns("lab.local",mode,server["url"],seconds=2,cafile=server["cafile"])
    assert reply["ok"],reply
    assert "127.0.0.1" in reply["details"]["answers"][0]
    assert reply["details"]["certificate_verified"]


def test_websocket_fixture(manager):
    server = manager.start("websocket")
    reply = websocket_probe(server["url"],"真实 WebSocket")
    assert reply["ok"] and reply["details"]["matches"]


def test_actual_http3_tls13(manager):
    server = manager.start("http3")
    reply = http3_probe(server["url"],3,server["cafile"])
    assert reply["ok"],reply
    assert reply["details"]["headers"][":status"]=="200"
    assert reply["details"]["http_version"]=="HTTP/3"
    assert reply["details"]["alpn"]=="h3"
    assert json.loads(reply["details"]["body_preview"])["kind"]=="measured"


def test_actual_http2_after_deadline_transport(manager):
    server=manager.start("http2")
    reply=diagnostics.http_probe(server["url"],cafile=server["cafile"])
    assert reply["ok"],reply
    assert reply["details"]["http_version"]=="HTTP/2"
    assert json.loads(reply["details"]["body_preview"])["service"]=="NetLab HTTP/2"
    body="multiple DATA frames "*1100
    reply=diagnostics.http_probe(server["url"],method="POST",body=body,cafile=server["cafile"])
    assert reply["ok"],reply
    assert json.loads(reply["details"]["body_preview"])["body"]==body


def test_actual_ssh_pinned_host_key(manager):
    server = manager.start("ssh")
    observed = ssh_probe(server["host"],server["port"],3)
    assert observed["ok"],observed
    assert not observed["details"]["identity_verified"]
    response = ssh_local_client(server["host"],server["port"],server["trusted_public_key"],3)
    assert response["ok"],response
    assert response["details"]["host_key_verified"]
    assert "NetLab" in response["details"]["stdout"]


def test_stun_fixture(manager):
    server = manager.start("stun")
    response = stun_probe(server["host"],server["port"],1)
    assert response["ok"],response
    assert response["details"]["mapped"]["address"]=="127.0.0.1"
    assert response["details"]["mapped"]["port"]==response["details"]["local"][1]


def test_latency_is_connection_failure_rate(manager):
    server = manager.start("tcp")
    response = diagnostics.latency_probe(server["host"],server["port"],3,1)
    assert response["ok"] and response["failure_percent"]==0
    assert len(response["samples"])==3


def test_code_runner_exceptions_timeout_and_output():
    assert programming.run_python("print('hello')")["stdout"].strip()=="hello"
    failed = programming.run_python("raise RuntimeError('expected')")
    assert not failed["ok"] and "expected" in failed["stderr"]
    timed = programming.run_python("while True: pass",timeout=0.1)
    assert not timed["ok"] and "时间" in timed["error"]
    output = programming.run_python("while True: print('x' * 65536)")
    assert not output["ok"] and "输出" in output["error"]


@pytest.mark.parametrize("example",[t for t in programming.templates() if t["language"]=="python"],ids=lambda t:t["id"])
def test_all_python_templates_actually_run(example):
    response = programming.run_python(example["code"],timeout=5)
    assert response["ok"],response
    assert response["stdout"]


def test_pcaps_offline_and_filter(tmp_path):
    from scapy.all import Ether,IP,IPv6,TCP,UDP,DNS,DNSQR,Raw,wrpcap
    from scapy.utils import PcapNgWriter
    ethernet = Ether(src="02:00:00:00:00:01",dst="02:00:00:00:00:02")
    traffic = [ethernet/IP(src="192.0.2.1",dst="192.0.2.2")/TCP(sport=1234,dport=80,flags="S",seq=100),
               ethernet/IP(src="192.0.2.2",dst="192.0.2.1")/TCP(sport=80,dport=1234,flags="SA",seq=500,ack=101),
               ethernet/IPv6(src="2001:db8::1",dst="2001:db8::2")/UDP(sport=53000,dport=53)/DNS(qd=DNSQR(qname="lab.local"))]
    pcap = tmp_path/"example.pcap"
    wrpcap(str(pcap),traffic)
    analysis = packets.read_capture(pcap)
    assert analysis["data_source"]=="pcap_import"
    assert all(row["data_source"]=="pcap_import" for row in analysis["packets"])
    assert analysis["statistics"]["packet_count"]==3
    assert len(analysis["flows"])==1
    assert len(analysis["flows"][0]["packets"])==2
    assert all(event["data_source"]=="pcap_import" and "导入文件字段" in event["explanation"] and "实测" not in event["explanation"] for event in analysis["flows"][0]["events"])
    assert analysis["packets"][0]["hex"]==bytes(traffic[0]).hex()
    assert packets.read_capture(pcap,"DNS")["statistics"]["packet_count"]==1
    assert packets.read_capture(pcap,"IPv6")["packets"][0]["source"]=="2001:db8::1"
    json.dumps(analysis)
    pcapng = tmp_path/"example.pcapng"
    with PcapNgWriter(str(pcapng)) as writer: writer.write(traffic)
    assert packets.read_capture(pcapng)["statistics"]["packet_count"]==3
    truncated = packets.read_capture(pcap,max_packets="1")
    assert truncated["truncated"] and len(truncated["packets"])==1
    path = tmp_path/"packets.csv"
    assert packets.export_csv(analysis,path)["rows"]==3
    assert "TCP" in path.read_text(encoding="utf-8-sig")
    virtual = packets.parse_virtual_frame(bytes(traffic[0]))
    assert virtual["kind"]=="simulation"
    assert virtual["data_source"]=="virtual_frame"


def test_pcap_first_import_in_fresh_process():
    import subprocess,sys
    from pathlib import Path
    project=Path(__file__).resolve().parents[1]
    code="""import json,sys
from netlab.services.packets import read_capture
assert 'scapy.all' not in sys.modules
result=read_capture('examples/captures/teaching.pcap')
assert 'scapy.all' not in sys.modules
print(json.dumps({'packets':len(result['packets']),'protocols':result['statistics']['protocols'],'flows':len(result['flows']),'ethernet':all('Ether' in p['protocols'] for p in result['packets']),'source':result['data_source'],'first_tcp':next(p['tcp'] for p in result['packets'] if 'tcp' in p)}))
"""
    child=subprocess.run([sys.executable,"-X","utf8","-c",code],cwd=project,capture_output=True,text=True,encoding="utf-8",timeout=15,
                         creationflags=0x08000000 if sys.platform=="win32" else 0)
    assert child.returncode==0,child.stderr
    result=json.loads(child.stdout)
    assert result["packets"]==15 and result["ethernet"]
    assert result["flows"]>=1 and result["protocols"].get("TCP",0)>=3
    assert result["source"]=="pcap_import" and result["first_tcp"]["flags"]=="S"
    assert "unknown LL type" not in child.stderr


def test_capture_graceful_capability(monkeypatch):
    monkeypatch.setattr(packets,"capability",lambda:{"available":False,"offline_available":True,"error":"no driver"})
    response = packets.capture("interface")
    assert not response["ok"] and response["error"]=="no driver"
    assert response["data_source"]=="live_capture"


def test_tcp_payload_excludes_ethernet_padding_and_ipv6_extensions():
    from scapy.all import Ether,IP,IPv6,TCP,Raw
    from scapy.layers.inet6 import IPv6ExtHdrHopByHop
    base=Ether(src="02:00:00:00:00:01",dst="02:00:00:00:00:02")/IP(src="192.0.2.1",dst="192.0.2.2")/TCP(flags="S")
    padded=Ether(bytes(base)+b"\x00"*6)
    assert len(bytes(padded))==60
    assert packets.parse_packet(padded)["tcp"]["payload_length"]==0
    short=Ether(bytes(base/Raw(b"x"))+b"\x00"*5)
    assert packets.parse_packet(short)["tcp"]["payload_length"]==1
    ipv6=Ether(src="02:00:00:00:00:01",dst="02:00:00:00:00:02")/IPv6(src="2001:db8::1",dst="2001:db8::2")/IPv6ExtHdrHopByHop()/TCP(flags="PA")/Raw(b"sample")
    assert packets.parse_packet(Ether(bytes(ipv6)))["tcp"]["payload_length"]==6


def test_closing_all_servers_closes_ports():
    manager = LocalServerManager()
    servers = [manager.start("tcp"),manager.start("http"),manager.start("websocket")]
    manager.close()
    assert manager.list()==[]
    for server in servers:
        assert not diagnostics.tcp_probe(server["host"],server["port"],0.1)["ok"]


def test_command_cancel_and_partial_output():
    import sys,threading
    from netlab.services.common import command
    output=command([sys.executable,"-u","-c","import time; print('partial evidence',flush=True); time.sleep(10)"],0.4)
    assert not output["ok"] and output["partial"]
    assert "partial evidence" in output["stdout"]
    cancellation=threading.Event();cancellation.set()
    cancelled=command([sys.executable,"-c","import time; time.sleep(10)"],5,cancellation)
    assert not cancelled["ok"] and cancelled["cancelled"]


def test_ping_total_budget_preserves_measured_partial_reply():
    import os
    if os.name!="nt":pytest.skip("Windows ping interval")
    started=time.monotonic()
    output=diagnostics.ping("127.0.0.1",count=50,seconds=10,overall_budget=0.4)
    assert time.monotonic()-started<2
    assert not output["complete"] and not output["ok"]
    assert output["details"]["requested_count"]==50
    assert output["details"]["sent"] is None
    assert output["details"]["stdout"]


def test_compound_probe_budget_and_cancellation(manager):
    import threading
    server=manager.start("tcp")
    cancelled=threading.Event();cancelled.set()
    result=diagnostics.latency_probe(server["host"],server["port"],50,10,cancel_event=cancelled)
    assert not result["ok"] and not result["complete"]
    assert result["samples"]==[] and result["completed_count"]==0
    result=diagnostics.website_probe("http://127.0.0.1:%d/"%server["port"],cancel_event=cancelled)
    assert not result["ok"] and not result["complete"]


def test_diagnose_total_budget_returns_partial_evidence():
    started=time.monotonic()
    output=diagnostics.run_probe("diagnose","http://127.0.0.1:9/",timeout=10,overall_budget=0.05)
    assert time.monotonic()-started<3
    assert not output["ok"] and output.get("complete") is False
    assert output["checks"] and output["checks"][0]["operation"]=="适配器与地址"
    assert output["error"]


def test_http_whole_deadline_stops_slow_body():
    import http.server,threading
    class Slow(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header("Content-Length","100");self.end_headers()
            try:
                for _ in range(100):
                    self.wfile.write(b"x");self.wfile.flush();time.sleep(0.04)
            except OSError:pass
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Slow)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        started=time.monotonic()
        response=diagnostics.http_probe("http://127.0.0.1:%d/"%server.server_port,seconds=0.2)
        assert not response["ok"]
        assert time.monotonic()-started<1
        assert "time" in response["error"].lower() or "时间" in response["error"]
    finally:
        server.shutdown();server.server_close();thread.join(2)

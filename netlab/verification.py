"""Offline release checks which run unchanged from source or a packaged EXE.

All servers bind 127.0.0.1. DNS requests go to the ephemeral local resolver.
PCAP frames are generated fixtures, never sent. No real adapter is captured.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import sys


def run_verification(workdir: Path | None=None) -> dict:
    """Return JSON evidence, clean up all owned resources, target <45 seconds."""
    started=time.monotonic()
    deadline=started+43  # Leave two seconds for ordinary loopback cleanup.
    checks=[]
    report={"ok":False,"kind":"measured","mode":"local_verification","data_source":"local_verification",
            "scope":"loopback_only","external_network_used":False,"checks":checks,
            "cleanup":{"servers_closed":False,"temporary_files_removed":False}}
    temporary=None
    manager=None

    def seconds():
        remaining=deadline-time.monotonic()
        if remaining<0.1:raise TimeoutError("本地验证达到总时间限制")
        return min(2.0,remaining)

    def ensure(condition,message):
        if not condition:raise AssertionError(message)

    def require_probe(output):
        ensure(output.get("ok") is True,output.get("error") or "探测未成功")
        return output.get("details",{})

    def check(name,operation,source="measured",reserve=5):
        began=time.monotonic()
        if deadline-began<reserve:
            checks.append({"name":name,"ok":False,"status":"skipped","result_source":source,"error":"总时间限制不足，未开始本检查","elapsed_ms":0})
            return
        try:
            evidence=operation()
            checks.append({"name":name,"ok":True,"status":"passed","result_source":source,"evidence":evidence,"error":None,
                           "elapsed_ms":round((time.monotonic()-began)*1000,3)})
        except Exception as exc:
            checks.append({"name":name,"ok":False,"status":"failed","result_source":source,"evidence":{},
                           "error":f"{type(exc).__name__}: {exc}","elapsed_ms":round((time.monotonic()-began)*1000,3)})

    try:
        if workdir is not None:
            workdir=Path(workdir)
            workdir.mkdir(parents=True,exist_ok=True)
        temporary=tempfile.TemporaryDirectory(prefix="netlab-verify-",dir=str(workdir) if workdir is not None else None)
        directory=Path(temporary.name)
        from netlab.services.servers import LocalServerManager,echo_client
        from netlab.services.diagnostics import dns_probe,encrypted_dns,http_probe,tls_probe
        from netlab.services.modern import http3_probe,websocket_probe,ssh_local_client
        from netlab.services.p2p import stun_probe
        manager=LocalServerManager(directory)

        def echo(kind):
            server=manager.start(kind)
            try:
                details=require_probe(echo_client(kind,server["host"],server["port"],"NetLab packaged loopback",seconds()))
                ensure(details["matches"],"回显内容不匹配")
                return {"host":server["host"],"bytes":details["bytes"],"matches":True}
            finally:manager.stop(server["id"])
        for kind in ("tcp","udp"):check(kind.upper(),lambda kind=kind:echo(kind))

        def https():
            server=manager.start("https")
            try:
                tls=require_probe(tls_probe(server["host"],server["port"],seconds(),server["cafile"]))
                ensure(tls["certificate_verified"] and tls["hostname_verified"],"证书验证未成功")
                http=require_probe(http_probe(server["url"],seconds=seconds(),cafile=server["cafile"]))
                ensure(http["status"]==200,"HTTPS 状态码错误")
                return {"status":http["status"],"tls_version":tls["tls_version"],"certificate_verified":True,
                        "trust_source":tls["trust_context"]["source"],"verified_chain_available":tls["verified_chain_available"]}
            finally:manager.stop(server["id"])
        check("HTTPS + trusted local CA",https,reserve=7)

        def http2():
            server=manager.start("http2")
            try:
                details=require_probe(http_probe(server["url"],seconds=seconds(),cafile=server["cafile"]))
                ensure(details["http_version"]=="HTTP/2" and details["status"]==200,"未协商 HTTP/2")
                return {"http_version":details["http_version"],"status":details["status"]}
            finally:manager.stop(server["id"])
        check("HTTP/2",http2)

        def http3():
            server=manager.start("http3")
            try:
                details=require_probe(http3_probe(server["url"],seconds(),server["cafile"]))
                ensure(details["alpn"]=="h3" and details["headers"].get(":status")=="200","未完成 HTTP/3 响应")
                return {"http_version":details["http_version"],"alpn":details["alpn"],"status":200,"certificate_verified":details["certificate_verified"]}
            finally:manager.stop(server["id"])
        check("HTTP/3",http3,reserve=18)

        def websocket():
            server=manager.start("websocket")
            try:
                details=require_probe(websocket_probe(server["url"],"packaged WebSocket",seconds()))
                ensure(details["matches"],"WebSocket 回显内容不匹配")
                return {"matches":True}
            finally:manager.stop(server["id"])
        check("WebSocket",websocket,reserve=18)

        def ssh():
            server=manager.start("ssh")
            try:
                details=require_probe(ssh_local_client(server["host"],server["port"],server["trusted_public_key"],seconds()))
                ensure(details["host_key_verified"] and details["returncode"]==0 and "NetLab" in details["stdout"],"本机 SSH 命令未成功")
                return {"host_key_verified":True,"returncode":details["returncode"],"command":"netlab-info"}
            finally:manager.stop(server["id"])
        check("SSH pinned host key",ssh,reserve=18)

        def dns():
            server=manager.start("dns")
            try:
                details=require_probe(dns_probe("lab.local","A",seconds(),server["host"],server["port"]))
                ensure(details["records"]==["127.0.0.1"] and details["ttl"]==60,"本机 DNS 应答字段错误")
                return {"records":details["records"],"ttl":details["ttl"],"resolver_host":server["host"]}
            finally:manager.stop(server["id"])
        check("DNS",dns)

        def encrypted(mode):
            server=manager.start(mode)
            try:
                details=require_probe(encrypted_dns("lab.local",mode,server["url"],seconds=seconds(),cafile=server["cafile"]))
                ensure(details["certificate_verified"] and any("127.0.0.1" in answer for answer in details["answers"]),"加密 DNS 未返回预期应答")
                return {"transport":details["transport"],"certificate_verified":True,"answers":details["answers"]}
            finally:manager.stop(server["id"])
        for mode in ("doh","dot"):check(mode.upper(),lambda mode=mode:encrypted(mode))

        def stun():
            server=manager.start("stun")
            try:
                details=require_probe(stun_probe(server["host"],server["port"],seconds()))
                ensure(details["mapped"]["address"]=="127.0.0.1" and details["mapped"]["port"]==details["local"][1],"STUN 回环映射字段错误")
                return {"mapped_address":details["mapped"]["address"],"mapped_port_matches_local":True}
            finally:manager.stop(server["id"])
        check("STUN",stun)

        def pcap():
            from scapy.all import Ether,IP,TCP,Raw,wrpcap
            from netlab.services.packets import read_capture,parse_virtual_frame
            # Explicit MACs prevent Scapy from resolving a neighbor or sending traffic.
            frame=Ether(src="02:00:00:00:00:01",dst="02:00:00:00:00:02")/IP(src="192.0.2.1",dst="192.0.2.2")/TCP(sport=42000,dport=80,seq=123,ack=456,flags="PA")/Raw(b"verification fixture")
            raw=bytes(frame)
            path=directory/"generated-fixture.pcap"
            wrpcap(str(path),[frame])
            analysis=read_capture(path)
            packet=analysis["packets"][0]
            ensure(packet["hex"]==raw.hex() and packet["tcp"]["seq"]==123 and packet["tcp"]["ack"]==456,"PCAP 原始字节或 TCP 字段不匹配")
            ensure(packet["tcp"]["payload_length"]==20,"TCP 载荷长度错误")
            ensure(analysis["data_source"]=="pcap_import" and parse_virtual_frame(raw)["data_source"]=="virtual_frame","数据来源标记错误")
            return {"packet_count":analysis["statistics"]["packet_count"],"raw_bytes_match":True,"tcp_seq":123,"tcp_ack":456,
                    "source":"generated PCAP fixture, never transmitted","data_source":analysis["data_source"]}
        check("PCAP original fields",pcap,source="generated_fixture")

        def core():
            from netlab.core.subnet import analyze_network
            from netlab.core.topology import NetworkSimulator,example_topology
            from netlab.core.events import EventEngine
            network=analyze_network("192.0.2.37/24")
            ensure(network["network"]=="192.0.2.0" and network["usable_hosts"]==254,"子网计算错误")
            sim=NetworkSimulator.from_dict(example_topology())
            packet=sim.send("PC1","PC2")
            outcome=sim.run()
            ensure(sim.packets[packet]["status"]=="delivered" and any(e["kind"]=="ARP_REQUEST" for e in outcome["events"]),"虚拟 ARP/转发未成功")
            engine=EventEngine(7);engine.schedule(0.2,"later");engine.schedule(0.1,"first")
            restored=EventEngine.restore(json.loads(json.dumps(engine.snapshot())))
            ensure(restored.pop().kind=="first","模拟事件恢复或顺序错误")
            return {"network":network["network"],"usable_hosts":254,"virtual_packet_status":"delivered","ARP_events":True,"snapshot_scheduler":True}
        check("Core network + event snapshot",core,source="teaching_model")

        def cpu():
            from netlab.systems.cpu import CPU
            model=CPU();model.load("MOV R0, 7\nADD R0, 5\nSTORE 10, R0\nHALT")
            model.run(10)
            ensure(model.registers["R0"]==12 and model.memory[10]==12 and model.halted,"CPU 执行结果错误")
            restored=CPU.restore(json.loads(json.dumps(model.snapshot())))
            ensure(restored.memory[10]==12 and restored.halted,"CPU 快照恢复错误")
            return {"R0":12,"memory_10":12,"halted":True,"snapshot_restore":True}
        check("CPU execution + snapshot",cpu,source="teaching_model")

        def database():
            from netlab.storage import Database,SCHEMA_VERSION
            path=directory/"verification.sqlite3"
            with Database(path) as db:
                record_id=db.save_experiment("verification","temporary loopback verification",{"seed":7},{"kind":"measured","ok":True})
                db.set_setting("verification",{"local":True})
                version=db.connection.execute("PRAGMA user_version").fetchone()[0]
                ensure(version==SCHEMA_VERSION,"SQLite 迁移版本错误")
            with Database(path) as reopened:
                record=reopened.get_experiment(record_id)
                ensure(record["config"]["seed"]==7 and record["result"]["ok"] and reopened.get_setting("verification")=={"local":True},"SQLite 往返保存错误")
            return {"schema_version":version,"saved_and_reopened":True,"temporary_database_only":True}
        check("SQLite initialization + reopen",database,source="local_storage")

        if getattr(sys,"frozen",False):
            def bundled_python():
                from netlab.services.programming import TCP_CODE,run_python
                output=run_python(TCP_CODE,timeout=min(8.0,deadline-time.monotonic()),workdir=directory)
                ensure(output["ok"],output.get("error") or output.get("stderr") or "内置 Python 练习进程未成功")
                ensure(output["stdout"].strip()=="你好 TCP" and output["returncode"]==0,"内置 Python 的实际 TCP 回显输出错误")
                return {"stdout":output["stdout"],"stderr":output["stderr"],"returncode":output["returncode"],
                        "external_interpreter_used":False,"sandboxed":False,"scope":"loopback_only"}
            check("Python editor bundled runner",bundled_python,reserve=12)
    except Exception as exc:
        checks.append({"name":"verification setup","ok":False,"status":"failed","result_source":"local_runtime","error":f"{type(exc).__name__}: {exc}","elapsed_ms":0})
    finally:
        if manager is not None:
            try:
                manager.close();report["cleanup"]["servers_closed"]=not bool(manager.list())
            except Exception as exc:
                checks.append({"name":"server cleanup","ok":False,"status":"failed","result_source":"local_runtime","error":str(exc),"elapsed_ms":0})
        if temporary is not None:
            try:
                temporary.cleanup();report["cleanup"]["temporary_files_removed"]=not Path(temporary.name).exists()
            except Exception as exc:
                checks.append({"name":"temporary cleanup","ok":False,"status":"failed","result_source":"local_runtime","error":str(exc),"elapsed_ms":0})
    report["summary"]={"passed":sum(c["status"]=="passed" for c in checks),"failed":sum(c["status"]=="failed" for c in checks),
                       "skipped":sum(c["status"]=="skipped" for c in checks),"total":len(checks)}
    report["elapsed_ms"]=round((time.monotonic()-started)*1000,3)
    report["ok"]=bool(checks) and all(c["ok"] for c in checks) and all(report["cleanup"].values()) and report["elapsed_ms"]<45000
    return report

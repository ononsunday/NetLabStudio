"""Bounded Scapy-based offline parsing and explicitly initiated capture."""
from __future__ import annotations

import collections
import csv
import json
import os
from pathlib import Path
import time


def _json(value, depth=0):
    if depth > 6:
        return str(value)[:1000]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"hex": value[:4096].hex(), "length": len(value)}
    if isinstance(value, (list, tuple)):
        return [_json(item, depth+1) for item in value[:256]]
    if isinstance(value, dict):
        return {str(k): _json(v,depth+1) for k,v in value.items()}
    if hasattr(value, "fields"):
        return {"layer": value.name, "fields": _json(value.fields,depth+1)}
    return str(value)[:4096]


def _tcp_payload_length(tcp):
    """Captured TCP application bytes, excluding padding outside IP lengths."""
    from scapy.layers.inet import IP
    from scapy.layers.inet6 import IPv6
    from scapy.packet import Padding
    captured=len(bytes(tcp.payload))
    if Padding in tcp.payload:
        captured-=len(bytes(tcp.payload[Padding]))
    if tcp.dataofs is None:
        return max(0,captured)
    header_length=int(tcp.dataofs)*4
    layer=tcp.underlayer
    extension_length=0
    while layer is not None:
        if isinstance(layer,IP):
            if layer.len is not None and layer.ihl is not None:
                expected=int(layer.len)-int(layer.ihl)*4-extension_length-header_length
                return max(0,min(captured,expected))
            break
        if isinstance(layer,IPv6):
            if layer.plen:
                expected=int(layer.plen)-extension_length-header_length
                return max(0,min(captured,expected))
            break
        extension_length+=len(bytes(layer))-len(bytes(layer.payload))
        layer=layer.underlayer
    return max(0,captured)


def parse_packet(packet, index=1, kind="measured") -> dict:
    from scapy.layers.inet import IP, TCP, UDP, ICMP
    from scapy.layers.inet6 import IPv6, ICMPv6Unknown
    from scapy.layers.l2 import Ether, ARP
    from scapy.layers.dns import DNS
    protocols, fields = [], []
    layer = packet
    while layer and getattr(layer, "name", "") != "NoPayload":
        protocols.append(layer.__class__.__name__)
        # Build all declared fields, not only non-default fields in .fields.
        layer_fields = {}
        for descriptor in layer.fields_desc:
            try:
                layer_fields[descriptor.name] = _json(layer.getfieldval(descriptor.name))
            except Exception as exc:
                layer_fields[descriptor.name] = {"unavailable": str(exc)}
        fields.append({"layer": layer.name, "class": layer.__class__.__name__, "fields": layer_fields})
        layer = layer.payload
    source, destination, sport, dport = "", "", None, None
    if IP in packet:
        source, destination = packet[IP].src, packet[IP].dst
    elif IPv6 in packet:
        source, destination = packet[IPv6].src, packet[IPv6].dst
    elif ARP in packet:
        source, destination = packet[ARP].psrc, packet[ARP].pdst
    elif Ether in packet:
        source, destination = packet[Ether].src, packet[Ether].dst
    protocol = "Ethernet" if Ether in packet else protocols[-1] if protocols else "Unknown"
    for cls, name in ((ARP,"ARP"),(IP,"IPv4"),(IPv6,"IPv6"),(ICMP,"ICMP"),(UDP,"UDP"),(TCP,"TCP"),(DNS,"DNS")):
        if cls in packet:
            protocol = name
    if any(name.startswith("ICMPv6") for name in protocols):
        protocol = "ICMPv6"
    transport = packet[TCP] if TCP in packet else packet[UDP] if UDP in packet else None
    if transport:
        sport, dport = int(transport.sport), int(transport.dport)
    data = bytes(packet)
    row = {"index": index, "time": float(packet.time), "source": source, "destination": destination,
           "sport": sport, "dport": dport, "protocol": protocol, "protocols": protocols, "length": len(data),
           "summary": packet.summary(), "fields": fields, "hex": data.hex(), "kind": kind}
    if TCP in packet:
        row["tcp"] = {"seq": int(packet[TCP].seq), "ack": int(packet[TCP].ack), "flags": str(packet[TCP].flags), "window": int(packet[TCP].window), "payload_length": _tcp_payload_length(packet[TCP])}
    return row


def analyze(packets: list[dict], **extra) -> dict:
    protocols = collections.Counter(p["protocol"] for p in packets)
    sources = collections.Counter(p["source"] for p in packets)
    flows = {}
    for item in packets:
        if "tcp" not in item:
            continue
        endpoints = sorted([(item["source"],item["sport"]),(item["destination"],item["dport"])])
        key = json.dumps(endpoints)
        if key not in flows:
            flows[key] = {"endpoints": endpoints, "packets": [], "bytes": 0}
        flows[key]["bytes"] += item["length"]
        flows[key]["packets"].append({k:item[k] for k in ("index","time","source","destination","tcp","kind","data_source") if k in item})
    for flow in flows.values():
        observed = set()
        initial_time = min(item["time"] for item in flow["packets"])
        flow["events"] = []
        for order,item in enumerate(flow["packets"],1):
            tcp = item["tcp"]
            flags = tcp["flags"]
            fingerprint = (item["source"],tcp["seq"],tcp["payload_length"],flags)
            repeated = fingerprint in observed and (tcp["payload_length"]>0 or "S" in flags or "F" in flags)
            observed.add(fingerprint)
            kind = "TCP_RST" if "R" in flags else "TCP_SYN_ACK" if "S" in flags and "A" in flags else "TCP_SYN" if "S" in flags else "TCP_FIN" if "F" in flags else "TCP_DATA" if tcp["payload_length"] else "TCP_ACK"
            data_source=item.get("data_source",extra.get("data_source","source_unverified"))
            description={"pcap_import":"导入文件字段（文件可能包含教学示例）", "live_capture":"授权实时抓包字段", "virtual_frame":"教学虚拟帧字段"}.get(data_source,"数据包字段（来源未核实）")
            flow["events"].append({"id":f"capture-{item['index']}","time":item["time"]-initial_time,"order":order,"kind":kind,
                                  "source":item["source"],"target":item["destination"],"packet_id":str(item["index"]),"status":"observed",
                                  "data_source":data_source,
                                  "explanation":f"{description}：seq={tcp['seq']} ack={tcp['ack']} flags={flags}"+("；观察到相同序列片段，可能为重传或重复捕获。" if repeated else ""),
                                  "data":{**tcp,"possible_retransmission":repeated,"kind":item.get("kind","measured"),"data_source":data_source}})
    span = max(p["time"] for p in packets)-min(p["time"] for p in packets) if packets else 0
    return {"ok": True, "kind": "measured", "packets": packets, "flows": list(flows.values()),
            "statistics": {"packet_count": len(packets), "total_bytes": sum(p["length"] for p in packets), "duration_seconds": span,
                           "protocols": dict(protocols), "sources": dict(sources)},
            "note": "导入文件可能来自实测或教学生成，文件导入本身不能证明本机实测。TCP 时序依据文件或授权实时抓包的片段，不保证包含完整会话；未知密钥的 HTTPS 载荷保持加密。", **extra}


def read_capture(path, protocol="", max_packets=10000) -> dict:
    max_packets = int(max_packets)
    file = Path(path)
    if not file.is_file():
        raise ValueError("请选择存在的 PCAP/PCAPNG 文件")
    if file.stat().st_size > 256*1024*1024:
        raise ValueError("单文件分析限 256 MiB；请先在抓包工具中拆分")
    if not 1 <= int(max_packets) <= 100000:
        raise ValueError("最大解析数量必须为 1–100000")
    # Register link types and their payload bindings before PcapReader chooses
    # a decoder. Importing them in parse_packet is too late for a fresh process.
    from scapy.layers import l2, inet, inet6, dns
    from scapy.utils import PcapReader
    accepted = {p.strip().upper() for p in protocol.split(",") if p.strip()}
    rows = []
    truncated = False
    with PcapReader(str(file)) as reader:
        for index, packet in enumerate(reader, 1):
            if index > max_packets:
                truncated = True
                break
            row = parse_packet(packet,index)
            row["data_source"]="pcap_import"
            if not accepted or row["protocol"].upper() in accepted or any(p.upper() in accepted for p in row["protocols"]):
                rows.append(row)
    return analyze(rows,path=str(file.resolve()),truncated=truncated,filter=protocol,data_source="pcap_import")


def capability() -> dict:
    try:
        from scapy.all import conf
        if os.name == "nt":
            system = Path(os.environ.get("WINDIR", "C:\\Windows"))/"System32"
            has_npcap = (system/"Npcap"/"wpcap.dll").exists() and (system/"drivers"/"npcap.sys").exists()
            if not has_npcap:
                return {"available": False, "offline_available": True, "interfaces": [], "error": "未检测到 Npcap DLL 与驱动；PCAP 文件分析仍可使用。"}
        interfaces = [{"name": interface.name, "description": interface.description, "network_name": interface.network_name, "index": interface.index}
                      for interface in conf.ifaces.values()]
        return {"available": bool(interfaces), "offline_available": True, "interfaces": interfaces,
                "error": None if interfaces else "没有可抓包接口", "note": "接口存在不保证当前账户有权限；只有开始授权抓包后才能确认。"}
    except Exception as exc:
        return {"available": False, "offline_available": False, "interfaces": [], "error": str(exc)}


def capture(interface, duration=3, max_packets=100, output_path=None) -> dict:
    """No discovery, no injection, explicit interface, bounded time and count."""
    state = capability()
    if not state["available"]:
        return {"ok":False,"kind":"measured","data_source":"live_capture","error":state["error"],"packets":[],"capability":state}
    if not 0.1 <= float(duration) <= 30 or not 1 <= int(max_packets) <= 10000:
        raise ValueError("抓包限 0.1–30 秒、1–10000 包")
    allowed = {str(row[key]) for row in state["interfaces"] for key in ("name", "network_name", "index")}
    if str(interface) not in allowed:
        raise ValueError("请选择已检测到的明确接口")
    try:
        from scapy.all import sniff, wrpcap
        packets = sniff(iface=interface, timeout=float(duration), count=int(max_packets), promisc=False, store=True)
        if output_path:
            wrpcap(str(output_path),packets)
        rows=[{**parse_packet(packet,index),"data_source":"live_capture"} for index,packet in enumerate(packets,1)]
        return analyze(rows,interface=str(interface),capture_seconds=duration,data_source="live_capture")
    except Exception as exc:
        return {"ok":False,"kind":"measured","data_source":"live_capture","error":f"{type(exc).__name__}: {exc}","packets":[],"capability":state}


def export_csv(analysis, path):
    columns = ("index","time","source","destination","sport","dport","protocol","length","summary")
    with Path(path).open("w",encoding="utf-8-sig",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=columns,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(analysis["packets"])
    return {"ok": True, "path": str(Path(path).resolve()), "rows": len(analysis["packets"])}


def parse_virtual_frame(data: bytes, index=1) -> dict:
    from scapy.layers.l2 import Ether
    row = parse_packet(Ether(data),index,kind="simulation")
    row["data_source"]="virtual_frame"
    row["note"] = "虚拟实验帧，仅解析字节，不向真实网卡发送。"
    return row

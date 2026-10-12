"""Read-only Windows observation. Missing privilege/hardware returns unavailable."""
from __future__ import annotations

import json
import ipaddress
import os
import socket
import time

import psutil

from .common import command


def _powershell(script: str, limit=12) -> dict:
    if limit<=0:
        return {"available":False,"kind":"measured","rows":[],"raw":"","error":"采集达到总时间限制"}
    if os.name != "nt":
        return {"available": False, "kind":"measured", "rows": [], "raw": "", "error": "此信息需要 Windows"}
    completed = command(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); " + script], limit)
    if not completed["ok"]:
        return {"available": False, "kind":"measured", "rows": [], "raw": completed["stdout"], "error": completed.get("error") or completed["stderr"]}
    raw = completed["stdout"].lstrip("\ufeff").strip()
    try:
        rows = json.loads(raw) if raw else []
        if isinstance(rows, dict):
            rows = [rows]
        return {"available": True, "kind":"measured", "rows": rows, "raw": raw, "error": None}
    except json.JSONDecodeError:
        return {"available": False, "kind":"measured", "rows": [], "raw": raw, "error": "Windows 返回的信息无法解析"}


def routes(seconds=12) -> dict:
    return _powershell("Get-NetRoute | Select-Object InterfaceAlias,DestinationPrefix,NextHop,RouteMetric,InterfaceMetric,AddressFamily,State | ConvertTo-Json -Compress",seconds)


def firewall(seconds=20) -> dict:
    return _powershell("Get-NetFirewallRule -PolicyStore ActiveStore | Select-Object -First 1000 DisplayName,Enabled,Direction,Action,Profile | ConvertTo-Json -Compress",seconds)


def wifi(seconds=10) -> dict:
    if seconds<=0:
        return {"available":False,"raw":"","fields":{},"error":"采集达到总时间限制"}
    if os.name != "nt":
        return {"available": False, "error": "此信息需要 Windows WLAN 服务", "raw": "", "fields": {}}
    res = command(["netsh.exe", "wlan", "show", "interfaces"],seconds)
    fields = {}
    for line in res["stdout"].splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fields[key.strip()] = val.strip()
    # Preserve localized names rather than guessing signal, band or SSID.
    available = res["ok"] and any(key.lower() == "ssid" for key in fields)
    normalized = {}
    aliases = {
        "ssid":("SSID",),"bssid":("AP BSSID","BSSID"),"band":("Band","频段","波段"),"channel":("Channel","频道","信道","通道"),
        "signal_percent":("Signal","信号"),"radio_type":("Radio type","无线电类型"),
        "receive_mbps":("Receive rate (Mbps)","接收速率(Mbps)","接收速率 (Mbps)"),
        "transmit_mbps":("Transmit rate (Mbps)","传输速率 (Mbps)","传输速率(Mbps)"),"state":("State","状态"),
        "rssi_dbm":("Rssi",),"authentication":("Authentication","身份验证"),"cipher":("Cipher","密码"),
    }
    for output, names in aliases.items():
        normalized[output] = next((fields[key] for key in fields if key.casefold() in {name.casefold() for name in names}),None)
    for name in ("channel","signal_percent","receive_mbps","transmit_mbps","rssi_dbm"):
        if normalized[name]:
            try:
                normalized[name] = float(normalized[name].rstrip("%"))
            except ValueError:
                pass
    return {"available": available, "raw": res["stdout"], "fields": fields,
            **normalized,
            "error": None if available else res["stderr"] or "没有已连接的无线接口，或 Windows 隐私/硬件限制阻止读取。"}


def connections() -> dict:
    rows, errors = [], []
    try:
        for item in psutil.net_connections(kind="inet"):
            try:
                process = psutil.Process(item.pid).name() if item.pid else None
            except (psutil.Error, OSError):
                process = None
            rows.append({"family": "IPv6" if item.family == socket.AF_INET6 else "IPv4",
                         "protocol": "TCP" if item.type == socket.SOCK_STREAM else "UDP",
                         "local": f"{item.laddr.ip}:{item.laddr.port}" if item.laddr else "",
                         "remote": f"{item.raddr.ip}:{item.raddr.port}" if item.raddr else "",
                         "status": item.status, "pid": item.pid, "process": process})
    except (psutil.Error, OSError) as exc:
        errors.append(str(exc))
    return {"rows": rows, "errors": errors}


def system_snapshot(include_firewall=False,seconds=45) -> dict:
    errors = []
    expires = time.monotonic()+float(seconds) if seconds is not None else None
    def remaining(maximum):
        return min(maximum,max(0,expires-time.monotonic())) if expires is not None else maximum
    settings = _powershell("Get-NetIPConfiguration | Select-Object InterfaceAlias,@{n='Gateway';e={($_.IPv4DefaultGateway.NextHop -join ',')}},@{n='GatewayV6';e={($_.IPv6DefaultGateway.NextHop -join ',')}},@{n='DNS';e={($_.DNSServer.ServerAddresses -join ',')}} | ConvertTo-Json -Compress",remaining(12))
    prefixes = _powershell("Get-NetIPAddress | Select-Object InterfaceAlias,IPAddress,PrefixLength | ConvertTo-Json -Compress",remaining(12))
    prefix_lookup = {(entry["InterfaceAlias"],entry["IPAddress"]):entry["PrefixLength"] for entry in prefixes["rows"]}
    configs = {row["InterfaceAlias"]: row for row in settings["rows"]}
    adapters = []
    counters, states = psutil.net_io_counters(pernic=True), psutil.net_if_stats()
    for name, addresses in psutil.net_if_addrs().items():
        state, counter, cfg = states.get(name), counters.get(name), configs.get(name, {})
        row = {"name": name, "status": "up" if state and state.isup else "down", "ipv4": [], "ipv6": [], "mac": None,
               "speed_mbps": state.speed if state and state.speed > 0 else None, "mtu": state.mtu if state else None,
               "sent_bytes": counter.bytes_sent if counter else None, "recv_bytes": counter.bytes_recv if counter else None,
               "gateway": cfg.get("Gateway") or None, "gateway_v6":cfg.get("GatewayV6") or None,"dns": cfg.get("DNS") or None}
        for address in addresses:
            if address.family in (socket.AF_INET, socket.AF_INET6):
                prefix_length = prefix_lookup.get((name,address.address.split("%",1)[0]))
                netmask = address.netmask
                if netmask is None and prefix_length is not None:
                    netmask = str(ipaddress.ip_network(f"{address.address.split('%',1)[0]}/{prefix_length}",strict=False).netmask)
                row["ipv4" if address.family == socket.AF_INET else "ipv6"].append({"address": address.address, "netmask": netmask, "broadcast": address.broadcast,"prefix_length":prefix_length})
            elif address.family == psutil.AF_LINK:
                row["mac"] = address.address
        adapters.append(row)
    connection_rows = connections()
    errors.extend(connection_rows["errors"])
    if not settings["available"]:
        errors.append(settings["error"])
    return {"kind": "measured", "timestamp": time.time(), "platform": os.name, "adapters": adapters,
            "connections": connection_rows["rows"], "wifi": wifi(remaining(10)), "routes": routes(remaining(12)),
            "firewall": firewall(remaining(20)) if include_firewall else {"available": False, "rows": [], "error": "按需读取"}, "errors": errors}


class RateSampler:
    """Differences in counters, with real elapsed time and reset detection."""
    def __init__(self):
        self.previous = None

    def sample(self) -> dict:
        now = time.monotonic()
        counters = psutil.net_io_counters(pernic=True)
        rows = []
        if self.previous:
            previous_time, old = self.previous
            elapsed = now-previous_time
            for name, current in counters.items():
                if name in old and elapsed > 0:
                    rows.append({"name": name, "upload_bps": max(0, current.bytes_sent-old[name].bytes_sent)*8/elapsed,
                                 "download_bps": max(0, current.bytes_recv-old[name].bytes_recv)*8/elapsed})
        self.previous = now, counters
        return {"kind": "measured", "timestamp": time.time(), "rates": rows, "initial_sample": not bool(rows)}

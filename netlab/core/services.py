"""Stateful virtual network services and isolated security teaching models."""
from __future__ import annotations

import ipaddress
import math
from dataclasses import asdict, dataclass


class DHCPServer:
    def __init__(self, network: str = "192.168.1.0/24", gateway: str = "192.168.1.1",
                 dns: str = "192.168.1.1", start: int = 100, end: int = 199, lease_seconds: int = 3600):
        self.network = ipaddress.ip_network(network, strict=False)
        if self.network.version != 4 or lease_seconds < 1:
            raise ValueError("DHCPv4 池必须为 IPv4；租约时间应为正数。")
        self.gateway, self.dns = str(ipaddress.ip_address(gateway)), str(ipaddress.ip_address(dns))
        if ipaddress.ip_address(dns).version != 4:
            raise ValueError("DHCPv4 DNS 选项应为 IPv4 地址。")
        if ipaddress.ip_address(gateway) not in self.network:
            raise ValueError("网关必须位于地址池子网内。")
        if not 1 <= start <= end < self.network.num_addresses - 1:
            raise ValueError("地址池偏移必须在可用主机范围内。")
        self.pool = [str(self.network.network_address + offset) for offset in range(start, end + 1)
                     if str(self.network.network_address + offset) != self.gateway]
        self.lease_seconds = lease_seconds
        self.leases: dict[str, dict] = {}
        self.offers: dict[str, dict] = {}

    def expire(self, now: float) -> None:
        self.leases = {mac: row for mac, row in self.leases.items() if row["expires"] > now}
        self.offers = {mac: row for mac, row in self.offers.items() if row["expires"] > now}

    def discover(self, mac: str, now: float = 0.0) -> dict:
        self.expire(now)
        if mac in self.leases:
            address = self.leases[mac]["address"]
        elif mac in self.offers:
            address = self.offers[mac]["address"]
        else:
            used = {row["address"] for row in [*self.leases.values(), *self.offers.values()]}
            address = next((item for item in self.pool if item not in used), None)
            if address is None:
                raise RuntimeError("DHCP 地址池已耗尽。")
        self.offers[mac] = {"address": address, "expires": now + 60}
        return {"message": "OFFER", "address": address, "mask": str(self.network.netmask),
                "gateway": self.gateway, "dns": self.dns, "lease_seconds": self.lease_seconds}

    def request(self, mac: str, address: str, now: float = 0.0) -> dict:
        self.expire(now)
        existing = self.leases.get(mac) or self.offers.get(mac)
        if not existing or existing["address"] != address:
            return {"message": "NAK", "reason": "请求地址没有对应的有效租约或 OFFER。"}
        self.leases[mac] = {"address": address, "expires": now + self.lease_seconds}
        self.offers.pop(mac, None)
        return {"message": "ACK", **self.leases[mac], "gateway": self.gateway, "dns": self.dns,
                "mask": str(self.network.netmask), "renew_at": now + self.lease_seconds * 0.5}

    def allocate(self, mac: str, now: float = 0.0) -> dict:
        offer = self.discover(mac, now)
        lease = self.request(mac, offer["address"], now)
        return {**lease, "exchange": ["DISCOVER", "OFFER", "REQUEST", "ACK"]}


class NATTable:
    """Endpoint-independent PAT mapping plus optional inbound port forwarding."""
    def __init__(self, public_ip: str = "203.0.113.1", first_port: int = 40000, timeout: float = 120):
        self.public_ip = str(ipaddress.ip_address(public_ip))
        if ipaddress.ip_address(self.public_ip).version != 4:
            raise ValueError("当前 NAT/PAT 模型实现 NAT44，不实现 NAT64/NAT66。")
        if not 1 <= first_port <= 65535 or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("NAT 端口或超时无效。")
        self.next_port, self.timeout = first_port, timeout
        self.entries: dict[tuple, dict] = {}
        self.forwards: dict[tuple, tuple] = {}

    def outbound(self, private_ip: str, private_port: int, protocol: str = "UDP", now: float = 0) -> dict:
        private_ip = str(ipaddress.ip_address(private_ip))
        if ipaddress.ip_address(private_ip).version != 4:
            raise ValueError("NAT44 内部地址必须为 IPv4。")
        if not 1 <= private_port <= 65535:
            raise ValueError("端口必须为 1 至 65535。")
        self.expire(now)
        key = (protocol.upper(), private_ip, private_port)
        if key not in self.entries:
            occupied = {row["public_port"] for row in self.entries.values()} | {port for _, port in self.forwards}
            attempts = 0
            while self.next_port in occupied and attempts < 65535:
                self.next_port = self.next_port % 65535 + 1
                attempts += 1
            if attempts >= 65535:
                raise RuntimeError("NAT 端口空间已耗尽。")
            self.entries[key] = {"protocol": protocol.upper(), "private_ip": private_ip,
                                 "private_port": private_port, "public_ip": self.public_ip,
                                 "public_port": self.next_port, "expires": now + self.timeout}
            self.next_port = self.next_port % 65535 + 1
        self.entries[key]["expires"] = now + self.timeout
        return self.entries[key].copy()

    def inbound(self, public_port: int, protocol: str = "UDP", now: float = 0) -> dict | None:
        self.expire(now)
        forward = self.forwards.get((protocol.upper(), public_port))
        if forward:
            return {"private_ip": forward[0], "private_port": forward[1], "forward": True}
        entry = next((row for row in self.entries.values()
                      if row["protocol"] == protocol.upper() and row["public_port"] == public_port), None)
        return entry.copy() if entry else None

    def add_forward(self, public_port: int, private_ip: str, private_port: int, protocol: str = "TCP"):
        if not 1 <= public_port <= 65535 or not 1 <= private_port <= 65535:
            raise ValueError("端口必须为 1 至 65535。")
        address = ipaddress.ip_address(private_ip)
        if address.version != 4:
            raise ValueError("NAT44 端口映射内部地址必须为 IPv4。")
        self.forwards[(protocol.upper(), public_port)] = (str(address), private_port)

    def expire(self, now: float):
        self.entries = {key: value for key, value in self.entries.items() if value["expires"] > now}

    def to_dict(self):
        return {"public_ip": self.public_ip, "next_port": self.next_port, "timeout": self.timeout,
                "entries": list(self.entries.values()),
                "forwards": [{"protocol": key[0], "public_port": key[1], "private_ip": value[0], "private_port": value[1]}
                             for key, value in self.forwards.items()]}

    @classmethod
    def from_dict(cls, data):
        table = cls(data["public_ip"], data["next_port"], data["timeout"])
        table.entries = {(row["protocol"], row["private_ip"], row["private_port"]): row for row in data["entries"]}
        for row in data["forwards"]:
            table.add_forward(row["public_port"], row["private_ip"], row["private_port"], row["protocol"])
        return table


class DNSResolver:
    def __init__(self, records: dict | None = None):
        self.records = records or {"example.test": {"A": ["203.0.113.10"], "AAAA": ["2001:db8::10"], "TTL": 120}}
        self.cache: dict[tuple, dict] = {}

    def query(self, name: str, record_type: str = "A", now: float = 0.0) -> dict:
        name, record_type = name.rstrip(".").lower(), record_type.upper()
        if not name or len(name) > 253 or record_type not in {"A", "AAAA", "CNAME", "MX", "TXT", "NS"}:
            raise ValueError("域名或记录类型无效。")
        key = (name, record_type)
        if key in self.cache and self.cache[key]["expires"] > now:
            return {**self.cache[key], "cached": True, "steps": ["本地解析缓存命中"]}
        row = self.records.get(name)
        if row is None:
            return {"name": name, "type": record_type, "values": [], "rcode": "NXDOMAIN",
                    "cached": False, "steps": ["递归解析器", "根区指向 TLD", "TLD 指向权威服务器", "权威服务器：域名不存在"]}
        result = {"name": name, "type": record_type, "values": row.get(record_type, []),
                  "rcode": "NOERROR", "ttl": int(row.get("TTL", 120)), "expires": now + int(row.get("TTL", 120)),
                  "cached": False, "steps": ["递归解析器", "根区指向 TLD", "TLD 指向权威服务器", "权威回答", "写入缓存"]}
        self.cache[key] = result.copy()
        return result


def evaluate_firewall(packet: dict, rules: list[dict], default: str = "deny") -> dict:
    """Ordered first-match teaching firewall. Windows firewall has different policy semantics."""
    packet = {**packet,
              "source_ip": packet.get("source_ip", packet.get("source")),
              "destination_ip": packet.get("destination_ip", packet.get("destination")),
              "destination_port": packet.get("destination_port", packet.get("dport", 0))}
    if not packet.get("protocol"):
        raise ValueError("数据包必须包含 protocol。")
    if packet.get("source_ip"):
        ipaddress.ip_address(packet["source_ip"])
    if packet.get("destination_ip"):
        ipaddress.ip_address(packet["destination_ip"])
    if default not in {"allow", "deny"}:
        raise ValueError("默认动作应为 allow 或 deny。")
    for index, rule in enumerate(rules):
        if rule.get("protocol", "ANY").upper() not in {"ANY", packet["protocol"].upper()}:
            continue
        if ("port" in rule or "dport" in rule) and int(rule.get("port", rule.get("dport"))) != int(packet.get("destination_port", 0)):
            continue
        if "source" in rule and ipaddress.ip_address(packet["source_ip"]) not in ipaddress.ip_network(rule["source"], strict=False):
            continue
        if "destination" in rule and ipaddress.ip_address(packet["destination_ip"]) not in ipaddress.ip_network(rule["destination"], strict=False):
            continue
        if rule["action"] not in {"allow", "deny"}:
            raise ValueError("规则动作无效。")
        return {"action": rule["action"], "matched_rule": index, "explanation": f"命中第 {index + 1} 条规则。"}
    return {"action": default, "matched_rule": None, "explanation": "未匹配规则，使用默认动作。"}


def wifi_associate(access_points: list[dict], position: tuple[float, float], current: str | None = None,
                   roam_margin: float = 8) -> dict:
    """Distance/path-loss association illustration; not a hardware radio measurement."""
    import math
    if not access_points:
        return {"associated": None, "signals": [], "events": []}
    signals = []
    for ap in access_points:
        distance = max(1.0, math.hypot(ap["x"] - position[0], ap["y"] - position[1]))
        dbm = float(ap.get("power_dbm", -35)) - 20 * math.log10(distance)
        signals.append({"id": ap["id"], "signal_dbm": round(dbm, 2), "channel": ap.get("channel", 1)})
    best = max(signals, key=lambda row: row["signal_dbm"])
    old = next((row for row in signals if row["id"] == current), None)
    selected = old if old and best["signal_dbm"] - old["signal_dbm"] < roam_margin else best
    return {"associated": selected["id"], "signals": signals,
            "events": ["扫描信道", "开放系统认证及关联", "WPA 握手由成熟实现负责"] if not current
                      else ["漫游切换", "重新关联"] if selected["id"] != current else ["保持当前接入点"],
            "note": "距离衰减是教学近似；不模拟 OFDMA、MIMO、射频干扰或 WPA 密码学。"}

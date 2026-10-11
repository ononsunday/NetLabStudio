"""Event-driven Ethernet/IP network model with explicit device and packet state.

The model is educational: one frame is transmitted as a unit, IPv4 fragmentation,
FCS, router control protocols and physical radio behavior are not emulated.
"""
from __future__ import annotations

import copy
import ipaddress
import math
import re
from dataclasses import asdict, dataclass, field

from .events import Event, EventEngine
from .routing import bellman_ford, bgp_propagate, dijkstra, longest_prefix_match
from .services import DHCPServer, NATTable


@dataclass
class Interface:
    name: str = "eth0"
    ip: str = ""
    mac: str = ""
    vlan: int = 1
    mode: str = "access"
    allowed_vlans: list[int] = field(default_factory=lambda: [1])
    mtu: int = 1500
    up: bool = True

    def __post_init__(self):
        if self.ip:
            ipaddress.ip_interface(self.ip)
        if self.mac:
            self.mac = self.mac.replace("-", ":").lower()
            if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", self.mac):
                raise ValueError("MAC 地址应包含 6 组两位十六进制数。")
        if not 1 <= int(self.vlan) <= 4094 or self.mtu < 68 or self.mode not in {"access", "trunk"}:
            raise ValueError("接口 VLAN、MTU 或端口模式无效。")
        if any(not 1 <= int(vlan) <= 4094 for vlan in self.allowed_vlans):
            raise ValueError("Trunk VLAN 必须为 1 至 4094。")


@dataclass
class Device:
    id: str
    name: str = ""
    type: str = "pc"
    x: float = 0
    y: float = 0
    interfaces: list[Interface] = field(default_factory=list)
    gateway: str = ""
    routes: list[dict] = field(default_factory=list)
    up: bool = True
    dhcp: dict | None = None
    nat: dict | None = None
    asn: int = 65000
    arp: dict = field(default_factory=dict)
    mac_table: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id or ":" in self.id:
            raise ValueError("设备 id 必须非空且不包含冒号。")
        self.name = self.name or self.id
        self.type = self.type.lower()
        if self.type not in {"pc", "laptop", "server", "switch", "router", "ap", "internet"}:
            raise ValueError("未知设备类型。")
        if self.gateway:
            ipaddress.ip_address(self.gateway)
        for route in self.routes:
            ipaddress.ip_network(route["network"], strict=False)
            if route.get("gateway"):
                if ipaddress.ip_address(route["gateway"]).version != ipaddress.ip_network(route["network"], strict=False).version:
                    raise ValueError("路由网关与目的前缀必须为相同地址族。")
        if not self.interfaces:
            self.interfaces = [Interface()]

    def interface(self, name: str) -> Interface:
        return next(iface for iface in self.interfaces if iface.name == name)

    def owns(self, address: str) -> bool:
        return any(iface.ip and str(ipaddress.ip_interface(iface.ip).ip) == address for iface in self.interfaces)


@dataclass
class Link:
    a: str
    b: str
    id: str = ""
    delay_ms: float = 5
    jitter_ms: float = 0
    bandwidth_mbps: float = 100
    loss: float = 0
    cost: float = 1
    up: bool = True

    def __post_init__(self):
        if any(not math.isfinite(value) for value in (self.delay_ms, self.jitter_ms, self.bandwidth_mbps, self.loss, self.cost)) or self.delay_ms < 0 or self.jitter_ms < 0 or self.bandwidth_mbps <= 0 or not 0 <= self.loss <= 1 or self.cost <= 0:
            raise ValueError("链路时延、带宽、丢包率或代价无效。")


class Topology:
    def __init__(self, nodes: list[Device], links: list[Link], name: str = "实验拓扑"):
        self.name = name
        self.nodes = {node.id: node for node in nodes}
        if len(self.nodes) != len(nodes):
            raise ValueError("设备 id 必须唯一。")
        self.links = links
        endpoints = set()
        for index, node in enumerate(nodes, 1):
            names = set()
            for port, iface in enumerate(node.interfaces):
                if iface.name in names or not iface.name or ":" in iface.name:
                    raise ValueError("接口名必须唯一、非空且不含冒号。")
                names.add(iface.name)
                if not iface.mac:
                    iface.mac = f"02:00:{index // 256:02x}:{index % 256:02x}:00:{port:02x}"
        for index, link in enumerate(links, 1):
            link.id = link.id or f"link-{index}"
            for endpoint in (link.a, link.b):
                node, iface = self.resolve(endpoint)
                if endpoint in endpoints:
                    raise ValueError(f"接口 {endpoint} 已连接；每个接口只能连接一条链路。")
                endpoints.add(endpoint)
            if link.a == link.b:
                raise ValueError("不能连接同一个接口。")

    def resolve(self, endpoint: str) -> tuple[Device, Interface]:
        try:
            node_id, name = endpoint.split(":", 1)
            node = self.nodes[node_id]
            return node, node.interface(name)
        except (ValueError, KeyError, StopIteration) as error:
            raise ValueError(f"未知端口：{endpoint}") from error

    @classmethod
    def from_dict(cls, data: dict) -> "Topology":
        data = copy.deepcopy(data)
        def known(row, model):
            fields = model.__dataclass_fields__
            return {key: value for key, value in row.items() if key in fields}
        nodes = []
        for row in data["nodes"]:
            row = known(row, Device)
            row["interfaces"] = [Interface(**known(iface, Interface)) for iface in row.get("interfaces", [])]
            nodes.append(Device(**row))
        return cls(nodes, [Link(**known(row, Link)) for row in data.get("links", [])], data.get("name", "实验拓扑"))

    def to_dict(self) -> dict:
        return {"name": self.name, "nodes": [asdict(node) for node in self.nodes.values()],
                "links": [asdict(link) for link in self.links], "mode": "teaching_simulation"}


class NetworkSimulator:
    def __init__(self, topology: Topology, seed: int = 1):
        self.topology = topology
        self.original = copy.deepcopy(topology.to_dict())
        self.engine = EventEngine(seed)
        self.packets: dict[str, dict] = {}
        self.pending: dict[str, list[dict]] = {}
        self.link_ready: dict[str, float] = {}
        self.packet_counter = 0
        self.stats = {"frames_sent": 0, "delivered": 0, "dropped": 0, "bytes_sent": 0}
        self.dhcp = {node.id: DHCPServer(**node.dhcp) for node in topology.nodes.values() if node.dhcp}
        self.nat = {node.id: NATTable(**{key: value for key, value in node.nat.items()
                                      if key in {"public_ip", "first_port", "timeout"}})
                    for node in topology.nodes.values() if node.nat}
        self.blocked_links: set[str] = set()
        self.recompute_stp()

    @classmethod
    def from_dict(cls, topology: dict, seed: int = 1):
        return cls(Topology.from_dict(topology), seed)

    def recompute_stp(self):
        """Kruskal minimum tree for inter-switch links; bridge-id tie breaking."""
        previous_blocked = self.blocked_links.copy()
        parent = {node.id: node.id for node in self.topology.nodes.values() if node.up and node.type in {"switch", "ap"}}
        def find(node):
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node
        self.blocked_links = set()
        for link in sorted(self.topology.links, key=lambda row: (row.cost, row.id)):
            a, b = link.a.split(":")[0], link.b.split(":")[0]
            if not link.up or a not in parent or b not in parent:
                continue
            if find(a) == find(b):
                self.blocked_links.add(link.id)
            else:
                parent[find(b)] = find(a)
        if previous_blocked != self.blocked_links:
            for node in self.topology.nodes.values():
                if node.type in {"switch", "ap"}:
                    node.mac_table.clear()
            self._note("STP_TOPOLOGY_CHANGE", "STP", explanation="最小生成树变化，清除交换学习表并启用新的转发树。",
                       data={"blocked_before": sorted(previous_blocked), "blocked_after": sorted(self.blocked_links)})

    def _note(self, kind: str, source: str, target: str = "", packet_id: str | None = None,
              explanation: str = "", data: dict | None = None):
        self.engine.schedule(0, kind, source, target, packet_id, explanation, data)

    def _packet(self, protocol: str, source: str, destination: str, payload: str = "", **fields) -> dict:
        self.packet_counter += 1
        header = (40 if ":" in source else 20) + (20 if protocol == "TCP" else 8)
        packet = {"id": f"packet-{self.packet_counter:06d}", "protocol": protocol,
                  "source_ip": source, "destination_ip": destination, "payload": payload,
                  "ttl": 64, "size": len(payload.encode("utf-8")) + header,
                  "source_port": 50000, "destination_port": 7,
                  "status": "created", "current": "", "path": [], "encapsulation": [], **fields}
        self.packets[packet["id"]] = packet
        return packet

    def send(self, source: str, target: str, protocol: str = "ICMP", payload: str = "hello",
             source_port: int = 50000, destination_port: int = 7, ttl: int = 64, size: int | None = None) -> str:
        if source not in self.topology.nodes:
            raise ValueError("源设备不存在。")
        source_node = self.topology.nodes[source]
        if target in self.topology.nodes:
            target_node = self.topology.nodes[target]
            target = next((str(ipaddress.ip_interface(iface.ip).ip) for iface in target_node.interfaces if iface.ip), "")
        address = ipaddress.ip_address(target)
        selected_route = self._route(source_node, str(address))
        source_iface = selected_route[0] if selected_route and selected_route[0].ip else next((
            iface for iface in source_node.interfaces if iface.ip and ipaddress.ip_interface(iface.ip).version == address.version), None)
        if not source_iface:
            raise ValueError("源设备没有同地址族的 IP 接口。")
        if protocol.upper() not in {"ICMP", "UDP", "TCP"}:
            raise ValueError("拓扑发送支持 ICMP、UDP、TCP。")
        if not 1 <= ttl <= 255 or not 1 <= source_port <= 65535 or not 1 <= destination_port <= 65535:
            raise ValueError("TTL 或端口无效。")
        minimum_size = (40 if address.version == 6 else 20) + (20 if protocol.upper() == "TCP" else 8) + (
            0 if protocol.upper() == "TCP" else len(payload.encode("utf-8")))
        if size is not None and not minimum_size <= size <= 65535:
            raise ValueError(f"数据包大小应为 {minimum_size} 至 65535 字节，必须容纳实际首部与载荷。")
        packet = self._packet(protocol.upper(), str(ipaddress.ip_interface(source_iface.ip).ip), str(address),
                              "" if protocol.upper() == "TCP" else payload,
                              source_port=source_port, destination_port=destination_port, ttl=ttl,
                              **({"size": size} if size is not None else {}))
        if protocol.upper() == "TCP":
            packet.update(tcp_flags="SYN", sequence=1000, acknowledgement=0, application_payload=payload)
        self.engine.schedule(0, "IP_SEND", source, target, packet["id"],
                             "TCP 发起连接；用户载荷排队，拓扑模式仅建立连接。" if protocol.upper() == "TCP" else "应用数据交给虚拟 IP 协议栈。", {"node": source})
        return packet["id"]

    def _route(self, node: Device, destination: str) -> tuple[Interface, str] | None:
        address = ipaddress.ip_address(destination)
        routes = node.routes.copy()
        for iface in node.interfaces:
            if iface.ip and iface.up:
                network = ipaddress.ip_interface(iface.ip).network
                routes.append({"network": str(network), "interface": iface.name, "metric": 0})
        if node.gateway and ipaddress.ip_address(node.gateway).version == address.version:
            routes.append({"network": "0.0.0.0/0" if address.version == 4 else "::/0", "gateway": node.gateway,
                           "interface": node.interfaces[0].name, "metric": 100})
        route = longest_prefix_match(destination, routes)
        if not route:
            return None
        try:
            iface = node.interface(route.get("interface", node.interfaces[0].name))
        except StopIteration:
            return None
        return (iface, route.get("gateway") or destination) if iface.up and iface.ip and ipaddress.ip_interface(iface.ip).version == address.version else None

    def _drop(self, packet: dict, node: str, reason: str):
        packet["status"] = "dropped"
        self.stats["dropped"] += 1
        self._note("DROP", node, packet["destination_ip"], packet["id"], reason)

    def _ip_send(self, node_id: str, packet: dict):
        node = self.topology.nodes[node_id]
        packet["current"] = node_id
        if not node.up:
            self._drop(packet, node_id, "设备已关闭。")
            return
        if node.owns(packet["destination_ip"]):
            self._deliver(node, packet)
            return
        route = self._route(node, packet["destination_ip"])
        if route is None:
            self._drop(packet, node_id, "最长前缀匹配没有找到可用路由。")
            return
        iface, next_hop = route
        packet["path"].append(node_id)
        self._note("ROUTE", node_id, next_hop, packet["id"], f"最长前缀匹配选择 {iface.name}，下一跳 {next_hop}。")
        if packet["size"] > iface.mtu:
            self._drop(packet, node_id, f"数据包 {packet['size']} 字节超过 MTU {iface.mtu}；返回 Packet Too Big/需要分片提示，模型不执行分片。")
            return
        if node_id in self.nat and iface.name == node.nat.get("outside", "wan") and not packet.get("nat_applied"):
            mapping = self.nat[node_id].outbound(packet["source_ip"], packet["source_port"], packet["protocol"], self.engine.time)
            packet["original_source"] = [packet["source_ip"], packet["source_port"]]
            packet["source_ip"], packet["source_port"] = mapping["public_ip"], mapping["public_port"]
            packet["nat_applied"] = True
            self._note("NAT_OUT", node_id, next_hop, packet["id"], "PAT 改写源地址和源端口。", mapping)
        cache = node.arp.get(next_hop)
        if cache and cache["expires"] > self.engine.time:
            self._frame(node_id, iface, packet, cache["mac"])
            return
        key = f"{node_id}|{iface.name}|{next_hop}"
        self.pending.setdefault(key, []).append({"packet_id": packet["id"], "iface": iface.name})
        if len(self.pending[key]) == 1:
            version = ipaddress.ip_address(next_hop).version
            kind = "ARP" if version == 4 else "ND"
            request = self._packet(kind, str(ipaddress.ip_interface(iface.ip).ip), next_hop,
                                   operation="request", sender_mac=iface.mac, owner=node_id, size=28 if version == 4 else 64)
            self._note(f"{kind}_REQUEST", node_id, next_hop, request["id"],
                       "广播查询下一跳 MAC。" if version == 4 else "发送邻居请求（模型使用链路内泛洪表示 solicited-node 多播）。")
            self._frame(node_id, iface, request, "ff:ff:ff:ff:ff:ff")
            self.engine.schedule(1.0, "ARP_TIMEOUT", node_id, next_hop, packet["id"],
                                 "邻居解析超时检查。", {"key": key})

    def _frame(self, node_id: str, iface: Interface, packet: dict, destination_mac: str):
        frame = {"packet_id": packet["id"], "source_mac": iface.mac, "destination_mac": destination_mac,
                 "vlan": iface.vlan, "tagged": iface.mode == "trunk"}
        ethernet = {"layer": "Ethernet", "source": iface.mac, "destination": destination_mac,
                    "vlan": iface.vlan, "tagged": iface.mode == "trunk"}
        if packet["protocol"] == "ARP":
            packet["encapsulation"] = [ethernet, {"layer": "ARP", "operation": packet["operation"],
                                                  "sender_ip": packet["source_ip"], "target_ip": packet["destination_ip"],
                                                  "sender_mac": packet["sender_mac"]}]
        else:
            ipv6 = ":" in packet["source_ip"]
            protocol = {"layer": "ICMPv6 ND" if packet["protocol"] == "ND" else packet["protocol"],
                        "payload": packet["payload"]}
            if packet["protocol"] in {"TCP", "UDP"}:
                protocol.update(source_port=packet["source_port"], destination_port=packet["destination_port"])
            if packet["protocol"] == "TCP":
                protocol.update(flags=packet.get("tcp_flags"), sequence=packet.get("sequence"),
                                acknowledgement=packet.get("acknowledgement"))
            packet["encapsulation"] = [ethernet, {"layer": "IPv6" if ipv6 else "IPv4",
                                                  "source": packet["source_ip"], "destination": packet["destination_ip"],
                                                  "hop_limit" if ipv6 else "ttl": packet["ttl"]}, protocol]
        self._transmit(f"{node_id}:{iface.name}", frame)

    def _transmit(self, endpoint: str, frame: dict):
        packet = self.packets[frame["packet_id"]]
        link = next((link for link in self.topology.links if endpoint in (link.a, link.b)), None)
        if link is None or not link.up or link.id in self.blocked_links:
            if packet["protocol"] not in {"ARP", "ND"}:
                self._drop(packet, endpoint.split(":")[0], "端口未连接、链路关闭或被生成树阻塞。")
            return
        other = link.b if endpoint == link.a else link.a
        source_node, source_iface = self.topology.resolve(endpoint)
        target_node, target_iface = self.topology.resolve(other)
        if not source_node.up or not source_iface.up or not target_node.up or not target_iface.up:
            self._drop(packet, source_node.id, "链路端点设备或接口已关闭。")
            return
        now = self.engine.time
        queue_key = f"{link.id}:{endpoint}"
        start = max(now, self.link_ready.get(queue_key, now))
        frame_size = max(64, packet["size"] + 18 + (4 if frame.get("tagged") else 0))
        serialization = frame_size * 8 / (link.bandwidth_mbps * 1_000_000)
        self.link_ready[queue_key] = start + serialization
        propagation = max(0, link.delay_ms + self.engine.rng.uniform(-link.jitter_ms, link.jitter_ms)) / 1000
        self.stats["frames_sent"] += 1
        self.stats["bytes_sent"] += frame_size
        packet["status"] = "in_flight"
        self._note("FRAME_SEND", source_node.id, target_node.id, packet["id"],
                   f"链路排队 {(start - now) * 1000:.3f} ms；串行化 {serialization * 1000:.3f} ms。", {"link": link.id, **frame})
        if self.engine.rng.random() < link.loss:
            self.engine.schedule(start - now + serialization + propagation, "LINK_DROP", source_node.id,
                                 target_node.id, packet["id"], "依据链路丢包概率随机丢弃。")
        else:
            self.engine.schedule(start - now + serialization + propagation, "FRAME_RECEIVE", source_node.id,
                                 target_node.id, packet["id"], "完整虚拟帧到达链路另一端。", {"ingress": other, "link": link.id, "frame": copy.deepcopy(frame)})

    def _switch(self, node: Device, ingress: Interface, frame: dict):
        vlan = frame["vlan"] if ingress.mode == "trunk" else ingress.vlan
        if ingress.mode == "trunk" and vlan not in ingress.allowed_vlans:
            self._note("VLAN_DROP", node.id, packet_id=frame["packet_id"], explanation=f"Trunk 不允许 VLAN {vlan}。")
            return
        if frame["tagged"] and ingress.mode != "trunk":
            self._note("VLAN_DROP", node.id, packet_id=frame["packet_id"], explanation="带标签帧到达 Access 端口；教学模型拒绝。")
            return
        key = f"{vlan}|{frame['source_mac']}"
        node.mac_table[key] = {"port": ingress.name, "expires": self.engine.time + 300}
        self._note("MAC_LEARN", node.id, packet_id=frame["packet_id"],
                   explanation=f"从源 MAC 学习 VLAN {vlan}：{frame['source_mac']} → {ingress.name}。")
        entry = node.mac_table.get(f"{vlan}|{frame['destination_mac']}")
        if entry and entry["expires"] <= self.engine.time:
            entry = None
        ports = [node.interface(entry["port"])] if entry else node.interfaces
        for out in ports:
            if out.name == ingress.name or not out.up:
                continue
            if (out.mode == "access" and out.vlan != vlan) or (out.mode == "trunk" and vlan not in out.allowed_vlans):
                continue
            forwarded = {**frame, "vlan": vlan, "tagged": out.mode == "trunk"}
            self._note("SWITCH_FORWARD" if entry else "SWITCH_FLOOD", node.id, out.name, frame["packet_id"],
                       "查表单播转发。" if entry else f"目的 MAC 未知或广播，在 VLAN {vlan} 内泛洪。")
            self._transmit(f"{node.id}:{out.name}", forwarded)

    def _receive(self, event: Event):
        node, iface = self.topology.resolve(event.data["ingress"])
        frame = event.data["frame"]
        packet = self.packets[event.packet_id]
        packet["current"] = node.id
        link = next((link for link in self.topology.links if link.id == event.data.get("link")), None)
        if not node.up or not iface.up or link is not None and (not link.up or link.id in self.blocked_links):
            self._drop(packet, node.id, "帧到达前设备、接口或链路关闭，或生成树已阻塞该链路。")
            return
        if node.type in {"switch", "ap"}:
            self._switch(node, iface, frame)
            return
        if frame["destination_mac"] not in {iface.mac, "ff:ff:ff:ff:ff:ff"}:
            return
        if iface.mode == "trunk" and frame["vlan"] not in iface.allowed_vlans:
            return
        if iface.mode == "access" and frame["vlan"] != iface.vlan:
            return
        if packet["protocol"] in {"ARP", "ND"}:
            self._neighbor(node, iface, packet)
            return
        if node.id in self.nat and iface.name == node.nat.get("outside", "wan") and packet["destination_ip"] == self.nat[node.id].public_ip:
            mapping = self.nat[node.id].inbound(packet["destination_port"], packet["protocol"], self.engine.time)
            if mapping:
                packet["destination_ip"], packet["destination_port"] = mapping["private_ip"], mapping["private_port"]
                self._note("NAT_IN", node.id, packet["destination_ip"], packet["id"], "NAT 映射反向转换目的地址和端口。", mapping)
        if node.owns(packet["destination_ip"]):
            self._deliver(node, packet)
        elif node.type in {"router", "internet"}:
            packet["ttl"] -= 1
            if packet["ttl"] <= 0:
                self._drop(packet, node.id, "TTL/Hop Limit 归零，产生 Time Exceeded 教学事件。")
            else:
                self._ip_send(node.id, packet)
        else:
            self._drop(packet, node.id, "目标 IP 不属于此主机；主机不进行 IP 转发。")

    def _neighbor(self, node: Device, iface: Interface, packet: dict):
        node.arp[packet["source_ip"]] = {"mac": packet["sender_mac"], "expires": self.engine.time + 60}
        if packet["operation"] == "request" and node.owns(packet["destination_ip"]):
            response = self._packet(packet["protocol"], packet["destination_ip"], packet["source_ip"],
                                    operation="reply", sender_mac=iface.mac, size=28 if packet["protocol"] == "ARP" else 64)
            self._note(f"{packet['protocol']}_REPLY", node.id, packet["owner"], response["id"], "返回本接口 MAC 地址。")
            self._frame(node.id, iface, response, packet["sender_mac"])
        elif packet["operation"] == "reply":
            key = f"{node.id}|{iface.name}|{packet['source_ip']}"
            for item in self.pending.pop(key, []):
                self._frame(node.id, node.interface(item["iface"]), self.packets[item["packet_id"]], packet["sender_mac"])
        packet["status"] = "processed"

    def _deliver(self, node: Device, packet: dict):
        packet["status"], packet["current"] = "delivered", node.id
        if not packet["path"] or packet["path"][-1] != node.id:
            packet["path"].append(node.id)
        self.stats["delivered"] += 1
        self._note("DELIVER", node.id, node.id, packet["id"], "目的 IP 匹配，交给上层协议。")
        if packet["protocol"] == "ICMP" and not packet.get("reply"):
            reply = self._packet("ICMP", packet["destination_ip"], packet["source_ip"], packet["payload"], reply=True,
                                 source_port=packet["destination_port"], destination_port=packet["source_port"])
            self._ip_send(node.id, reply)
        elif packet["protocol"] == "TCP":
            flags = packet.get("tcp_flags", "")
            if flags == "SYN":
                response = self._packet("TCP", packet["destination_ip"], packet["source_ip"], "", tcp_flags="SYN,ACK",
                                        sequence=7000, acknowledgement=packet["sequence"] + 1,
                                        source_port=packet["destination_port"], destination_port=packet["source_port"])
                self._note("TCP_STATE", node.id, packet_id=packet["id"], explanation="服务器 LISTEN → SYN_RECEIVED。")
                self._ip_send(node.id, response)
            elif flags == "SYN,ACK":
                ack = self._packet("TCP", packet["destination_ip"], packet["source_ip"], "", tcp_flags="ACK",
                                   sequence=packet["acknowledgement"], acknowledgement=packet["sequence"] + 1,
                                   source_port=packet["destination_port"], destination_port=packet["source_port"])
                self._note("TCP_STATE", node.id, packet_id=packet["id"], explanation="客户端 SYN_SENT → ESTABLISHED；发送 ACK。")
                self._ip_send(node.id, ack)
            elif flags == "ACK":
                self._note("TCP_STATE", node.id, packet_id=packet["id"], explanation="服务器 SYN_RECEIVED → ESTABLISHED（仅连接建立模型）。")

    def request_dhcp(self, client: str, server: str) -> dict:
        if client not in self.topology.nodes or server not in self.dhcp:
            raise ValueError("客户端或 DHCP 服务器不存在。")
        node = self.topology.nodes[client]
        iface = node.interfaces[0]
        if client == server or not self._dhcp_reachable(node, iface, self.topology.nodes[server], self.dhcp[server].network):
            raise RuntimeError("客户端无法在当前链路、VLAN 与设备状态下访问该 DHCP 服务；模型未配置 DHCP 中继。")
        allocation = self.dhcp[server].allocate(iface.mac, self.engine.time)
        iface.ip = f"{allocation['address']}/{ipaddress.ip_network('0.0.0.0/' + allocation['mask']).prefixlen}"
        node.gateway = allocation["gateway"]
        for index, kind in enumerate(allocation["exchange"]):
            self.engine.schedule(index * 0.01, f"DHCP_{kind}", client if index % 2 == 0 else server,
                                 server if index % 2 == 0 else client, explanation=f"DHCP {kind}：{allocation['address']}。",
                                 data={"lease": allocation.copy()})
        return allocation

    def _dhcp_reachable(self, client: Device, iface: Interface, server: Device, network) -> bool:
        """Traverse the client's broadcast domain, respecting STP and port VLANs."""
        if not client.up or not iface.up or not server.up:
            return False
        work = [(f"{client.id}:{iface.name}", iface.vlan, iface.mode == "trunk")]
        visited = set()
        while work:
            endpoint, vlan, tagged = work.pop()
            if (endpoint, vlan, tagged) in visited:
                continue
            visited.add((endpoint, vlan, tagged))
            link = next((link for link in self.topology.links if endpoint in (link.a, link.b)), None)
            if link is None or not link.up or link.id in self.blocked_links:
                continue
            opposite = link.b if endpoint == link.a else link.a
            node, ingress = self.topology.resolve(opposite)
            if not node.up or not ingress.up:
                continue
            if ingress.mode == "trunk" and vlan not in ingress.allowed_vlans:
                continue
            if ingress.mode == "access" and (tagged or node.type not in {"switch", "ap"} and vlan != ingress.vlan):
                continue
            incoming_vlan = vlan if ingress.mode == "trunk" else ingress.vlan
            if node.id == server.id and ingress.ip and ipaddress.ip_interface(ingress.ip).ip in network:
                return True
            if node.type not in {"switch", "ap"}:
                continue
            for out in node.interfaces:
                if out.name == ingress.name or not out.up:
                    continue
                if out.mode == "access" and out.vlan != incoming_vlan or out.mode == "trunk" and incoming_vlan not in out.allowed_vlans:
                    continue
                work.append((f"{node.id}:{out.name}", incoming_vlan, out.mode == "trunk"))
        return False

    def set_link(self, link_id: str, up: bool):
        link = next((item for item in self.topology.links if item.id == link_id), None)
        if link is None:
            raise ValueError("链路不存在。")
        link.up = bool(up)
        self.recompute_stp()
        self._note("LINK_STATE", link.a.split(":")[0], link.b.split(":")[0], explanation=f"链路 {link.id} {'恢复' if up else '断开'}。")

    def set_device(self, node_id: str, up: bool):
        if node_id not in self.topology.nodes:
            raise ValueError("设备不存在。")
        self.topology.nodes[node_id].up = bool(up)
        self.recompute_stp()
        self._note("DEVICE_STATE", node_id, explanation=f"设备 {'恢复' if up else '关闭'}。")

    def configure_routing(self, protocol: str = "OSPF") -> dict:
        """Compute teaching convergence and atomically install virtual IP routes.

        Neighbor detection follows IP prefixes and live L2 VLAN reachability;
        only routers are transit vertices. This does not emit real RIP/OSPF/BGP.
        Static routes are retained and win same-prefix metric ties when lower.
        """
        protocol = protocol.upper()
        if protocol not in {"RIP", "OSPF", "BGP"}:
            raise ValueError("动态路由教学协议支持 RIP、OSPF、BGP。")
        routers = {node.id: node for node in self.topology.nodes.values()
                   if node.up and node.type in {"router", "internet"}}
        graph, adjacency = {node: {} for node in routers}, {}
        for source_id, source in routers.items():
            for iface in source.interfaces:
                if not iface.up or not iface.ip:
                    continue
                network = ipaddress.ip_interface(iface.ip).network
                link = next((link for link in self.topology.links if f"{source_id}:{iface.name}" in (link.a, link.b)), None)
                if not link or not link.up:
                    continue
                for neighbor_id, neighbor in routers.items():
                    if neighbor_id == source_id:
                        continue
                    candidate = next((other for other in neighbor.interfaces if other.up and other.ip
                                      and ipaddress.ip_interface(other.ip).version == network.version
                                      and ipaddress.ip_interface(other.ip).ip in network), None)
                    if candidate is None or not self._dhcp_reachable(source, iface, neighbor, network):
                        continue
                    cost = float(link.cost) if protocol == "OSPF" else 1.0
                    if neighbor_id not in graph[source_id] or cost < graph[source_id][neighbor_id]:
                        graph[source_id][neighbor_id] = cost
                        adjacency[(source_id, neighbor_id)] = {"interface": iface.name,
                                                               "gateway": str(ipaddress.ip_interface(candidate.ip).ip)}
        result = {"protocol": protocol, "mode": "teaching_simulation", "adjacency": graph,
                  "tables": {}, "steps": {}, "events": []}
        bgp = bgp_propagate(graph, {node: routers[node].asn for node in routers}) if protocol == "BGP" else None
        for source_id, source in routers.items():
            source.routes = [route for route in source.routes if route.get("protocol") not in {"RIP", "OSPF", "BGP"}]
            connected = {str(ipaddress.ip_interface(iface.ip).network) for iface in source.interfaces if iface.ip and iface.up}
            if protocol == "BGP":
                paths = {row["destination"]: row["path"] for row in bgp["tables"][source_id]}
                metrics = {row["destination"]: row["metric"] for row in bgp["tables"][source_id]}
                result["steps"][source_id] = bgp["steps"]
            else:
                computed = bellman_ford(graph, source_id) if protocol == "RIP" else dijkstra(graph, source_id)
                paths, metrics = computed["paths"], computed["distances"]
                result["steps"][source_id] = computed["steps"]
            installed = {}
            for destination_id, path in paths.items():
                metric = metrics[destination_id]
                if len(path) < 2 or metric is None or protocol == "RIP" and metric >= 16:
                    continue
                for destination_iface in routers[destination_id].interfaces:
                    if not destination_iface.ip or not destination_iface.up:
                        continue
                    prefix = str(ipaddress.ip_interface(destination_iface.ip).network)
                    if prefix in connected:
                        continue
                    route = {"network": prefix, **adjacency[(source_id, path[1])],
                             "metric": metric, "protocol": protocol, "device_path": path.copy()}
                    if prefix not in installed or metric < installed[prefix]["metric"]:
                        installed[prefix] = route
            source.routes.extend(installed.values())
            result["tables"][source_id] = list(installed.values())
            self._note("ROUTE_INSTALL", source_id, explanation=f"按 {protocol} 教学收敛计算安装 {len(installed)} 条虚拟路由。",
                       data={"protocol": protocol, "routes": list(installed.values())})
        if bgp:
            result["events"] = bgp["events"]
        result["note"] = "相邻路由器按同子网与当前L2/VLAN可达性发现，教学算法结果原子安装进共享路由表；RIP使用路由跳数，OSPF使用源接口链路代价，BGP使用AS路径。没有模拟控制报文定时/LSA/邻接会话。链路变化后再次计算收敛以撤回或切换路径。"
        return result

    def step(self) -> dict | None:
        event = self.engine.pop()
        if event is None:
            return None
        if event.kind == "IP_SEND":
            self._ip_send(event.data["node"], self.packets[event.packet_id])
        elif event.kind == "FRAME_RECEIVE":
            self._receive(event)
        elif event.kind == "LINK_DROP":
            self._drop(self.packets[event.packet_id], event.source, event.explanation)
        elif event.kind == "ARP_TIMEOUT":
            for item in self.pending.pop(event.data["key"], []):
                self._drop(self.packets[item["packet_id"]], event.source, "ARP/ND 无应答：检查 IP、VLAN、链路及目标状态。")
        return self.engine.record(event)

    def run(self, max_events: int = 10000) -> dict:
        if not 1 <= max_events <= 100000:
            raise ValueError("事件数量应为 1 至 100000。")
        for _ in range(max_events):
            if self.step() is None:
                break
        return self.result()

    def result(self) -> dict:
        return {"mode": "teaching_simulation", "events": copy.deepcopy(self.engine.history),
                "packets": copy.deepcopy(list(self.packets.values())), "devices": self.topology.to_dict()["nodes"],
                "topology": self.topology.to_dict(),
                "stats": self.stats.copy(), "time": self.engine.time, "pending_events": len(self.engine.queue),
                "stp_blocked_links": sorted(self.blocked_links),
                "nat_tables": {key: value.to_dict() for key, value in self.nat.items()},
                "note": "DHCP 为状态化 DORA 服务模型；ND 使用链路泛洪表示多播；STP 为最小树教学模型；TCP 拓扑仅建立连接，重传实验在传输层模拟器。"}

    def packet_bytes(self, packet_id: str) -> bytes:
        """Construct analyzable bytes from virtual fields; never inject these bytes."""
        try:
            from scapy.all import Ether, Dot1Q, IP, IPv6, ARP, ICMP, UDP, TCP, Raw
            from scapy.layers.inet6 import ICMPv6EchoRequest, ICMPv6EchoReply, ICMPv6ND_NS, ICMPv6ND_NA
        except ImportError as error:
            raise RuntimeError("虚拟数据包编码需要可选依赖 Scapy。") from error
        if packet_id not in self.packets:
            raise ValueError("数据包不存在。")
        packet = self.packets[packet_id]
        layer = (packet.get("encapsulation") or [{}])[0]
        ether = Ether(src=layer.get("source", "02:00:00:00:00:01"), dst=layer.get("destination", "02:00:00:00:00:02"))
        if layer.get("tagged"):
            ether = ether / Dot1Q(vlan=int(layer["vlan"]))
        def pad_frame(frame):
            raw = bytes(frame)
            return raw + b"\0" * max(0, 60 - len(raw))  # capture-like bytes omit Ethernet FCS
        if packet["protocol"] == "ARP":
            return pad_frame(ether / ARP(op=1 if packet["operation"] == "request" else 2,
                                     hwsrc=packet["sender_mac"], psrc=packet["source_ip"],
                                     pdst=packet["destination_ip"]))
        ipv6 = ":" in packet["source_ip"]
        ip = IPv6(src=packet["source_ip"], dst=packet["destination_ip"], hlim=packet["ttl"]) if ipv6 else IP(
            src=packet["source_ip"], dst=packet["destination_ip"], ttl=packet["ttl"])
        if packet["protocol"] == "ND":
            protocol = ICMPv6ND_NS(tgt=packet["destination_ip"]) if packet["operation"] == "request" else ICMPv6ND_NA(tgt=packet["source_ip"])
        elif packet["protocol"] == "ICMP":
            protocol = (ICMPv6EchoReply() if packet.get("reply") else ICMPv6EchoRequest()) if ipv6 else ICMP(
                type=0 if packet.get("reply") else 8, id=packet["source_port"] if not packet.get("reply") else packet["destination_port"])
        elif packet["protocol"] == "UDP":
            protocol = UDP(sport=packet["source_port"], dport=packet["destination_port"])
        else:
            flags = {"SYN": "S", "SYN,ACK": "SA", "ACK": "A"}.get(packet.get("tcp_flags"), "PA")
            protocol = TCP(sport=packet["source_port"], dport=packet["destination_port"], flags=flags,
                           seq=packet.get("sequence", 1), ack=packet.get("acknowledgement", 0))
        payload = packet["payload"].encode("utf-8")
        transport_header_length = len(bytes(protocol))
        padding = max(0, packet["size"] - (40 if ipv6 else 20) - transport_header_length - len(payload))
        return pad_frame(ether / ip / protocol / Raw(load=payload + b"\0" * padding))

    def reset(self):
        fresh = self.from_dict(self.original, self.engine.seed)
        self.__dict__.update(fresh.__dict__)

    def snapshot(self) -> dict:
        return copy.deepcopy({"format": "netlab.snapshot.v1", "topology": self.topology.to_dict(), "original": self.original,
                              "engine": self.engine.snapshot(), "packets": self.packets, "pending": self.pending,
                              "link_ready": self.link_ready, "packet_counter": self.packet_counter, "stats": self.stats,
                              "nat": {key: value.to_dict() for key, value in self.nat.items()},
                              "dhcp": {key: {"leases": value.leases, "offers": value.offers} for key, value in self.dhcp.items()}})

    @classmethod
    def restore(cls, snapshot: dict):
        if snapshot.get("format") != "netlab.snapshot.v1":
            raise ValueError("不支持的快照格式。")
        sim = cls.from_dict(snapshot["topology"], snapshot["engine"]["seed"])
        # Construction computes the STP tree and intentionally flushes learning.
        # A snapshot restores already-learned tables, so reload its device state
        # after that initial construction instead of losing MAC entries in loops.
        sim.topology = Topology.from_dict(copy.deepcopy(snapshot["topology"]))
        sim.original = copy.deepcopy(snapshot["original"])
        sim.engine = EventEngine.restore(snapshot["engine"])
        for key in ["packets", "pending", "link_ready", "packet_counter", "stats"]:
            setattr(sim, key, copy.deepcopy(snapshot[key]))
        sim.nat = {key: NATTable.from_dict(value) for key, value in snapshot["nat"].items()}
        for key, value in snapshot["dhcp"].items():
            sim.dhcp[key].leases, sim.dhcp[key].offers = value["leases"], value["offers"]
        return sim


def example_topology(name: str = "home") -> dict:
    def node(identifier, kind, x, y, interfaces, **extra):
        return {"id": identifier, "name": identifier, "type": kind, "x": x, "y": y, "interfaces": interfaces, **extra}
    def port(name, ip="", **extra):
        return {"name": name, "ip": ip, **extra}
    nodes = [node("PC1", "pc", 70, 90, [port("eth0", "192.168.1.10/24")], gateway="192.168.1.1"),
             node("PC2", "laptop", 70, 270, [port("eth0", "192.168.1.20/24")], gateway="192.168.1.1"),
             node("SW1", "switch", 310, 180, [port("p1"), port("p2"), port("p3")]),
             node("R1", "router", 530, 180, [port("lan", "192.168.1.1/24"), port("wan", "203.0.113.1/24")],
                  dhcp={"network": "192.168.1.0/24", "gateway": "192.168.1.1", "start": 100, "end": 199},
                  nat={"public_ip": "203.0.113.1", "outside": "wan"}),
             node("WEB", "server", 760, 180, [port("eth0", "203.0.113.10/24")], gateway="203.0.113.1")]
    links = [{"a": a, "b": b, "id": f"L{index}", "delay_ms": 5, "bandwidth_mbps": 100, "loss": 0}
             for index, (a, b) in enumerate([("PC1:eth0", "SW1:p1"), ("PC2:eth0", "SW1:p2"),
                                             ("SW1:p3", "R1:lan"), ("R1:wan", "WEB:eth0")], 1)]
    if name == "ipv6":
        for node_row in nodes:
            node_row.pop("dhcp", None)
            node_row.pop("nat", None)
            for iface in node_row["interfaces"]:
                ipv4 = iface["ip"]
                if ipv4:
                    octet = ipv4.split("/")[0].split(".")[-1]
                    iface["ip"] = f"2001:db8:{'1' if ipv4.startswith('192') else '2'}::{octet}/64"
            if node_row.get("gateway"):
                node_row["gateway"] = f"2001:db8:{'1' if node_row['gateway'].startswith('192') else '2'}::1"
    elif name == "vlan":
        nodes[1]["interfaces"][0]["vlan"] = 20
        nodes[2]["interfaces"][1]["vlan"] = 20
    elif name in {"vlan_routed", "trunk"}:
        nodes[0]["interfaces"][0].update(ip="192.168.10.10/24", vlan=10)
        nodes[0]["gateway"] = "192.168.10.1"
        nodes[1]["interfaces"][0].update(ip="192.168.20.20/24", vlan=20)
        nodes[1]["gateway"] = "192.168.20.1"
        nodes[2]["interfaces"] = [port("p1", vlan=10), port("p2", vlan=20), port("p3", vlan=10), port("p4", vlan=20)]
        nodes[3].pop("dhcp", None)
        nodes[3]["interfaces"] = [port("lan10", "192.168.10.1/24", vlan=10),
                                  port("lan20", "192.168.20.1/24", vlan=20), port("wan", "203.0.113.1/24")]
        links[2]["b"] = "R1:lan10"
        links.append({"a": "SW1:p4", "b": "R1:lan20", "id": "L5", "delay_ms": 5})
        if name == "trunk":
            nodes[2]["interfaces"] = [port("p1", vlan=10), port("p2", vlan=20),
                                      port("trunk", mode="trunk", allowed_vlans=[10, 20])]
            nodes.append(node("SW2", "switch", 430, 330, [port("trunk", mode="trunk", allowed_vlans=[10, 20]),
                                                          port("p3", vlan=10), port("p4", vlan=20)]))
            links[2].update(a="SW1:trunk", b="SW2:trunk")
            links[-1].update(a="SW2:p4")
            links.append({"a": "SW2:p3", "b": "R1:lan10", "id": "L6", "delay_ms": 5})
    elif name == "routed":
        nodes[3].pop("nat", None)
        nodes[4]["interfaces"][0]["ip"] = "10.20.0.10/24"
        nodes[4]["gateway"] = "10.20.0.1"
        nodes[4]["x"] = 1000
        nodes.append(node("R2", "router", 770, 180, [port("wan", "203.0.113.2/24"), port("lan", "10.20.0.1/24")], asn=65002))
        nodes[3]["asn"] = 65001
        links[3]["b"] = "R2:wan"
        links.append({"a": "R2:lan", "b": "WEB:eth0", "id": "L5", "delay_ms": 5})
    elif name not in {"home", "fault"}:
        raise ValueError("示例名支持 home、ipv6、vlan、vlan_routed、trunk、routed、fault。")
    if name == "fault":
        nodes[0]["gateway"] = "192.168.1.254"
    return {"name": f"示例：{name}", "mode": "teaching_simulation", "nodes": nodes, "links": links}

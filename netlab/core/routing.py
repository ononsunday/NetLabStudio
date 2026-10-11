"""Shortest path and teaching routing models; no host routes are modified."""
from __future__ import annotations

import heapq
import ipaddress
import math


def fragment_datagram(size: int = 4000, mtu: int = 1500, version: int = 4,
                      df: bool = False, header_size: int | None = None,
                      identification: int = 1) -> dict:
    """Compute real IPv4 fragment fields, or the IPv6 router PTB outcome."""
    header = header_size if header_size is not None else (20 if version == 4 else 40)
    if version not in {4, 6} or not isinstance(size, int) or not isinstance(mtu, int):
        raise ValueError("地址族应为 4 或 6；数据包大小与 MTU 应为整数。")
    if version == 4 and (not 20 <= header <= 60 or header % 4):
        raise ValueError("IPv4 首部应为 20 至 60 字节且是 4 的倍数。")
    if version == 6 and header != 40:
        raise ValueError("此模型只计算不含扩展首部的 40 字节 IPv6 首部。")
    if not header <= size <= 65535 or mtu < (68 if version == 4 else 1280) or mtu <= header:
        raise ValueError("大小应在首部长度至 65535 之间；MTU 至少为 IPv4 68 / IPv6 1280 且大于首部。")
    if not 0 <= identification <= 65535:
        raise ValueError("IPv4 Identification 应为 0 至 65535。")
    result = {"mode": "teaching_calculation", "version": version, "packet_size": size,
              "mtu": mtu, "header_size": header, "payload_size": size - header,
              "fragments": [], "error": None, "fragmented": False}
    if size <= mtu:
        result["fragments"] = [{"identification": identification if version == 4 else None,
                                 "offset_bytes": 0, "fragment_offset": 0, "more_fragments": False,
                                 "payload_size": size - header, "total_length": size}]
    elif version == 6 or df:
        result["error"] = "ICMPv6 Packet Too Big" if version == 6 else "ICMP Destination Unreachable: Fragmentation Needed"
        result["suggested_max_payload"] = mtu - header
    else:
        chunk = (mtu - header) // 8 * 8
        remaining, offset = size - header, 0
        while remaining:
            length = min(chunk, remaining)
            remaining -= length
            result["fragments"].append({"identification": identification, "offset_bytes": offset,
                                        "fragment_offset": offset // 8, "more_fragments": remaining > 0,
                                        "payload_size": length, "total_length": header + length})
            offset += length
        result["fragmented"] = True
    result["note"] = "IPv4 非最后一片载荷按 8 字节对齐；偏移以 8 字节计。IPv6 路由器不能分片，源端需处理 Packet Too Big；此函数未构造 IPv6 源端 Fragment 扩展首部。"
    return result


def path_mtu_experiment(packet_size: int = 4000, mtus: list[int] | None = None,
                        version: int = 4, df: bool = True) -> dict:
    mtus = mtus or [1500, 1400, 1280]
    if not mtus or any(not isinstance(mtu, int) for mtu in mtus):
        raise ValueError("路径 MTU 应为非空整数列表。")
    # Validate each link even if the first link already causes a failure.
    for mtu in mtus:
        fragment_datagram(packet_size, mtu, version, df)
    original = packet_size
    events, probes, learned = [], 0, packet_size
    if version == 4 and not df:
        result = fragment_datagram(packet_size, min(mtus), 4, False)
        for index, mtu in enumerate(mtus):
            events.append({"time": float(index), "kind": "MTU_FORWARD", "source": f"R{index}", "target": f"R{index + 1}",
                           "packet_id": "pmtu-datagram", "explanation": f"链路 MTU {mtu}；允许 IPv4 路由分片。",
                           "data": {"mtu": mtu}})
        return {**result, "events": events, "path_mtu": min(mtus), "probes": 1}
    while True:
        probes += 1
        failed = False
        for index, mtu in enumerate(mtus):
            events.append({"time": float(len(events)), "kind": "PMTU_PROBE", "source": f"R{index}", "target": f"R{index + 1}",
                           "packet_id": f"probe-{probes}", "explanation": f"尝试转发 {learned} 字节，出口 MTU {mtu}。",
                           "data": {"packet_size": learned, "mtu": mtu}})
            if learned > mtu:
                events.append({"time": float(len(events)), "kind": "PACKET_TOO_BIG", "source": f"R{index}", "target": "source",
                               "packet_id": f"probe-{probes}", "explanation": "向源端返回所需 MTU；源端缩小下一次探测。",
                               "data": {"mtu": mtu, "icmp": "ICMPv6 PTB" if version == 6 else "IPv4 Fragmentation Needed"}})
                learned, failed = mtu, True
                break
        if not failed:
            break
    return {"mode": "teaching_simulation", "version": version, "events": events,
            "original_size": original, "path_mtu": min(mtus), "successful_probe_size": learned,
            "probes": probes, "success": True,
            "note": "缩小的是后续探测数据包。应用载荷需重新分段或源端分片，不能直接截断原始数据；假定 ICMP 可达，未模拟 PMTU 黑洞。"}


def longest_prefix_match(destination: str, routes: list[dict]) -> dict | None:
    address = ipaddress.ip_address(destination)
    candidates = []
    for route in routes:
        network = ipaddress.ip_network(route["network"], strict=False)
        if network.version == address.version and address in network:
            candidates.append((network.prefixlen, -int(route.get("metric", 0)), route))
    return max(candidates, key=lambda item: item[:2])[2].copy() if candidates else None


def _normalize(graph: dict) -> dict[str, dict[str, float]]:
    result = {str(node): {str(other): float(cost) for other, cost in edges.items()} for node, edges in graph.items()}
    if any(not math.isfinite(cost) for edges in result.values() for cost in edges.values()):
        raise ValueError("图的边权必须为有限数字。")
    for edges in list(result.values()):
        for node in edges:
            result.setdefault(node, {})
    return result


def _paths(previous: dict, distance: dict, source: str) -> dict:
    paths = {}
    for node, cost in distance.items():
        if math.isinf(cost):
            paths[node] = []
            continue
        path, cursor = [], node
        while cursor is not None:
            if cursor in path:
                raise ValueError("发现负权环，无法形成最短路径。")
            path.append(cursor)
            cursor = previous.get(cursor)
        paths[node] = list(reversed(path))
    return paths


def dijkstra(graph: dict, source: str) -> dict:
    graph = _normalize(graph)
    if source not in graph or any(cost < 0 for edges in graph.values() for cost in edges.values()):
        raise ValueError("起点不存在，或 Dijkstra 图包含负权边。")
    distance = {node: math.inf for node in graph}
    distance[source] = 0.0
    previous, visited, steps = {}, set(), []
    queue = [(0.0, source)]
    while queue:
        cost, node = heapq.heappop(queue)
        if node in visited:
            continue
        visited.add(node)
        updates = []
        for neighbor, weight in graph[node].items():
            if cost + weight < distance[neighbor]:
                distance[neighbor], previous[neighbor] = cost + weight, node
                heapq.heappush(queue, (cost + weight, neighbor))
                updates.append({"node": neighbor, "distance": cost + weight, "via": node})
        steps.append({"selected": node, "settled": sorted(visited), "updates": updates,
                      "distances": {key: None if math.isinf(value) else value for key, value in distance.items()}})
    return {"algorithm": "Dijkstra", "distances": {k: None if math.isinf(v) else v for k, v in distance.items()},
            "paths": _paths(previous, distance, source), "steps": steps}


def bellman_ford(graph: dict, source: str) -> dict:
    graph = _normalize(graph)
    if source not in graph:
        raise ValueError("起点不存在。")
    distance = {node: math.inf for node in graph}
    distance[source] = 0.0
    previous, steps = {}, []
    for iteration in range(max(0, len(graph) - 1)):
        updates = []
        old = distance.copy()
        for node, edges in graph.items():
            for neighbor, cost in edges.items():
                if old[node] + cost < distance[neighbor]:
                    distance[neighbor], previous[neighbor] = old[node] + cost, node
                    updates.append({"node": neighbor, "via": node, "distance": distance[neighbor]})
        steps.append({"iteration": iteration + 1, "updates": updates,
                      "distances": {k: None if math.isinf(v) else v for k, v in distance.items()}})
        if not updates:
            break
    if any(distance[node] + cost < distance[neighbor] for node, edges in graph.items() for neighbor, cost in edges.items()):
        raise ValueError("存在可达负权环。")
    return {"algorithm": "Bellman-Ford", "distances": {k: None if math.isinf(v) else v for k, v in distance.items()},
            "paths": _paths(previous, distance, source), "steps": steps}


def route_protocol(topology: dict, protocol: str = "OSPF") -> dict:
    nodes = {node["id"]: node for node in topology["nodes"]}
    graph = {node: {} for node in nodes}
    for link in topology["links"]:
        if not link.get("up", True):
            continue
        a, b = link["a"].split(":")[0], link["b"].split(":")[0]
        cost = float(link.get("cost", 1)) if protocol.upper() == "OSPF" else 1.0
        graph[a][b], graph[b][a] = cost, cost
    protocol = protocol.upper()
    if protocol not in {"OSPF", "RIP", "BGP"}:
        raise ValueError("支持 RIP、OSPF 或 BGP。")
    if protocol == "BGP":
        return bgp_propagate(graph, {node: nodes[node].get("asn", 65000 + list(nodes).index(node)) for node in nodes})
    tables, events = {}, []
    for source in graph:
        result = bellman_ford(graph, source) if protocol == "RIP" else dijkstra(graph, source)
        tables[source] = []
        for destination, path in result["paths"].items():
            if len(path) < 2:
                continue
            metric = result["distances"][destination]
            if protocol == "RIP" and metric >= 16:
                continue
            as_path = [nodes[node].get("asn", 65000 + list(nodes).index(node)) for node in path]
            tables[source].append({"destination": destination, "next_hop": path[1], "metric": metric,
                                   "path": path, "as_path": as_path if protocol == "BGP" else None})
        for index, step in enumerate(result["steps"]):
            events.append({"time": float(index), "kind": f"{protocol}_UPDATE", "source": source, "target": "",
                           "packet_id": None, "explanation": str(step), "data": step})
    return {"protocol": protocol, "tables": tables, "events": events,
            "note": {"RIP": "同步距离向量轮次；度量 16 表示不可达。未实现 RIP 报文、定时器和 split horizon。",
                     "OSPF": "已知全图后的 SPF 教学计算；未实现邻接状态机、LSA 洪泛和多区域。",
                     "BGP": "简化路径向量模型。"}[protocol]}


def bgp_propagate(graph: dict, asns: dict | None = None) -> dict:
    """Synchronous neighbor path-vector propagation with AS-loop rejection.

    Nodes advertise their own teaching destinations. Consecutive devices in the
    same AS do not lengthen AS_PATH. AS policy, MED and sessions are not modeled.
    """
    graph = _normalize(graph)
    asns = asns or {node: 65000 + index for index, node in enumerate(graph)}
    if set(graph) - set(asns):
        raise ValueError("每个节点都需要一个 ASN。")
    routes = {node: {node: {"destination": node, "next_hop": node, "path": [node],
                            "as_path": [int(asns[node])], "metric": 0}} for node in graph}
    events, steps = [], []
    for iteration in range(1, len(graph) + 1):
        old = {node: {dst: row.copy() for dst, row in table.items()} for node, table in routes.items()}
        updates = []
        for receiver, peers in graph.items():
            for sender in sorted(peers):
                for destination, advertisement in old[sender].items():
                    if receiver in advertisement["path"]:
                        continue
                    as_path = advertisement["as_path"].copy()
                    if int(asns[receiver]) != int(asns[sender]):
                        if int(asns[receiver]) in as_path:
                            events.append({"time": float(iteration), "kind": "BGP_AS_LOOP_REJECT",
                                           "source": sender, "target": receiver, "packet_id": None,
                                           "explanation": f"目的 {destination} 的 AS_PATH 已包含本 AS {asns[receiver]}，拒绝。",
                                           "data": {"destination": destination, "as_path": as_path}})
                            continue
                        as_path.insert(0, int(asns[receiver]))
                    candidate = {"destination": destination, "next_hop": sender,
                                 "path": [receiver, *advertisement["path"]], "as_path": as_path,
                                 "metric": len(as_path) - 1}
                    current = routes[receiver].get(destination)
                    rank = lambda row: (len(row["as_path"]), len(row["path"]), row["next_hop"])
                    if current is None or rank(candidate) < rank(current):
                        routes[receiver][destination] = candidate
                        change = {"receiver": receiver, "sender": sender, **candidate}
                        updates.append(change)
                        events.append({"time": float(iteration), "kind": "BGP_UPDATE", "source": sender,
                                       "target": receiver, "packet_id": None,
                                       "explanation": f"邻居通告 {destination}；选择 AS_PATH {as_path}。", "data": change})
        steps.append({"iteration": iteration, "updates": updates})
        if not updates:
            break
    return {"protocol": "BGP", "tables": {node: [row for dst, row in table.items() if node != dst] for node, table in routes.items()},
            "events": events, "steps": steps,
            "note": "邻居逐轮通告路径、拒绝重复本 AS、按 AS_PATH 长度选路，连续同 AS 去重。每个设备为教学目的节点；未实现 eBGP/iBGP 会话、路由反射、LOCAL_PREF/MED/商业策略；修改链路后从初始通告重算撤回。"}

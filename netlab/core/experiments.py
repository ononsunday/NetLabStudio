"""Cross-module scenarios backed by shared event/packet models.

Every result is a teaching simulation. Domain names and addresses here never
trigger DNS queries, socket connections, packet injection or system changes.
"""
from __future__ import annotations

import math
from urllib.parse import urlsplit

from .events import EventEngine
from .services import DNSResolver, NATTable
from .topology import NetworkSimulator, example_topology
from .transport import simulate_tcp, simulate_quic


def website_experiment(url: str = "https://example.test", transport: str = "TCP", seed: int = 1, **conditions) -> dict:
    parsed = urlsplit(url if "://" in url else "https://" + url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("请输入不带凭据的 HTTP 或 HTTPS 地址。")
    if transport.upper() not in {"TCP", "QUIC"}:
        raise ValueError("传输方式应为 TCP 或 QUIC。")
    if transport.upper() == "QUIC" and parsed.scheme != "https":
        raise ValueError("HTTP/3 使用 QUIC 与 TLS，请选择 HTTPS。")
    engine = EventEngine(seed)
    dns = DNSResolver({parsed.hostname.lower(): {"A": ["203.0.113.10"], "AAAA": ["2001:db8::10"], "TTL": 120}})
    query = dns.query(parsed.hostname)
    elapsed = 0.0
    for step in query["steps"]:
        engine.time = elapsed
        engine.schedule(0, "DNS_STEP", "client", "resolver", explanation=step,
                        data={"name": parsed.hostname, "type": "A", "virtual_address": "203.0.113.10"})
        elapsed += 0.012
    allowed = {key: value for key, value in conditions.items() if key in {
        "bytes_total", "loss", "delay_ms", "jitter_ms", "bandwidth_mbps", "receive_window"}}
    transfer = simulate_tcp(seed=seed, **allowed) if transport.upper() == "TCP" else simulate_quic(seed=seed, **allowed)
    while engine.queue:
        engine.record(engine.pop())
    events = engine.history.copy()
    # Preserve transport ordering while application bytes wait for TLS/request.
    # This is a composed timing model: the inserted TLS markers do not execute crypto.
    established_relative = next((event["time"] for event in transfer["events"]
                                 if event["kind"] == "QUIC_ESTABLISHED" or
                                 event["kind"] == "TCP_STATE" and event.get("data", {}).get("side") == "client"
                                 and event.get("data", {}).get("to") == "ESTABLISHED"), None)
    established = None if established_relative is None else established_relative + elapsed
    delay = conditions.get("delay_ms", 30) / 1000
    tls_delay = 3 * delay if parsed.scheme == "https" and transport.upper() == "TCP" else 0
    application_delay = tls_delay + max(delay, 0.000001)
    http_start = None if established is None else established + tls_delay + 0.00000025
    acknowledgement_relative = next((event["time"] for event in transfer["events"]
                                     if event["kind"] == "ACK_PROGRESS" and event.get("data", {}).get("acked") == transfer["metrics"]["requested_bytes"]), None)
    for event in transfer["events"]:
        fields = event.get("data", {})
        kind, flag = event["kind"], fields.get("flag")
        handshake = flag in {"SYN", "SYN_ACK", "HANDSHAKE_ACK"} or kind in {
            "QUIC_INITIAL", "TLS_HANDSHAKE", "QUIC_ESTABLISHED"}
        handshake = handshake or kind == "TCP_STATE" and fields.get("to") in {"SYN_SENT", "SYN_RECEIVED", "ESTABLISHED"}
        handshake = handshake or kind == "RETRANSMIT_TIMEOUT" and "SYN" in event["explanation"]
        handshake = handshake or kind == "PACKET_LOSS" and "offset" not in fields and fields.get("sequence") in {1000, 7000}
        # QUIC PTO before established belongs to the cryptographic handshake.
        handshake = handshake or kind == "QUIC_PTO" and "index" not in fields
        application = established_relative is not None and not handshake and event["time"] >= established_relative
        shift = application_delay if application else 0
        close = flag in {"FIN", "FIN_ACK", "SERVER_FIN", "LAST_ACK"} or kind == "TIME_WAIT" or (
            kind == "TCP_STATE" and fields.get("to") in {"FIN_WAIT_1", "FIN_WAIT_2", "CLOSE_WAIT", "LAST_ACK", "TIME_WAIT", "CLOSED"})
        if close:
            shift += 0.000001
        events.append({**event, "time": event["time"] + elapsed + shift, "id": "transport-" + event["id"]})
    # TLS markers are derived from establishment and configured propagation delay.
    if established is not None and parsed.scheme == "https" and transport.upper() == "TCP":
        for index, text in enumerate(["ClientHello：支持 TLS 1.3 与密钥交换组", "ServerHello、加密证书消息与 CertificateVerify",
                                      "教学客户端验证虚拟 CA 和域名；Finished 确认握手", "建立受保护应用数据通道"]):
            events.append({"id": f"tls-{index}", "time": established + index * delay, "kind": "TLS13_STEP",
                           "source": "client" if index % 2 == 0 else "server", "target": "server" if index % 2 == 0 else "client",
                           "packet_id": None, "explanation": text, "status": "processed", "data": {"virtual": True, "stage_index": index}})
    if transfer["metrics"]["success"]:
        version = "HTTP/3" if transport.upper() == "QUIC" else "HTTP/1.1"
        if transport.upper() == "TCP":
            response_time = elapsed + acknowledgement_relative + application_delay + 0.00000025
        else:
            response_time = max(event["time"] for event in events if event["kind"] == "STREAM_DELIVER") + 0.00000025
        events.extend([
            {"id": "http-request", "time": http_start, "kind": "HTTP_REQUEST", "source": "client", "target": "server",
             "packet_id": None, "status": "processed", "explanation": f"GET {parsed.path or '/'}；Host: {parsed.hostname}。",
             "data": {"method": "GET", "path": parsed.path or "/", "host": parsed.hostname, "version": version}},
            {"id": "http-response", "time": response_time,
             "kind": "HTTP_RESPONSE", "source": "server", "target": "client", "packet_id": None,
             "status": "processed", "explanation": "教学服务器返回虚拟资源，响应载荷使用传输实验确认字节数。",
             "data": {"status": 200, "virtual": True, "body_bytes": transfer["metrics"]["delivered_bytes"]}},
        ])
    else:
        events.append({"id": "website-failure", "time": elapsed + transfer["metrics"]["duration_ms"] / 1000 + (application_delay if established is not None else 0),
                       "kind": "WEBSITE_FAILURE", "source": "client", "target": "server", "packet_id": None,
                       "status": "failed", "explanation": "传输未完成，因此没有成功的 HTTP 响应。", "data": {}})
    def phase(event):
        if event["kind"] == "DNS_STEP":
            return 0
        if event["kind"] == "TLS_HANDSHAKE":
            return 19  # QUIC crypto becomes usable before QUIC_ESTABLISHED.
        if event["kind"] == "QUIC_ESTABLISHED" or event["kind"] == "TCP_STATE" and event.get("data", {}).get("to") == "ESTABLISHED":
            return 20
        if event["kind"] == "TLS13_STEP":
            return 30 + event["data"]["stage_index"]
        if event["kind"] == "HTTP_REQUEST":
            return 40
        return 50
    events.sort(key=lambda event: (event["time"], phase(event), event.get("order", 0), str(event.get("id"))))
    if established is not None:
        transfer["metrics"] = {**transfer["metrics"], "duration_ms": transfer["metrics"]["duration_ms"] + application_delay * 1000,
                               "goodput_mbps": transfer["metrics"]["delivered_bytes"] * 8 / max(1e-9, transfer["metrics"]["duration_ms"] / 1000 + application_delay) / 1e6}
    return {"mode": "teaching_simulation", "url": parsed.geturl(), "events": events,
            "results": {"dns": query, "transport": transfer["metrics"], "success": transfer["metrics"]["success"]},
            "note": "域名映射至文档示例地址，只在模拟器中使用。TLS/HTTP 是根据建立状态与传播延迟插入的阶段标记；应用字节时序整体等待 TLS/请求，响应在确认后、关闭前。载荷是可靠传输示例，未编码双向 HTTP 请求响应、TLS 密码学、证书或 CDN。"}


def home_experiment(seed: int = 1) -> dict:
    sim = NetworkSimulator.from_dict(example_topology("home"), seed)
    leases = [sim.request_dhcp(client, "R1") for client in ("PC1", "PC2")]
    sim.send("PC1", "PC2")
    sim.send("PC1", "WEB")
    result = sim.run()
    result["results"] = {"leases": leases, "success": result["stats"]["dropped"] == 0}
    return result


def nat_traversal(nat_a: str = "restricted", nat_b: str = "restricted", seed: int = 1) -> dict:
    choices = {"open", "restricted", "symmetric", "cgnat"}
    nat_a, nat_b = nat_a.lower(), nat_b.lower()
    nat_a = "open" if nat_a == "cone" else nat_a
    nat_b = "open" if nat_b == "cone" else nat_b
    if nat_a not in choices or nat_b not in choices:
        raise ValueError("NAT 类型支持 open、restricted、symmetric、cgnat。")
    a = NATTable("203.0.113.1", 40000)
    b = NATTable("198.51.100.1", 45000)
    mappings = [a.outbound("192.168.1.10", 30000), b.outbound("192.168.2.10", 30000)]
    engine = EventEngine(seed)
    engine.schedule(0, "STUN_BINDING_REQUEST", "A/B", "STUN", explanation="双方向教学 STUN 服务发送 Binding 请求。")
    engine.schedule(0.02, "STUN_BINDING_RESPONSE", "STUN", "A/B", explanation="返回服务观察到的映射地址。", data={"mappings": mappings})
    engine.schedule(0.04, "SIGNAL_EXCHANGE", "A", "B", explanation="通过应用信令交换候选地址；STUN 不负责信令。")
    # cgnat models two restrictive layers here; CGNAT itself does not prove traversal impossible.
    direct = nat_a not in {"symmetric", "cgnat"} and nat_b not in {"symmetric", "cgnat"}
    engine.schedule(0.06, "UDP_HOLE_PUNCH", "A/B", "B/A", explanation="同时向对方候选地址发送 UDP，建立 NAT 过滤状态。")
    engine.schedule(0.1 if direct else 0.3, "DIRECT_READY" if direct else "TURN_RELAY", "A/B", "B/A" if direct else "TURN",
                    explanation="模型的候选连通性检查成功。" if direct else "此模型中的端点相关映射或双层限制使直接候选失败，选用中继。")
    while engine.queue:
        engine.record(engine.pop())
    return {"mode": "teaching_simulation", "events": engine.history, "path": "direct" if direct else "relay",
            "mappings": mappings, "extra_latency_ms": 0 if direct else 40,
            "note": "NAT 行为按四种教学配置近似。实际打洞取决于映射/过滤、UDP 支持、超时及多层 NAT；CGNAT 不必然禁止打洞。TURN 不等于免费公开服务器。"}


def game_experiment(delay_ms: float = 80, loss: float = 0.05, seed: int = 1,
                    nat_type: str = "restricted", duration: float = 5, tick_rate: int = 20,
                    jitter_ms: float = 10, interpolation_ms: float = 100) -> dict:
    if not 0 <= delay_ms <= 10000 or not 0 <= loss <= 1 or not 0.5 <= duration <= 30 or not 1 <= tick_rate <= 120:
        raise ValueError("游戏网络参数无效。")
    aliases = {"开放": "open", "受限": "restricted", "对称": "symmetric", "CGNAT": "cgnat"}
    nat_type = aliases.get(nat_type, nat_type.lower())
    traversal = nat_traversal(nat_type, nat_type, seed)
    engine = EventEngine(seed)
    interval = 1 / tick_rate
    effective_delay = delay_ms + traversal["extra_latency_ms"]
    true_position, server_position, predicted, observed = 0.0, 0.0, 0.0, 0.0
    server_tick = -1
    snapshots, rows = [], []
    lost_packets, sent_packets = 0, 0
    for tick in range(int(duration * tick_rate) + 1):
        engine.schedule(tick * interval, "GAME_TICK", "client", "server", data={"tick": tick})
    while engine.queue:
        event = engine.pop()
        if event.kind == "GAME_TICK":
            tick = event.data["tick"]
            velocity = 1.0 if tick * interval < duration / 2 else -1.0
            true_position += velocity * interval
            predicted += velocity * interval
            sent_packets += 1
            if engine.rng.random() < loss:
                lost_packets += 1
                event.explanation = "输入更新丢失；客户端继续本地预测。"
            else:
                latency = max(0, effective_delay + engine.rng.uniform(-jitter_ms, jitter_ms)) / 1000
                engine.schedule(latency, "GAME_INPUT", "client", "server", data={"tick": tick, "position": true_position})
            target_time = engine.time - interpolation_ms / 1000
            earlier = [item for item in snapshots if item[0] <= target_time]
            later = [item for item in snapshots if item[0] > target_time]
            if earlier:
                left = earlier[-1]
                if later:
                    right = later[0]
                    alpha = (target_time - left[0]) / max(right[0] - left[0], 1e-9)
                    observed = left[1] + (right[1] - left[1]) * alpha
                else:
                    observed = left[1]
            rows.append({"time": engine.time, "true": true_position, "predicted": predicted,
                         "server": server_position, "interpolated": observed,
                         "prediction_error": abs(predicted - server_position), "display_error": abs(true_position - observed)})
        elif event.kind == "GAME_INPUT":
            # Ignore stale datagrams; an older update must not roll back authoritative state.
            if event.data["tick"] > server_tick:
                server_tick, server_position = event.data["tick"], event.data["position"]
                sent_packets += 1
                if engine.rng.random() < loss:
                    lost_packets += 1
                    event.explanation = "服务器状态快照丢失。"
                else:
                    latency = max(0, effective_delay + engine.rng.uniform(-jitter_ms, jitter_ms)) / 1000
                    engine.schedule(latency, "GAME_SNAPSHOT", "server", "client", data={"position": server_position, "server_time": engine.time})
        elif event.kind == "GAME_SNAPSHOT":
            snapshots.append((event.data["server_time"], event.data["position"]))
            snapshots.sort()
        engine.record(event)
    return {"mode": "teaching_simulation", "events": traversal["events"] + engine.history,
            "frames": rows, "results": {"path": traversal["path"], "sent_packets": sent_packets,
                                        "lost_packets": lost_packets, "observed_loss": lost_packets / max(sent_packets, 1),
                                        "mean_display_error": sum(row["display_error"] for row in rows) / len(rows),
                                        "one_way_delay_ms": effective_delay},
            "note": "一维移动：客户端本地预测、带序号 UDP 输入、服务器权威状态与插值。未实现碰撞、回滚、输入重放或具体游戏协议。"}


def fault_experiment(fault: str = "gateway", seed: int = 1) -> dict:
    choices = ["gateway", "link", "vlan", "dns", "route"]
    if fault == "random":
        fault = EventEngine(seed).rng.choice(choices)
    if fault not in choices:
        raise ValueError("故障支持 gateway、link、vlan、dns、route、random。")
    topology = example_topology("home")
    answers = {"gateway": "PC1 默认网关地址不存在。", "link": "SW1 与 R1 之间的链路关闭。",
               "vlan": "PC1 交换机端口 VLAN 与路由器端口 VLAN 不一致。", "dns": "虚拟域名没有对应 DNS 记录。",
               "route": "R1 的外网接口配置到错误子网，缺少到 WEB 的路由。"}
    if fault == "gateway":
        topology["nodes"][0]["gateway"] = "192.168.1.254"
    elif fault == "link":
        topology["links"][2]["up"] = False
    elif fault == "vlan":
        topology["nodes"][2]["interfaces"][0]["vlan"] = 20
    elif fault == "route":
        topology["nodes"][3]["interfaces"][1]["ip"] = "198.51.100.1/24"
    sim = NetworkSimulator.from_dict(topology, seed)
    sim.send("PC1", "PC2")
    sim.run()
    local_ok = any(packet["protocol"] == "ICMP" and packet["status"] == "delivered" and packet["current"] == "PC2"
                   for packet in sim.packets.values())
    if fault != "dns":
        sim.send("PC1", "WEB")
        result = sim.run()
    else:
        result = sim.result()
        query = DNSResolver().query("missing.test")
        result["dns"] = query
    result.update(fault=fault, answer=answers[fault],
                  evidence={"local_ping_success": local_ok,
                            "drop_reasons": [event["explanation"] for event in result["events"] if event["kind"] == "DROP"],
                            "arp": sim.topology.nodes["PC1"].arp, "routes": sim.topology.nodes["R1"].routes},
                  steps=["检查设备与端口是否启用", "核对地址/掩码/网关", "Ping 同网段设备", "检查 ARP 与 VLAN", "检查路由表", "查询 DNS"])
    return result


def performance_experiment(packet_size: int = 1024, buffer_size: int = 4096, packets: int = 32,
                           io_mode: str = "interrupt", cpu_mhz: float = 1000,
                           bandwidth_mbps: float = 100, cycles_per_byte: float = 2,
                           interrupt_cycles: int = 3000, **aliases) -> dict:
    io_mode = aliases.get("mode", io_mode)
    if not 64 <= packet_size <= 65535 or buffer_size < packet_size or not 1 <= packets <= 10000 or cpu_mhz <= 0 or bandwidth_mbps <= 0:
        raise ValueError("包大小、缓冲区、数量、CPU 或链路参数无效；缓冲区至少容纳一个包。")
    if io_mode not in {"interrupt", "polling", "batch"}:
        raise ValueError("处理方式支持 interrupt、polling、batch。")
    engine = EventEngine(1)
    buffer_used, cpu_free, processed, dropped, cycles_total = 0, 0.0, 0, 0, 0.0
    wire_interval = packet_size * 8 / (bandwidth_mbps * 1e6)
    for index in range(packets):
        engine.schedule(index * wire_interval, "NIC_RECEIVE", "network", "NIC", packet_id=f"perf-{index}",
                        explanation=f"网卡收到 {packet_size} 字节。")
    batch_size = max(1, min(16, buffer_size // packet_size))
    while engine.queue:
        event = engine.pop()
        if event.kind == "NIC_RECEIVE":
            if buffer_used + packet_size > buffer_size:
                dropped += 1
                event.explanation = "Socket/接收环教学缓冲区已满，丢包。"
                event.status = "dropped"
            else:
                buffer_used += packet_size
                base_cycles = cycles_per_byte * packet_size
                overhead = interrupt_cycles if io_mode == "interrupt" else interrupt_cycles / batch_size if io_mode == "batch" else 500
                cycles = base_cycles + overhead
                cycles_total += cycles
                start = max(cpu_free, engine.time)
                if io_mode == "polling":
                    # A polling interval has latency; idle polling cost is counted separately below.
                    start = max(start, math.ceil(engine.time / 0.0001) * 0.0001)
                elapsed = cycles / (cpu_mhz * 1e6)
                cpu_free = start + elapsed
                engine.schedule(0, "DMA_WRITE", "NIC", "memory", event.packet_id,
                                "DMA 将数据写入接收缓冲区，CPU 无需逐字节搬运。", {"buffer_used": buffer_used})
                engine.schedule(start - engine.time, "OS_DISPATCH", "OS", "CPU", event.packet_id,
                                "中断处理" if io_mode == "interrupt" else "批量处理，开销按批次摊销" if io_mode == "batch" else "轮询发现可用数据",
                                {"cycles": cycles, "buffer_used": buffer_used})
                engine.schedule(cpu_free - engine.time, "APP_RECEIVE", "kernel", "application", event.packet_id,
                                "协议栈处理完成，应用读取数据。")
        elif event.kind == "APP_RECEIVE":
            buffer_used -= packet_size
            processed += 1
        engine.record(event)
    duration = max(engine.time, wire_interval)
    polling_cycles = math.ceil(duration / 0.0001) * 200 if io_mode == "polling" else 0
    cycles_total += polling_cycles
    return {"mode": "teaching_simulation", "events": engine.history,
            "results": {"packet_size": packet_size, "buffer_size": buffer_size, "processed": processed, "dropped": dropped,
                        "duration_ms": duration * 1000, "cpu_cycles": cycles_total,
                        "cpu_utilization": min(1, cycles_total / (cpu_mhz * 1e6 * duration)),
                        "throughput_mbps": processed * packet_size * 8 / duration / 1e6, "io_mode": io_mode},
            "note": "单核串行处理与有限缓冲区模型，固定每字节/中断开销；批处理开销摊销为近似。真实吞吐还受 RSS、卸载、缓存、驱动和调度影响。"}

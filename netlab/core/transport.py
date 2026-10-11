"""Stateful transport experiments generated from network conditions and timers.

TCP is a Reno-style teaching model (not a conformant replacement TCP stack).
QUIC represents streams and recovery, not wire encryption or a production stack.
"""
from __future__ import annotations

import math
import struct

from .events import EventEngine


def _validate(bytes_total, loss, delay_ms, jitter_ms, bandwidth_mbps, receive_window=4096):
    if not isinstance(bytes_total, int) or not 1 <= bytes_total <= 4_000_000:
        raise ValueError("传输大小应为 1 至 4000000 字节。")
    if any(not math.isfinite(value) for value in (loss, delay_ms, jitter_ms, bandwidth_mbps)) or not 0 <= loss <= 1 or not 0 <= delay_ms <= 10000 or not 0 <= jitter_ms <= 10000 or bandwidth_mbps <= 0:
        raise ValueError("丢包、时延、抖动或带宽参数无效。")
    if not isinstance(receive_window, int) or not 64 <= receive_window <= 16_777_216:
        raise ValueError("接收窗口应为 64 至 16777216 字节。")


class _TCP:
    def __init__(self, bytes_total, loss, delay_ms, jitter_ms, bandwidth_mbps, receive_window, seed):
        _validate(bytes_total, loss, delay_ms, jitter_ms, bandwidth_mbps, receive_window)
        self.total, self.loss = bytes_total, loss
        self.delay, self.jitter, self.bandwidth = delay_ms / 1000, jitter_ms / 1000, bandwidth_mbps * 1e6
        self.rwnd, self.mss = receive_window, min(512, receive_window)
        self.engine = EventEngine(seed)
        self.states = {"client": "CLOSED", "server": "LISTEN"}
        self.state_history, self.window_history = [], []
        self.ready = {"client": 0.0, "server": 0.0}
        self.next_sequence = 0
        self.acknowledged = 0
        self.received: dict[int, int] = {}
        self.receive_next = 0
        self.outstanding: dict[int, dict] = {}
        self.cwnd, self.ssthresh = float(self.mss), float(64 * self.mss)
        self.srtt, self.rttvar, self.rto = None, None, max(0.2, self.delay * 4 + self.jitter * 4)
        self.duplicate_ack = 0
        self.fast_recovery = False
        self.transmissions, self.drops, self.retransmissions = 0, 0, 0
        self.controls: dict[str, int] = {}
        self.finished = None
        self.failed = False
        self.app_start = None

    def note(self, kind, source="", target="", text="", data=None):
        self.engine.schedule(0, kind, source, target, explanation=text, data=data)

    def state(self, side, new):
        old = self.states[side]
        if old == new:
            return
        self.states[side] = new
        row = {"time": self.engine.time, "side": side, "from": old, "to": new}
        self.state_history.append(row)
        self.note("TCP_STATE", side, text=f"{side}: {old} → {new}", data=row)

    def wire(self, kind, side, fields=None):
        fields = fields or {}
        target = "server" if side == "client" else "client"
        size = fields.get("size", 0) + 40
        now = self.engine.time
        start = max(now, self.ready[side])
        self.ready[side] = start + size * 8 / self.bandwidth
        delay = start - now + size * 8 / self.bandwidth + max(0.000001, self.delay + self.engine.rng.uniform(-self.jitter, self.jitter))
        self.transmissions += 1
        self.note("TCP_SEND", side, target, f"发送 {kind}，SEQ={fields.get('sequence', 1000)} ACK={fields.get('ack', 0)}。",
                  {"flag": kind, **fields, "cwnd": round(self.cwnd), "rwnd": self.rwnd, "rto": self.rto})
        if self.engine.rng.random() < self.loss:
            self.drops += 1
            self.engine.schedule(delay, "PACKET_LOSS", side, target, explanation=f"{kind} 在链路中丢失。", data=fields)
        else:
            self.engine.schedule(delay, "TCP_ARRIVE", side, target, explanation=f"{kind} 到达。", data={"flag": kind, **fields})

    def control(self, flag, side, fields=None):
        attempt = self.controls.get(flag, 0) + 1
        self.controls[flag] = attempt
        if attempt > 10:
            self.failed = True
            self.state(side, "CLOSED")
            self.note("TCP_ABORT", side, text="控制报文重试达到上限，连接失败。")
            return
        if attempt > 1:
            self.retransmissions += 1
        self.wire(flag, side, fields)
        self.engine.schedule(self.rto * min(2 ** (attempt - 1), 8), "CONTROL_TIMEOUT", side,
                             data={"flag": flag, "attempt": attempt, "fields": fields or {}})

    def data_send(self, sequence, retransmit=False):
        if retransmit:
            row = self.outstanding[sequence]
            row["attempt"] += 1
            row["retransmitted"] = True
            self.retransmissions += 1
        else:
            row = {"size": min(self.mss, self.total - sequence), "sent_at": self.engine.time,
                   "attempt": 1, "retransmitted": False}
            self.outstanding[sequence] = row
        if row["attempt"] > 10:
            self.failed = True
            self.note("TCP_ABORT", "client", text="数据重传达到上限，连接失败。")
            return
        self.wire("DATA", "client", {"sequence": 1001 + sequence, "offset": sequence, "size": row["size"],
                                     "attempt": row["attempt"]})
        self.engine.schedule(self.rto * min(2 ** (row["attempt"] - 1), 8), "DATA_TIMEOUT", "client",
                             data={"offset": sequence, "attempt": row["attempt"]})

    def fill(self):
        if self.failed or self.states["client"] != "ESTABLISHED":
            return
        flight = sum(row["size"] for row in self.outstanding.values())
        window = min(self.cwnd, self.rwnd)
        while self.next_sequence < self.total:
            size = min(self.mss, self.total - self.next_sequence)
            if flight + size > window:
                break
            sequence = self.next_sequence
            self.next_sequence += size
            self.data_send(sequence)
            flight += size
        self.window_history.append({"time": self.engine.time, "cwnd": self.cwnd, "rwnd": self.rwnd,
                                    "in_flight": flight, "acked": self.acknowledged, "rto": self.rto})

    def arrival(self, event):
        flag, data = event.data["flag"], event.data
        if flag == "SYN":
            if self.states["server"] == "LISTEN":
                self.state("server", "SYN_RECEIVED")
            if self.states["server"] == "SYN_RECEIVED":
                self.control("SYN_ACK", "server", {"sequence": 7000, "ack": 1001})
        elif flag == "SYN_ACK":
            if self.states["client"] in {"SYN_SENT", "ESTABLISHED"}:
                self.controls.pop("SYN", None)
                self.state("client", "ESTABLISHED")
                self.wire("HANDSHAKE_ACK", "client", {"sequence": 1001, "ack": 7001})
                if self.app_start is None:
                    self.app_start = self.engine.time
                    self.fill()
        elif flag == "HANDSHAKE_ACK":
            self.controls.pop("SYN_ACK", None)
            if self.states["server"] == "SYN_RECEIVED":
                self.state("server", "ESTABLISHED")
        elif flag == "DATA":
            if self.states["server"] == "SYN_RECEIVED":
                self.controls.pop("SYN_ACK", None)
                self.state("server", "ESTABLISHED")
            offset, size = data["offset"], data["size"]
            if offset >= self.receive_next and offset + size <= self.receive_next + self.rwnd:
                self.received[offset] = size
            while self.receive_next in self.received:
                self.receive_next += self.received.pop(self.receive_next)
            self.wire("ACK", "server", {"sequence": 7001, "ack": 1001 + self.receive_next, "offset": self.receive_next})
        elif flag == "ACK":
            self.ack(data["offset"])
        elif flag == "FIN":
            if self.states["server"] == "ESTABLISHED":
                self.state("server", "CLOSE_WAIT")
                self.wire("FIN_ACK", "server", {"ack": 1002 + self.total})
                self.state("server", "LAST_ACK")
                self.control("SERVER_FIN", "server", {"sequence": 7001, "ack": 1002 + self.total})
            elif self.states["server"] == "LAST_ACK":
                self.wire("FIN_ACK", "server", {"ack": 1002 + self.total})
        elif flag == "FIN_ACK":
            self.controls.pop("FIN", None)
            if self.states["client"] == "FIN_WAIT_1":
                self.state("client", "FIN_WAIT_2")
        elif flag == "SERVER_FIN":
            self.controls.pop("FIN", None)
            self.state("client", "TIME_WAIT")
            self.wire("LAST_ACK", "client", {"ack": 7002, "sequence": 1002 + self.total})
        elif flag == "LAST_ACK":
            self.controls.pop("SERVER_FIN", None)
            self.state("server", "CLOSED")
            self.finished = self.engine.time
            self.note("TIME_WAIT", "client", text="保持 TIME_WAIT 以处理重复 FIN；真实等待与 MSL 有关，本实验不按真实秒数等待。")
            self.state("client", "CLOSED")

    def ack(self, offset):
        if offset > self.acknowledged:
            acknowledged = [seq for seq, row in self.outstanding.items() if seq + row["size"] <= offset]
            newly_acked = offset - self.acknowledged
            sample = None
            for seq in acknowledged:
                row = self.outstanding.pop(seq)
                if not row["retransmitted"]:
                    sample = self.engine.time - row["sent_at"]
            if sample is not None:
                if self.srtt is None:
                    self.srtt, self.rttvar = sample, sample / 2
                else:
                    self.rttvar = 0.75 * self.rttvar + 0.25 * abs(self.srtt - sample)
                    self.srtt = 0.875 * self.srtt + 0.125 * sample
                self.rto = max(0.2, self.srtt + max(0.001, 4 * self.rttvar))
            self.acknowledged, self.duplicate_ack = offset, 0
            if self.fast_recovery:
                self.cwnd, self.fast_recovery = self.ssthresh, False
                self.note("FAST_RECOVERY_END", "client", text="新 ACK 到达，cwnd 回到 ssthresh。")
            elif self.cwnd < self.ssthresh:
                self.cwnd += min(newly_acked, self.mss)
            else:
                self.cwnd += self.mss * self.mss / self.cwnd
            self.note("ACK_PROGRESS", "client", text=f"累计确认 {offset}/{self.total} 字节；cwnd={self.cwnd:.0f}。",
                      data={"acked": offset, "cwnd": self.cwnd, "srtt": self.srtt, "rto": self.rto})
            if offset >= self.total:
                self.state("client", "FIN_WAIT_1")
                self.control("FIN", "client", {"sequence": 1001 + self.total, "ack": 7001})
            else:
                self.fill()
        elif offset == self.acknowledged and self.outstanding:
            self.duplicate_ack += 1
            if self.duplicate_ack == 3:
                self.ssthresh = max(2 * self.mss, sum(row["size"] for row in self.outstanding.values()) / 2)
                self.cwnd, self.fast_recovery = self.ssthresh + 3 * self.mss, True
                self.note("FAST_RETRANSMIT", "client", text="三个重复 ACK：重传最早未确认段，进入快速恢复。")
                self.data_send(min(self.outstanding), True)
            elif self.fast_recovery:
                self.cwnd += self.mss
                self.fill()

    def run(self):
        self.state("client", "SYN_SENT")
        self.control("SYN", "client", {"sequence": 1000})
        for _ in range(150000):
            event = self.engine.pop()
            if event is None or self.failed:
                break
            if event.kind == "TCP_ARRIVE":
                self.arrival(event)
            elif event.kind == "CONTROL_TIMEOUT":
                flag = event.data["flag"]
                if self.controls.get(flag) == event.data["attempt"]:
                    self.note("RETRANSMIT_TIMEOUT", event.source, text=f"{flag} 超时，指数退避重传。")
                    self.control(flag, event.source, event.data["fields"])
            elif event.kind == "DATA_TIMEOUT":
                row = self.outstanding.get(event.data["offset"])
                if row and row["attempt"] == event.data["attempt"]:
                    self.ssthresh = max(2 * self.mss, sum(row["size"] for row in self.outstanding.values()) / 2)
                    self.cwnd, self.fast_recovery = float(self.mss), False
                    self.note("RETRANSMIT_TIMEOUT", "client", text="RTO 超时，cwnd 回到 1 MSS，进入慢启动。")
                    self.data_send(event.data["offset"], True)
            self.engine.record(event)
            if self.finished is not None:
                while self.engine.queue and self.engine.queue[0].time <= self.engine.time:
                    self.engine.record(self.engine.pop())
                break
        if self.finished is None and not self.failed and self.engine.queue:
            self.failed = True
        duration = self.finished if self.finished is not None else self.engine.time
        return {"protocol": "TCP", "mode": "teaching_simulation", "events": self.engine.history,
                "states": self.states, "state_history": self.state_history, "window_history": self.window_history,
                "metrics": {"requested_bytes": self.total, "delivered_bytes": self.receive_next,
                            "acknowledged_bytes": self.acknowledged, "duration_ms": duration * 1000,
                            "goodput_mbps": self.acknowledged * 8 / max(duration, 1e-9) / 1e6,
                            "transmissions": self.transmissions, "lost_packets": self.drops,
                            "retransmissions": self.retransmissions, "srtt_ms": None if self.srtt is None else self.srtt * 1000,
                            "rto_ms": self.rto * 1000, "success": self.finished is not None and not self.failed},
                "note": "Reno 风格模型：累计 ACK、滑动窗口、慢启动、拥塞避免、快速重传/恢复及 Karn RTT 采样。未实现 SACK、延迟 ACK、Keepalive 探测和生产 TCP 的全部状态；TIME_WAIT 不按真实 MSL 等待。"}


def simulate_tcp(bytes_total: int = 8192, loss: float = 0.05, delay_ms: float = 30, jitter_ms: float = 5,
                 bandwidth_mbps: float = 10, receive_window: int = 4096, seed: int = 1) -> dict:
    return _TCP(bytes_total, loss, delay_ms, jitter_ms, bandwidth_mbps, receive_window, seed).run()


def internet_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return (~total) & 0xffff


def simulate_udp(bytes_total: int = 8192, loss: float = 0.05, delay_ms: float = 30, jitter_ms: float = 5,
                 bandwidth_mbps: float = 10, seed: int = 1, reliable: bool = False,
                 datagram_size: int = 512, **unused) -> dict:
    _validate(bytes_total, loss, delay_ms, jitter_ms, bandwidth_mbps)
    if not 1 <= datagram_size <= 1400:
        raise ValueError("数据报载荷应为 1 至 1400 字节。")
    engine, ready, arrivals = EventEngine(seed), 0.0, {}
    transmissions, lost, retries = 0, 0, 0
    count = math.ceil(bytes_total / datagram_size)
    outstanding = {number: {"size": min(datagram_size, bytes_total - number * datagram_size), "attempt": 0}
                   for number in range(count)}
    def send(number):
        nonlocal ready, transmissions, lost, retries
        row = outstanding[number]
        row["attempt"] += 1
        transmissions += 1
        if row["attempt"] > 1:
            retries += 1
        start = max(ready, engine.time)
        serialization = (row["size"] + 28) * 8 / (bandwidth_mbps * 1e6)
        ready = start + serialization
        elapsed = start - engine.time + serialization + max(0.000001, delay_ms + engine.rng.uniform(-jitter_ms, jitter_ms)) / 1000
        engine.schedule(0, "UDP_SEND", "client", "server", explanation=f"独立数据报 #{number}，尝试 {row['attempt']}。",
                        data={"number": number, "size": row["size"], "attempt": row["attempt"],
                              "payload_checksum": internet_checksum(bytes([number % 256]) * row["size"])})
        if engine.rng.random() < loss:
            lost += 1
            engine.schedule(elapsed, "PACKET_LOSS", "client", "server", explanation=f"数据报 #{number} 丢失。")
        else:
            engine.schedule(elapsed, "UDP_RECEIVE", "client", "server", data={"number": number, "size": row["size"]},
                            explanation=f"数据报 #{number} 到达。")
        if reliable and row["attempt"] < 8:
            engine.schedule(max(0.2, 4 * (delay_ms + jitter_ms) / 1000), "APP_TIMEOUT", "client",
                            data={"number": number, "attempt": row["attempt"]})
    for number in outstanding:
        send(number)
    sequence, delivered, finish = [], 0, 0.0
    while engine.queue:
        event = engine.pop()
        if event.kind == "UDP_RECEIVE":
            number = event.data["number"]
            if number not in arrivals:
                arrivals[number] = engine.time
                sequence.append(number)
                delivered += event.data["size"]
                finish = engine.time
            if reliable:
                # Application acknowledgments are themselves sent over the modeled lossy network.
                if engine.rng.random() >= loss:
                    engine.schedule(delay_ms / 1000, "APP_ACK", "server", "client", data={"number": number},
                                    explanation=f"应用层确认 #{number}。")
        elif event.kind == "APP_ACK":
            outstanding[event.data["number"]]["acknowledged"] = True
        elif event.kind == "APP_TIMEOUT":
            row = outstanding[event.data["number"]]
            if not row.get("acknowledged") and row["attempt"] == event.data["attempt"]:
                send(event.data["number"])
        engine.record(event)
    out_of_order = sum(1 for index, value in enumerate(sequence) if value < max(sequence[:index], default=-1))
    return {"protocol": "UDP", "mode": "teaching_simulation", "events": engine.history,
            "arrival_order": sequence, "states": {"connection": "无连接"},
            "metrics": {"requested_bytes": bytes_total, "delivered_bytes": delivered, "duration_ms": finish * 1000,
                        "goodput_mbps": delivered * 8 / max(finish, 1e-9) / 1e6,
                        "transmissions": transmissions, "lost_packets": lost, "retransmissions": retries,
                        "out_of_order": out_of_order, "delivery_ratio": delivered / bytes_total,
                        "success": delivered == bytes_total},
            "note": "UDP 本身不重传；reliable=True 启用应用层超时/确认/去重，最多尝试 8 次。payload_checksum 为载荷演示，完整 UDP 校验和还包含伪首部与 UDP 首部。"}


def simulate_quic(bytes_total: int = 8192, loss: float = 0.05, delay_ms: float = 30, jitter_ms: float = 5,
                  bandwidth_mbps: float = 10, seed: int = 1, streams: int = 3,
                  migrate_at: int | None = 4, **unused) -> dict:
    _validate(bytes_total, loss, delay_ms, jitter_ms, bandwidth_mbps)
    if not 1 <= streams <= 32:
        raise ValueError("流数量应为 1 至 32。")
    engine = EventEngine(seed)
    events, packet_number, lost, retransmissions = [], 0, 0, 0
    ready, finish = 0.0, 0.0
    delivered = [0] * streams
    attempts = {}
    def record(kind, time, source, target, explanation, data=None):
        engine.time = time
        event = engine.schedule(0, kind, source, target, explanation=explanation, data=data)
        # Keep scheduler queue reserved for transport arrivals.
        engine.queue.remove(event)
        import heapq
        heapq.heapify(engine.queue)
        events.append(event.to_dict() | {"status": "processed"})
    # Handshake packets use loss/retry, rather than displaying unconditional success.
    handshake_ok = False
    handshake_time = 0.0
    for attempt in range(1, 9):
        record("QUIC_INITIAL", handshake_time, "client", "server", "Initial 中携带 TLS 1.3 ClientHello；尚未建立连接。", {"attempt": attempt})
        if engine.rng.random() < loss or engine.rng.random() < loss:
            lost += 1
            retransmissions += 1
            handshake_time += max(0.2, 4 * delay_ms / 1000) * 2 ** min(attempt - 1, 4)
            record("QUIC_PTO", handshake_time, "client", "server", "握手探测超时，重新发送加密握手数据。")
        else:
            handshake_time += 2 * delay_ms / 1000
            record("TLS_HANDSHAKE", handshake_time, "server", "client", "教学标记：TLS 验证身份并协商密钥；不执行密码运算。")
            record("QUIC_ESTABLISHED", handshake_time, "client", "server", "1-RTT 密钥可用，打开独立数据流。")
            handshake_ok = True
            break
    ready = handshake_time
    segments = []
    offset = 0
    while offset < bytes_total:
        size = min(512, bytes_total - offset)
        segments.append((len(segments) % streams, offset, size))
        offset += size
    stream_buffer = {stream: {} for stream in range(streams)}
    stream_order = {stream: [index for index, row in enumerate(segments) if row[0] == stream] for stream in range(streams)}
    stream_cursor = [0] * streams
    migration_done = False
    completed = set()
    def send(index):
        nonlocal packet_number, lost, retransmissions, ready, migration_done
        stream, offset, size = segments[index]
        attempt = attempts.get(index, 0) + 1
        attempts[index] = attempt
        if attempt > 1:
            retransmissions += 1
        packet_number += 1
        start = max(engine.time, ready)
        serialization = (size + 48) * 8 / (bandwidth_mbps * 1e6)
        ready = start + serialization
        arrival = ready + max(0.000001, delay_ms + engine.rng.uniform(-jitter_ms, jitter_ms)) / 1000
        if migrate_at is not None and packet_number >= migrate_at and not migration_done:
            migration_done = True
            record("PATH_CHALLENGE", start, "client", "server", "连接 ID 保持；新路径发送 PATH_CHALLENGE。")
            record("PATH_RESPONSE", start + 2 * delay_ms / 1000, "server", "client", "教学近似：路径验证成功后继续同一连接；验证包本身未单独建模丢包。")
        record("QUIC_STREAM_SEND", start, "client", "server", f"STREAM {stream}；新包号 {packet_number}。",
               {"stream_id": stream, "packet_number": packet_number, "offset": offset, "size": size, "attempt": attempt})
        engine.time = start
        if engine.rng.random() < loss:
            lost += 1
            record("PACKET_LOSS", arrival, "client", "server", f"包号 {packet_number} 丢失；流数据将以新包号重发。")
            if attempt < 8:
                engine.time = start
                engine.schedule(max(0.2, 4 * (delay_ms + jitter_ms) / 1000), "QUIC_PTO", data={"index": index})
        else:
            engine.time = start
            engine.schedule(arrival - start, "QUIC_RECEIVE", "client", "server", data={"index": index})
    if handshake_ok:
        engine.time = handshake_time
        for index in range(len(segments)):
            send(index)
        while engine.queue:
            event = engine.pop()
            events.append(event.to_dict() | {"status": "processed"})
            index = event.data["index"]
            stream, _, size = segments[index]
            if event.kind == "QUIC_PTO":
                if index not in completed:
                    send(index)
            else:
                completed.add(index)
                stream_buffer[stream][index] = size
                order = stream_order[stream]
                while stream_cursor[stream] < len(order) and order[stream_cursor[stream]] in stream_buffer[stream]:
                    delivered[stream] += stream_buffer[stream].pop(order[stream_cursor[stream]])
                    stream_cursor[stream] += 1
                finish = max(finish, engine.time)
                record("STREAM_DELIVER", engine.time, "server", "application",
                       f"流 {stream} 交付连续数据，其他流不等待本流缺口。", {"stream_id": stream, "delivered": delivered[stream]})
    events.sort(key=lambda event: (event["time"], event["order"]))
    total_delivered = sum(delivered)
    return {"protocol": "QUIC", "mode": "teaching_simulation", "events": events,
            "states": {"connection": "ESTABLISHED" if handshake_ok else "HANDSHAKE_FAILED"},
            "stream_bytes": delivered,
            "metrics": {"requested_bytes": bytes_total, "delivered_bytes": total_delivered,
                        "duration_ms": max(finish, handshake_time) * 1000,
                        "goodput_mbps": total_delivered * 8 / max(finish, handshake_time, 1e-9) / 1e6,
                        "transmissions": packet_number, "lost_packets": lost, "retransmissions": retransmissions,
                        "success": total_delivered == bytes_total},
            "note": "教学模型：TLS 1.3 集成、包号与流偏移分离、独立流交付、PTO 和迁移。未实现 QUIC 编码、拥塞控制、0-RTT、真实加密或 HTTP/3 QPACK。与 TCP 的吞吐量不能作为真实实现的性能排名。"}


def compare_transports(**conditions) -> dict:
    allowed = {key: value for key, value in conditions.items() if key in {
        "bytes_total", "loss", "delay_ms", "jitter_ms", "bandwidth_mbps", "seed"}}
    results = [simulate_tcp(**allowed), simulate_udp(**allowed), simulate_quic(**allowed)]
    return {"results": results, "note": "模型的传输策略不同；比较用于观察可靠性、时序和流阻塞，不构成生产环境速度结论。"}


def simulate_connection_control(action: str = "keepalive", idle_seconds: float = 30,
                                interval_seconds: float = 10, probe_count: int = 3,
                                loss: float = 0, delay_ms: float = 30, seed: int = 1,
                                peer_alive: bool = True, valid_sequence: bool = True) -> dict:
    """Keepalive timeout or RST state transition of an already established pair."""
    if action not in {"keepalive", "reset"} or not 1 <= probe_count <= 20 or idle_seconds < 0 or interval_seconds <= 0:
        raise ValueError("控制动作、探测数量或时间间隔无效。")
    _validate(1, loss, delay_ms, 0, 1)
    engine, states = EventEngine(seed), {"client": "ESTABLISHED", "server": "ESTABLISHED"}
    acknowledged, probes = False, 0
    if action == "reset":
        engine.schedule(0, "TCP_RST_SEND", "server", "client", explanation="发送 RST。",
                        data={"sequence": 7001 if valid_sequence else 999999, "valid_sequence": valid_sequence})
        if engine.rng.random() >= loss:
            engine.schedule(delay_ms / 1000, "TCP_RST_ACCEPT" if valid_sequence else "TCP_CHALLENGE_ACK", "client", "server",
                            explanation="RST 序列号通过教学检查，立即关闭连接。" if valid_sequence else "RST 不匹配当前接收序列；教学模型保留连接并发送 challenge ACK。")
            if valid_sequence:
                states = {"client": "CLOSED", "server": "CLOSED"}
        else:
            engine.schedule(delay_ms / 1000, "PACKET_LOSS", "server", "client", explanation="RST 丢失，远端尚不知道连接已被重置。")
            states["server"] = "CLOSED"
    else:
        for probe in range(probe_count):
            engine.schedule(idle_seconds + probe * interval_seconds, "KEEPALIVE_TIMER", "client", "server",
                            data={"probe": probe + 1})
        engine.schedule(idle_seconds + probe_count * interval_seconds, "KEEPALIVE_ABORT_TIMER", "client", "server")
    while engine.queue:
        event = engine.pop()
        if event.kind == "KEEPALIVE_TIMER":
            if acknowledged:
                continue
            probes += 1
            event.explanation = f"空闲后发送探测 #{probes}，SEQ=SND.NXT−1；不推进发送序号。"
            event.data.update(sequence=1000, next_sequence=1001)
            if peer_alive and engine.rng.random() >= loss and engine.rng.random() >= loss:
                engine.schedule(2 * delay_ms / 1000, "KEEPALIVE_ACK", "server", "client",
                                explanation="对端 ACK 1001，确认连接仍可达。", data={"ack": 1001})
            else:
                engine.schedule(delay_ms / 1000, "KEEPALIVE_NO_REPLY", "client", "server",
                                explanation="对端不在线，或探测/ACK 在模型链路中丢失。")
        elif event.kind == "KEEPALIVE_ACK":
            acknowledged = True
            engine.queue.clear()
        elif event.kind == "KEEPALIVE_ABORT_TIMER" and not acknowledged:
            states["client"] = "CLOSED"
            event.explanation = "连续探测无回复，客户端报告连接超时并关闭。远端状态无法由此判断。"
            if not peer_alive:
                states["server"] = "UNREACHABLE"
        engine.record(event)
    return {"protocol": "TCP", "mode": "teaching_simulation", "states": states, "events": engine.history,
            "metrics": {"action": action, "probes": probes, "keepalive_acknowledged": acknowledged,
                        "duration_ms": engine.time * 1000},
            "note": "已建立连接的控制实验；Keepalive 默认与时序因操作系统配置而异，探测不能证明应用健康。RST 使用序列号是否有效的简化输入，未实现完整 RFC 5961 窗口检查。"}

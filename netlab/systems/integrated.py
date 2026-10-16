"""CPU message bytes traverse the shared network state, with conditional echo."""
from __future__ import annotations

import copy

from .cpu import CPU
from .os import network_pipeline


DEFAULT_NETWORK_ASSEMBLY = "MOV R0, 72\nSTORE 10, R0\nMOV R0, 105\nSTORE 11, R0\nSEND 10, 2\nHALT"


def cpu_network_experiment(assembly: str = DEFAULT_NETWORK_ASSEMBLY, topology: dict | None = None,
                           source: str = "PC1", target: str = "WEB", seed: int = 1,
                           max_steps: int = 1000, receive_address: int = 128) -> dict:
    """Run assembly, send each SEND message as virtual UDP, echo only after delivery.

    CPU message bytes are hex-encoded as textual UDP payload so arbitrary bytes
    remain lossless through the topology's text payload API. Encoded-byte overhead
    is included in that API's packet size; this is an application framing choice.
    Nothing here calls a socket, resolver, Scapy injection, or system command.
    """
    from netlab.core.topology import NetworkSimulator, example_topology

    cpu = CPU(receive_policy="external")
    if not isinstance(receive_address, int) or not 0 <= receive_address < cpu.memory_size:
        raise ValueError("接收内存地址超出教学 CPU 内存")
    cpu.load(assembly)
    if not isinstance(max_steps, int) or not 1 <= max_steps <= 100_000:
        raise ValueError("步数上限必须为 1 到 100000")
    simulator = NetworkSimulator.from_dict(copy.deepcopy(topology or example_topology("home")), seed)
    if source not in simulator.topology.nodes or target not in simulator.topology.nodes:
        raise ValueError("综合实验的源与目标设备必须存在于虚拟拓扑")
    cpu_events, receive_events, outcomes = [], [], []
    event_budget = 100_000
    blocked, executed_steps, cpu_wall_time = False, 0, 0.0

    def until_packet_done(packet_id):
        nonlocal event_budget
        packet = simulator.packets[packet_id]
        while event_budget > 0 and simulator.engine.queue and packet["status"] not in ("delivered", "dropped"):
            simulator.step()
            event_budget -= 1
        return packet["status"] == "delivered"

    def outgoing_messages():
        nonlocal blocked, executed_steps, cpu_wall_time
        while executed_steps < max_steps and not cpu.halted:
            if not 0 <= cpu.pc < len(cpu.program):
                cpu.halted = True
                break
            instruction = cpu.program[cpu.pc]
            if instruction["op"] == "RECV" and not cpu.receive_queue:
                blocked = True
                cpu_events.append({"id": "cpu-receive-block", "time": max(cpu_wall_time, simulator.engine.time),
                                   "kind": "os.block", "source": source + ":application", "target": source + ":socket-buffer",
                                   "packet_id": None, "status": "blocked",
                                   "explanation": "RECV 没有已到达的虚拟消息；应用阻塞，没有伪造回环接收。",
                                   "data": {"pc": cpu.pc}, "teaching_model": True})
                break
            event_start, previous_cycles = len(cpu.events), cpu.cycles
            wall_start = max(cpu_wall_time, simulator.engine.time)
            sent_count = len(cpu.sent_messages)
            cpu.step()
            executed_steps += 1
            for event in cpu.events[event_start:]:
                event = copy.deepcopy(event)
                event["time"] = wall_start + event["time"] - previous_cycles / 1000
                cpu_events.append(event)
            cpu_wall_time = wall_start + (cpu.cycles - previous_cycles) / 1000
            if len(cpu.sent_messages) > sent_count:
                yield sent_count, cpu.sent_messages[-1]

    for index, message in outgoing_messages():
        payload = bytes.fromhex(message["payload_hex"])
        if len(payload) > cpu.memory_size - receive_address:
            raise ValueError("接收缓冲区不能容纳该消息；请降低接收起始地址")
        sent_event = next(event for event in cpu_events if event["kind"] == "network.send" and event["packet_id"] == message["id"])
        simulator.engine.time = max(simulator.engine.time, sent_event["time"])
        packet_id = simulator.send(source, target, "UDP", payload.hex(),
                                   source_port=50000 + index % 10000, destination_port=7)
        simulator.packets[packet_id]["cpu_message_id"] = message["id"]
        simulator.packets[packet_id]["payload_encoding"] = "hex"
        for event in cpu_events:
            if event["packet_id"] == message["id"]:
                event["packet_id"] = packet_id
                event["data"]["cpu_message_id"] = message["id"]
        outcome = {"message_id": message["id"], "request_packet_id": packet_id,
                   "sent_hex": payload.hex(), "sent_bytes": len(payload), "delivered": False,
                   "echo_received": False, "receive_address": receive_address}
        if until_packet_done(packet_id):
            packet = simulator.packets[packet_id]
            outcome["delivered"] = packet["current"] == target
            if outcome["delivered"]:
                # Send to the source IP and port observed at the server, not to a
                # guessed private client address. A NAT return mapping is exercised.
                simulator.engine.schedule(0, "APPLICATION_ECHO", target, source, packet_id,
                                          "教学 UDP 回显服务收到消息后原样返回；消息字节采用十六进制文本编码。",
                                          {"payload_hex": payload.hex(), "payload_encoding": "hex"})
                reply_id = simulator.send(target, packet["source_ip"], "UDP", packet["payload"],
                                           source_port=packet["destination_port"], destination_port=packet["source_port"])
                simulator.packets[reply_id].update(reply_to=packet_id, cpu_message_id=message["id"], payload_encoding="hex")
                outcome["reply_packet_id"] = reply_id
                if until_packet_done(reply_id):
                    reply = simulator.packets[reply_id]
                    if reply["current"] == source:
                        received = bytes.fromhex(reply["payload"])
                        outcome["received_hex"] = received.hex()
                        outcome["echo_received"] = received == payload
                        cpu.memory[receive_address:receive_address + len(received)] = list(received)
                        cpu.queue_receive(received, reply_id)
                        # Align the receive pipeline's first NIC arrival with the
                        # actual delivered reply. Only internal service work follows.
                        pipe = network_pipeline(received, packet_size=max(1, len(received)),
                                                buffer_bytes=max(1, len(received)), direction="receive")
                        first_arrival = next((event["time"] for event in pipe["events"] if event["kind"] == "network.receive"), 0)
                        for event in pipe["events"]:
                            event = copy.deepcopy(event)
                            event["time"] = simulator.engine.time + (event["time"] - first_arrival) / 1000
                            event["packet_id"] = reply_id
                            event["source"] = source + ":" + event["source"]
                            event["target"] = source + ":" + event["target"]
                            receive_events.append(event)
                        receive_events.append({"id": f"received-memory-{index}",
                                               "time": simulator.engine.time + (pipe["duration_ms"] - first_arrival) / 1000,
                                               "kind": "memory.receive", "source": source + ":kernel",
                                               "target": source + ":application", "packet_id": reply_id,
                                               "status": "completed", "explanation": f"回显字节写入教学内存地址 {receive_address}",
                                               "data": {"address": receive_address, "payload_hex": received.hex()}, "teaching_model": True})
        if not outcome["echo_received"]:
            outcome["reason"] = "虚拟请求未到达服务端，或回包未到达客户端；没有生成成功的接收结果。"
        outcomes.append(outcome)
    network = simulator.run(max_events=min(max(event_budget, 1), 100_000))
    all_events = cpu_events + network["events"] + receive_events
    all_events.sort(key=lambda event: (event["time"], str(event.get("id", ""))))
    for index, event in enumerate(all_events, 1):
        event["original_id"] = event.get("id")
        event["id"] = f"integrated-{index:08d}"
        event["teaching_model"] = True
    network_success = bool(outcomes) and all(outcome["echo_received"] for outcome in outcomes)
    success = network_success and cpu.halted and not blocked
    return {"mode": "teaching_simulation", "teaching_model": True, "events": all_events,
            "packets": network["packets"], "topology": network["topology"], "network": network,
            "cpu": cpu.snapshot(), "messages": outcomes,
            "results": {"success": success, "network_success": network_success, "messages_sent": len(outcomes),
                        "messages_received": sum(outcome["echo_received"] for outcome in outcomes),
                        "cpu_halted": cpu.halted,
                        "blocked": blocked, "executed_steps": executed_steps,
                        "execution_limit_reached": not cpu.halted and not blocked},
            "config": {"assembly": assembly, "source": source, "target": target, "seed": seed,
                       "receive_address": receive_address, "topology": copy.deepcopy(topology or example_topology("home"))},
            "note": "共享数据包 ID 关联 CPU、系统调用、DMA、ARP、交换、路由、NAT 与回显接收。任意消息字节以十六进制文本封装，链路大小计入编码开销。CPU/网卡周期为教学参数，未模拟真实硬件；所有消息只在虚拟模型中流转。"}

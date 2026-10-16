"""Discrete scheduler and CPU/OS/NIC network pipeline teaching models."""
from __future__ import annotations

import math
from collections import deque


def schedule_processes(processes: list[dict], algorithm: str = "RR", quantum: int = 2) -> dict:
    """Simulate arrival, ready, running, blocked, and terminated states.

    Input: {pid,arrival,burst} or {pid,arrival,cpu_bursts:[...],io_bursts:[...]};
    CPU and I/O durations use the same arbitrary simulated time unit.
    """
    algorithm = algorithm.upper()
    if algorithm not in ("FCFS", "SJF", "RR", "PRIORITY"):
        raise ValueError("调度算法支持 FCFS、SJF、RR、PRIORITY")
    if not isinstance(quantum, int) or not 1 <= quantum <= 100_000:
        raise ValueError("时间片须为正整数")
    if not 1 <= len(processes) <= 1000:
        raise ValueError("进程数量须为 1 到 1000")
    jobs, names = [], set()
    for index, source in enumerate(processes):
        pid = str(source.get("pid", f"P{index + 1}"))
        if pid in names or not pid:
            raise ValueError("进程 ID 必须唯一且非空")
        names.add(pid)
        bursts = list(source.get("cpu_bursts", [source.get("burst", 1)]))
        io = list(source.get("io_bursts", []))
        arrival = source.get("arrival", 0)
        priority = source.get("priority", 0)
        if not bursts or len(io) != len(bursts) - 1 or any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in bursts + io):
            raise ValueError("CPU 和 I/O 时长须为正整数，I/O 段数比 CPU 段数少 1")
        if not isinstance(arrival, int) or arrival < 0 or not isinstance(priority, int):
            raise ValueError("到达时间须为非负整数，优先级须为整数")
        jobs.append({"pid": pid, "arrival": arrival, "priority": priority, "bursts": bursts,
                     "io": io, "index": index, "burst_index": 0, "remaining": bursts[0],
                     "state": "new", "ready_at": arrival, "waiting": 0, "start": None,
                     "finish": None, "order": 0})
    ready, timeline, events = deque(), [], []
    time, sequence, done = 0, 0, 0

    def event(job, state, at, explanation):
        job["state"] = state
        events.append({"id": f"os-{len(events) + 1}", "time": at, "kind": "os.process_state",
                       "source": "scheduler", "target": job["pid"], "packet_id": None,
                       "status": state, "explanation": explanation, "data": {"pid": job["pid"], "state": state},
                       "teaching_model": True})

    def arrivals(until):
        nonlocal sequence
        newcomers = sorted((job for job in jobs if job["state"] in ("new", "blocked") and job["ready_at"] <= until),
                           key=lambda job: (job["ready_at"], job["index"]))
        for job in newcomers:
            sequence += 1
            job["order"] = sequence
            event(job, "ready", job["ready_at"], "I/O 完成，进入就绪队列" if job["state"] == "blocked" else "进程到达，进入就绪队列")
            ready.append(job)

    while done < len(jobs):
        arrivals(time)
        if not ready:
            future = min(job["ready_at"] for job in jobs if job["state"] in ("new", "blocked"))
            if future > time:
                timeline.append({"pid": "IDLE", "start": time, "end": future})
            time = future
            arrivals(time)
        if algorithm in ("SJF", "PRIORITY"):
            job = min(ready, key=lambda item: (item["remaining"] if algorithm == "SJF" else item["priority"], item["order"]))
            ready.remove(job)
        else:
            job = ready.popleft()
        job["waiting"] += time - job["ready_at"]
        if job["start"] is None:
            job["start"] = time
        event(job, "running", time, f"{algorithm} 选择进程运行")
        duration = min(job["remaining"], quantum) if algorithm == "RR" else job["remaining"]
        end = time + duration
        timeline.append({"pid": job["pid"], "start": time, "end": end, "cpu_burst": job["burst_index"]})
        job["remaining"] -= duration
        arrivals(end)
        time = end
        if job["remaining"]:
            job["ready_at"] = time
            sequence += 1
            job["order"] = sequence
            event(job, "ready", time, "时间片用完，保留剩余执行量并回到就绪队列")
            ready.append(job)
        elif job["burst_index"] < len(job["bursts"]) - 1:
            job["ready_at"] = time + job["io"][job["burst_index"]]
            job["burst_index"] += 1
            job["remaining"] = job["bursts"][job["burst_index"]]
            event(job, "blocked", time, f"等待 I/O，预计 {job['ready_at']} 完成")
        else:
            job["finish"] = time
            event(job, "terminated", time, "所有 CPU 段执行完毕")
            done += 1
        if len(timeline) > 100_000:
            raise ValueError("调度事件超过 100000，请减小实验规模")
    metrics = [{"pid": job["pid"], "arrival": job["arrival"], "finish": job["finish"],
                "waiting": job["waiting"], "response": job["start"] - job["arrival"],
                "turnaround": job["finish"] - job["arrival"], "state": job["state"]}
               for job in jobs]
    return {"algorithm": algorithm, "quantum": quantum, "timeline": timeline,
            "events": sorted(events, key=lambda item: item["time"]), "processes": metrics,
            "total_time": time, "average_waiting": sum(job["waiting"] for job in jobs) / len(jobs),
            "cpu_utilization": sum(sum(job["bursts"]) for job in jobs) / time if time else 0,
            "teaching_model": True, "limitations": "单核模型，I/O 可并行；未计入切换开销和真实线程优先级。"}


def network_pipeline(payload: bytes | str, packet_size: int = 512, buffer_bytes: int = 4096,
                     bandwidth_mbps: float = 100, processing: str = "interrupt",
                     cpu_mhz: float = 1000, direction: str = "send", batch_size: int = 8) -> dict:
    """Event-driven single NIC model with backpressure and CPU/network overlap.

    Model costs: syscall 400 cycles, copy 2 cycles/byte, stack 300 cycles/packet,
    interrupt 800 cycles/packet; polling batches cost 200 + 100/packet cycles.
    No values are hardware measurements. NIC transmits one packet at a time.
    """
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if not isinstance(payload, bytes) or len(payload) > 16_777_216:
        raise ValueError("载荷须为不超过 16 MiB 的字节或字符串")
    if not isinstance(packet_size, int) or not 1 <= packet_size <= 65535:
        raise ValueError("教学数据块大小应为 1 到 65535 字节")
    if not isinstance(buffer_bytes, int) or not packet_size <= buffer_bytes <= 16_777_216:
        raise ValueError("缓冲区须至少容纳一个数据块，最大 16 MiB")
    if not all(math.isfinite(float(v)) and float(v) > 0 for v in (bandwidth_mbps, cpu_mhz)):
        raise ValueError("带宽和 CPU 频率须为有限正数")
    if processing not in ("interrupt", "polling") or direction not in ("send", "receive"):
        raise ValueError("处理方式应为 interrupt 或 polling；方向应为 send 或 receive")
    if not isinstance(batch_size, int) or not 1 <= batch_size <= 1024:
        raise ValueError("批处理大小须为 1 到 1024")
    if len(payload) / packet_size > 100_000:
        raise ValueError("数据块数量超过 100000，请增大块大小")
    events, packets, in_flight = [], [], []
    cpu_free, nic_free, cpu_cycles, waiting, peak = 0.0, 0.0, 0, 0.0, 0
    cycles_per_ms = cpu_mhz * 1000

    def add(at, kind, source, target, packet_id, explanation, **data):
        events.append({"id": f"pipeline-{len(events) + 1}", "time": at, "kind": kind,
                       "source": source, "target": target, "packet_id": packet_id,
                       "status": "completed", "explanation": explanation, "data": data,
                       "teaching_model": True})

    for index, offset in enumerate(range(0, len(payload), packet_size)):
        data = payload[offset:offset + packet_size]
        count, packet_id = len(data), f"system-packet-{index + 1}"
        completion_cost = 800 if processing == "interrupt" else 100 + (200 if index % batch_size == 0 else 0)
        work = 400 + 2 * count + 300 + completion_cost
        if direction == "send":
            in_flight = [(end, size) for end, size in in_flight if end > cpu_free]
            while sum(size for _, size in in_flight) + count > buffer_bytes:
                earliest = min(end for end, _ in in_flight)
                add(cpu_free, "os.block", "socket-buffer", "application", packet_id,
                    "发送缓冲区不足，应用阻塞等待网卡释放空间", occupied=sum(size for _, size in in_flight))
                waiting += earliest - cpu_free
                cpu_free = earliest
                in_flight = [(end, size) for end, size in in_flight if end > cpu_free]
            add(cpu_free, "cpu.application", "cpu", "application", packet_id, "CPU 执行网络应用")
            add(cpu_free, "os.syscall", "application", "kernel", packet_id, "send 系统调用进入内核态")
            buffer_at = cpu_free + (400 + 2 * count) / cycles_per_ms
            add(buffer_at, "os.socket_buffer", "kernel", "socket-buffer", packet_id,
                "数据复制到发送缓冲区", bytes=count)
            ready = cpu_free + (400 + 2 * count + 300) / cycles_per_ms
            start = max(nic_free, ready)
            add(start, "nic.dma", "memory", "nic", packet_id, "DMA 读取缓冲区；CPU 可继续处理其他块")
            end = start + count * 8 / (bandwidth_mbps * 1000)
            add(end, "network.send", "nic", "virtual-network", packet_id, "虚拟网卡完成发送", bytes=count)
            add(end, "nic.interrupt" if processing == "interrupt" else "nic.poll", "nic", "kernel", packet_id,
                "完成通知释放 Socket 缓冲区", cycles=completion_cost)
            cpu_free += work / cycles_per_ms
            nic_free = end
            in_flight.append((end, count))
            peak = max(peak, sum(size for _, size in in_flight))
        else:
            start = nic_free
            arrival = start + count * 8 / (bandwidth_mbps * 1000)
            add(arrival, "network.receive", "virtual-network", "nic", packet_id, "数据块到达网卡", bytes=count)
            add(arrival, "nic.dma", "nic", "memory", packet_id, "DMA 将数据写入接收缓冲区")
            in_flight = [(end, size) for end, size in in_flight if end > arrival]
            if sum(size for _, size in in_flight) + count > buffer_bytes:
                add(arrival, "network.drop", "socket-buffer", "application", packet_id,
                    "接收缓冲区已满，教学数据块丢弃", bytes=count)
                packets.append({"id": packet_id, "offset": offset, "size": count, "status": "dropped", "start": start, "end": arrival})
                nic_free = arrival
                continue
            service = max(cpu_free, arrival)
            add(service, "nic.interrupt" if processing == "interrupt" else "nic.poll", "nic", "kernel", packet_id,
                "内核开始处理接收数据", cycles=completion_cost)
            end = service + work / cycles_per_ms
            add(end, "os.syscall", "kernel", "application", packet_id,
                "协议栈处理完成，应用 recv 读取缓冲区", bytes=count)
            in_flight.append((end, count))
            cpu_free, nic_free = end, arrival
            peak = max(peak, sum(size for _, size in in_flight))
        cpu_cycles += work
        packets.append({"id": packet_id, "offset": offset, "size": count, "payload_hex": data.hex(),
                        "status": "delivered", "start": start, "end": end})
    total_ms = max(cpu_free, nic_free)
    delivered = sum(packet["size"] for packet in packets if packet["status"] == "delivered")
    return {"events": sorted(events, key=lambda event: (event["time"], int(event["id"].split("-")[-1]))),
            "packets": packets, "bytes": len(payload), "delivered_bytes": delivered,
            "dropped_packets": sum(packet["status"] == "dropped" for packet in packets),
            "duration_ms": total_ms, "throughput_mbps": delivered * 8 / (total_ms * 1000) if total_ms else 0,
            "cpu_cycles": cpu_cycles, "cpu_busy_ms": cpu_cycles / cycles_per_ms,
            "cpu_utilization": cpu_cycles / cycles_per_ms / total_ms if total_ms else 0,
            "buffer_wait_ms": waiting, "peak_buffer_bytes": peak,
            "parameters": {"packet_size": packet_size, "buffer_bytes": buffer_bytes,
                           "bandwidth_mbps": bandwidth_mbps, "cpu_mhz": cpu_mhz,
                           "processing": processing, "direction": direction, "batch_size": batch_size},
            "teaching_model": True,
            "limitations": "简化单队列网卡与单 CPU 模型，教学周期为固定参数。未模拟 TSO、RSS、零复制、Cache 一致性或真实驱动，不代表本机性能。"}

"""A 16-bit educational ISA, with independent fetch/decode/execute state."""
from __future__ import annotations

import re
import copy

from .binary import alu


class CPU:
    """Eight registers; word-addressed memory. SEND start,length emits simulated events."""

    def __init__(self, bits: int = 16, memory_size: int = 256, receive_policy: str = "loopback"):
        if not 8 <= bits <= 32 or not isinstance(memory_size, int) or not 1 <= memory_size <= 65536:
            raise ValueError("CPU 位宽应为 8 到 32；内存应为 1 到 65536 字")
        self.bits, self.memory_size = bits, memory_size
        if receive_policy not in ("loopback", "external"):
            raise ValueError("接收策略须为 loopback 或 external")
        self.receive_policy = receive_policy
        self.mask = (1 << bits) - 1
        self.program, self.source = [], ""
        self.reset()

    def reset(self) -> None:
        self.pc, self.cycles, self.halted = 0, 0, False
        self.registers = {f"R{i}": 0 for i in range(8)}
        self.flags = {key: False for key in "ZNCV"}
        self.memory = [0] * self.memory_size
        self.events, self.trace, self.sent_messages = [], [], []
        self.receive_queue = []
        self.stack_pointer = self.memory_size

    def load(self, assembly: str) -> dict:
        if not isinstance(assembly, str) or len(assembly) > 1_000_000:
            raise ValueError("汇编程序必须为不超过 1 MB 的文本")
        labels, raw = {}, []
        for line_no, line in enumerate(assembly.splitlines(), 1):
            line = line.split(";", 1)[0].strip()
            if not line:
                continue
            if ":" in line:
                name, line = line.split(":", 1)
                if not re.fullmatch(r"[A-Za-z_]\w*", name) or name in labels:
                    raise ValueError(f"第 {line_no} 行：标签无效或重复")
                labels[name] = len(raw)
                line = line.strip()
                if not line:
                    continue
            parts = line.replace(",", " ").split()
            raw.append((parts[0].upper(), [p.upper() if re.fullmatch(r"[rR][0-7]", p) else p for p in parts[1:]], line_no, line))
        valid = {"MOV": 2, "LOAD": 2, "STORE": 2, "ADD": 2, "SUB": 2, "AND": 2, "OR": 2,
                 "XOR": 2, "SHL": 2, "SHR": 2, "CMP": 2, "JMP": 1, "JZ": 1, "JNZ": 1,
                 "PUSH": 1, "POP": 1, "SEND": 2, "RECV": 2, "NOP": 0, "HALT": 0, "NOT": 1}
        prepared = []
        for op, args, line_no, text in raw:
            if op not in valid or len(args) != valid[op]:
                raise ValueError(f"第 {line_no} 行：指令或操作数数量错误")
            if op in ("JMP", "JZ", "JNZ"):
                args[0] = labels.get(args[0], args[0])
                target = self._literal(args[0], line_no)
                if not 0 <= target < len(raw):
                    raise ValueError(f"第 {line_no} 行：跳转目标不在指令存储中")
                args[0] = target
            elif op not in ("NOP", "HALT"):
                for arg in args:
                    token = arg[1:-1] if isinstance(arg, str) and arg.startswith("[") and arg.endswith("]") else arg
                    if token not in self.registers:
                        self._literal(token, line_no)
                if op in ("MOV", "LOAD", "ADD", "SUB", "AND", "OR", "XOR", "SHL", "SHR", "CMP", "NOT", "POP") and args[0] not in self.registers:
                    raise ValueError(f"第 {line_no} 行：目标必须为 R0 到 R7")
            prepared.append({"op": op, "args": args, "line": line_no, "text": text})
        self.program, self.source = prepared, assembly
        self.reset()
        return self.snapshot()

    @staticmethod
    def _literal(token, line_no=0) -> int:
        if isinstance(token, int):
            return token
        try:
            value = int(token, 0)
        except (ValueError, TypeError):
            # Decimal strings such as 08 should also work.
            try:
                value = int(token, 10)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"第 {line_no} 行：无效数值 {token}") from exc
        return value

    def _value(self, token) -> int:
        if token in self.registers:
            return self.registers[token]
        return self._literal(token)

    def _address(self, token) -> int:
        token = token[1:-1] if isinstance(token, str) and token.startswith("[") and token.endswith("]") else token
        address = self._value(token)
        if not 0 <= address < self.memory_size:
            raise ValueError(f"内存地址 {address} 越界")
        return address

    def _event(self, kind, source="cpu", target="cpu", packet_id=None, explanation="", **data):
        event = {"id": f"cpu-{len(self.events) + 1}", "time": self.cycles / 1000,
                 "kind": kind, "source": source, "target": target, "packet_id": packet_id,
                 "status": "completed", "explanation": explanation, "data": data,
                 "teaching_model": True}
        self.events.append(event)
        return event

    def queue_receive(self, payload: bytes, message_id: str | None = None) -> None:
        """Inject already-delivered virtual bytes; this never reads a real socket."""
        if not isinstance(payload, bytes) or len(payload) > self.memory_size:
            raise ValueError("教学接收消息须为字节且不能超过内存大小")
        self.receive_queue.append({"id": message_id or f"incoming-{len(self.receive_queue) + 1}",
                                   "payload_hex": payload.hex()})

    def step(self) -> dict:
        if self.halted:
            return {"status": "halted", **self.snapshot()}
        if not 0 <= self.pc < len(self.program):
            self.halted = True
            return {"status": "end", **self.snapshot()}
        instruction = self.program[self.pc]
        op, args = instruction["op"], instruction["args"]
        old_pc, before = self.pc, dict(self.registers)
        event_start = len(self.events)
        self._event("cpu.fetch", explanation=f"PC={self.pc} 取指：{instruction['text']}", pc=self.pc)
        next_pc = self.pc + 1
        consumed = 1
        if op == "MOV":
            self.registers[args[0]] = self._value(args[1]) & self.mask
        elif op == "LOAD":
            address = self._address(args[1])
            self.registers[args[0]] = self.memory[address]
            consumed = 3
            self._event("memory.read", target="memory", explanation=f"从地址 {address} 读取字", address=address)
        elif op == "STORE":
            address = self._address(args[0])
            self.memory[address] = self._value(args[1]) & self.mask
            consumed = 3
            self._event("memory.write", target="memory", explanation=f"写入地址 {address}", address=address, value=self.memory[address])
        elif op in ("ADD", "SUB", "AND", "OR", "XOR", "SHL", "SHR", "NOT", "CMP"):
            result = alu("SUB" if op == "CMP" else op, self.registers[args[0]],
                         0 if op == "NOT" else self._value(args[1]), self.bits)
            if op != "CMP":
                self.registers[args[0]] = result["result"]
            self.flags = result["flags"]
            self._event("cpu.alu", explanation=f"ALU 执行 {op}", **result)
        elif op in ("JMP", "JZ", "JNZ"):
            if op == "JMP" or (op == "JZ" and self.flags["Z"]) or (op == "JNZ" and not self.flags["Z"]):
                next_pc = args[0]
        elif op == "PUSH":
            if self.stack_pointer == 0:
                raise ValueError("栈溢出")
            self.stack_pointer -= 1
            self.memory[self.stack_pointer] = self._value(args[0]) & self.mask
            consumed = 3
        elif op == "POP":
            if self.stack_pointer == self.memory_size:
                raise ValueError("栈为空")
            self.registers[args[0]] = self.memory[self.stack_pointer]
            self.stack_pointer += 1
            consumed = 3
        elif op in ("SEND", "RECV"):
            address, length = self._address(args[0]), self._value(args[1])
            if not 0 <= length <= self.memory_size - address:
                raise ValueError("网络缓冲区范围越界")
            packet_id = f"message-{len(self.sent_messages) + 1}"
            if op == "RECV" and self.receive_queue:
                packet_id = self.receive_queue[0]["id"]
            payload = bytes(value & 255 for value in self.memory[address:address + length])
            self._event("os.syscall", target="os", packet_id=packet_id,
                        explanation=f"{op} 进入内核态，地址={address}，长度={length}", address=address, length=length)
            if op == "SEND":
                self._event("os.socket_buffer", source="os", target="socket-buffer", packet_id=packet_id,
                            explanation="教学内核将应用数据复制到 Socket 发送缓冲区", payload_hex=payload.hex())
                self._event("nic.dma", source="memory", target="nic", packet_id=packet_id,
                            explanation="教学网卡 DMA 读取发送缓冲区")
                self._event("network.send", source="nic", target="virtual-network", packet_id=packet_id,
                            explanation="将虚拟消息交给模拟网络；未发送到真实网卡", payload_hex=payload.hex())
                self.sent_messages.append({"id": packet_id, "payload_hex": payload.hex(), "length": length})
                if self.receive_policy == "loopback":
                    self.queue_receive(payload, packet_id)
            else:
                if not self.receive_queue:
                    raise ValueError("没有可接收的模拟消息，请先 SEND")
                incoming = self.receive_queue.pop(0)
                packet_id = incoming["id"]
                whole = bytes.fromhex(incoming["payload_hex"])
                received = whole[:length]
                if len(received) < len(whole):
                    self.receive_queue.insert(0, {"id": packet_id, "payload_hex": whole[len(received):].hex()})
                self.memory[address:address + len(received)] = list(received)
                self._event("network.receive", source="virtual-network", target="nic", packet_id=packet_id,
                            explanation="从教学接收队列读取已交付的消息" + ("（CPU 本地回环）" if self.receive_policy == "loopback" else "（虚拟网络回包）"), payload_hex=received.hex())
                self._event("nic.interrupt", source="nic", target="os", packet_id=packet_id,
                            explanation="DMA 完成后通知内核")
                self._event("os.wakeup", source="os", target="application", packet_id=packet_id,
                            explanation="应用读取 Socket 缓冲区")
            consumed = 5 + length
        elif op == "HALT":
            self.halted = True
        self.cycles += consumed
        self.pc = next_pc
        entry = {"pc_before": old_pc, "pc_after": self.pc, "instruction": instruction["text"],
                 "line": instruction["line"], "cycles": self.cycles,
                 "register_changes": {name: {"before": before[name], "after": value} for name, value in self.registers.items() if before[name] != value},
                 "registers": dict(self.registers), "flags": dict(self.flags), "halted": self.halted,
                 "events": self.events[event_start:], "teaching_model": True}
        self.trace.append(entry)
        return entry

    def run(self, max_steps: int = 1000) -> list[dict]:
        if not isinstance(max_steps, int) or not 1 <= max_steps <= 100_000:
            raise ValueError("步数上限必须为 1 到 100000")
        trace = []
        for _ in range(max_steps):
            if self.halted or not 0 <= self.pc < len(self.program):
                self.halted = True
                break
            trace.append(self.step())
        return trace

    def snapshot(self) -> dict:
        return copy.deepcopy({"format": "netlab.cpu.snapshot.v1", "bits": self.bits,
                "memory_size": self.memory_size, "assembly": self.source,
                "receive_policy": self.receive_policy, "receive_queue": list(self.receive_queue),
                "pc": self.pc, "registers": dict(self.registers), "flags": dict(self.flags),
                "memory": list(self.memory), "cycles": self.cycles, "halted": self.halted,
                "stack_pointer": self.stack_pointer, "program": list(self.program),
                "events": list(self.events), "sent_messages": list(self.sent_messages),
                "teaching_model": True})

    @classmethod
    def restore(cls, snapshot: dict) -> "CPU":
        if snapshot.get("format") != "netlab.cpu.snapshot.v1":
            raise ValueError("不支持的 CPU 快照格式")
        cpu = cls(snapshot["bits"], snapshot["memory_size"], snapshot.get("receive_policy", "loopback"))
        cpu.load(snapshot["assembly"])
        if not isinstance(snapshot["pc"], int) or not 0 <= snapshot["pc"] <= len(cpu.program):
            raise ValueError("CPU 快照的 PC 超出指令范围")
        if set(snapshot["registers"]) != set(cpu.registers) or set(snapshot["flags"]) != set(cpu.flags):
            raise ValueError("CPU 快照的寄存器或标志字段不完整")
        if len(snapshot["memory"]) != cpu.memory_size or any(not isinstance(v, int) or not 0 <= v <= cpu.mask
                                                          for v in list(snapshot["registers"].values()) + snapshot["memory"]):
            raise ValueError("CPU 快照的寄存器或内存值无效")
        if not 0 <= snapshot["stack_pointer"] <= cpu.memory_size or snapshot["cycles"] < 0:
            raise ValueError("CPU 快照的栈指针或周期无效")
        for key in ("pc", "registers", "flags", "memory", "cycles", "halted", "stack_pointer", "events", "sent_messages"):
            setattr(cpu, key, copy.deepcopy(snapshot[key]))
        cpu.receive_queue = copy.deepcopy(snapshot.get("receive_queue", []))
        for message in cpu.receive_queue:
            if len(bytes.fromhex(message["payload_hex"])) > cpu.memory_size:
                raise ValueError("CPU 快照包含过长的接收消息")
        return cpu

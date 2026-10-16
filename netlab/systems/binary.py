"""Integer representations, IEEE 754, ALU, and connected combinational circuits."""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field


def _width(bits: int) -> None:
    if not isinstance(bits, int) or isinstance(bits, bool) or not 2 <= bits <= 64:
        raise ValueError("位宽必须为 2 到 64 的整数")


def describe_integer(value: int, bits: int = 8) -> dict:
    _width(bits)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("请输入整数")
    mask = (1 << bits) - 1
    if not -(1 << (bits - 1)) <= value <= mask:
        raise ValueError(f"数值超出 {bits} 位可表示范围")
    unsigned = value & mask
    signed = unsigned if unsigned < (1 << (bits - 1)) else unsigned - (1 << bits)
    magnitude_ok = abs(value) < (1 << (bits - 1))
    sign_magnitude = f"{int(value < 0)}{abs(value):0{bits - 1}b}" if magnitude_ok else None
    ones = ((~abs(value)) & mask) if value < 0 else value
    steps = [{"bit": i, "weight": 1 << i, "value": (unsigned >> i) & 1}
             for i in range(bits - 1, -1, -1)]
    return {"value": value, "bits": bits, "binary": f"{unsigned:0{bits}b}",
            "hex": f"0x{unsigned:0{(bits + 3) // 4}X}", "unsigned": unsigned,
            "signed": signed, "sign_magnitude": sign_magnitude,
            "ones_complement": f"{ones:0{bits}b}" if magnitude_ok else None,
            "twos_complement": f"{unsigned:0{bits}b}", "steps": steps,
            "explanation": "补码按固定宽度取模；原码和反码无法表示最小负数。",
            "teaching_model": True}


def describe_float(value: float, bits: int = 32) -> dict:
    if bits not in (32, 64):
        raise ValueError("IEEE 754 实验支持 binary32 或 binary64")
    try:
        value = float(value)
        packed = struct.pack(">f" if bits == 32 else ">d", value)
    except (ValueError, OverflowError, TypeError) as exc:
        raise ValueError("数值无法编码为指定浮点格式") from exc
    exponent_bits, fraction_bits = (8, 23) if bits == 32 else (11, 52)
    raw = int.from_bytes(packed, "big")
    text = f"{raw:0{bits}b}"
    exponent = (raw >> fraction_bits) & ((1 << exponent_bits) - 1)
    fraction = raw & ((1 << fraction_bits) - 1)
    bias = (1 << (exponent_bits - 1)) - 1
    special = "normal"
    if exponent == 0:
        special = "zero" if fraction == 0 else "subnormal"
    elif exponent == (1 << exponent_bits) - 1:
        special = "infinity" if fraction == 0 else "NaN"
    rounded = struct.unpack(">f" if bits == 32 else ">d", packed)[0]
    serializable = lambda v: v if math.isfinite(v) else "NaN" if math.isnan(v) else "+Infinity" if v > 0 else "-Infinity"
    return {"value": serializable(value), "rounded_value": serializable(rounded),
            "bits": bits, "binary": text, "hex": packed.hex().upper(), "sign": int(text[0]),
            "exponent_bits": text[1:1 + exponent_bits], "exponent_stored": exponent,
            "fraction_bits": text[1 + exponent_bits:], "fraction": fraction / (1 << fraction_bits),
            "exponent": (1 - bias) if exponent == 0 else exponent - bias,
            "bias": bias, "classification": special,
            "formula": "正常数：(-1)^符号 × (1 + 尾数) × 2^(阶码 - 偏置)",
            "teaching_model": True}


def alu(op: str, a: int, b: int = 0, bits: int = 8) -> dict:
    _width(bits)
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (a, b)):
        raise ValueError("ALU 操作数必须为整数")
    if op.upper() in ("SHL", "SHR") and not 0 <= b < bits:
        raise ValueError("移位数必须为非负数且小于位宽")
    mask = (1 << bits) - 1
    a, b = a & mask, b & mask
    op = op.upper()
    signed_a = a if a < 1 << (bits - 1) else a - (1 << bits)
    signed_b = b if b < 1 << (bits - 1) else b - (1 << bits)
    carry, overflow = False, False
    if op in ("ADD", "SUB"):
        raw = a + b if op == "ADD" else a - b
        signed_raw = signed_a + signed_b if op == "ADD" else signed_a - signed_b
        carry = raw > mask if op == "ADD" else raw < 0
        overflow = not -(1 << (bits - 1)) <= signed_raw < (1 << (bits - 1))
    elif op == "AND":
        raw = a & b
    elif op == "OR":
        raw = a | b
    elif op == "XOR":
        raw = a ^ b
    elif op == "NOT":
        raw = ~a
    elif op in ("SHL", "SHR"):
        if b >= bits:
            raise ValueError("移位数必须小于位宽")
        raw = a << b if op == "SHL" else a >> b
        carry = bool(a & ((1 << b) - 1)) if op == "SHR" else bool(raw & ~mask)
    else:
        raise ValueError(f"不支持的 ALU 操作：{op}")
    result = raw & mask
    return {"op": op, "a": a, "b": b, "bits": bits, "result": result,
            "binary": f"{result:0{bits}b}", "signed_result": result if result < 1 << (bits - 1) else result - (1 << bits),
            "flags": {"Z": result == 0, "N": bool(result & (1 << (bits - 1))),
                      "C": carry, "V": overflow}, "teaching_model": True}


def _bit(value: int) -> int:
    if value not in (0, 1):
        raise ValueError("逻辑输入只能是 0 或 1")
    return int(value)


def half_adder(a: int, b: int) -> dict:
    a, b = _bit(a), _bit(b)
    return {"sum": a ^ b, "carry": a & b}


def full_adder(a: int, b: int, carry_in: int = 0) -> dict:
    a, b, carry_in = _bit(a), _bit(b), _bit(carry_in)
    first = half_adder(a, b)
    second = half_adder(first["sum"], carry_in)
    return {"sum": second["sum"], "carry": first["carry"] | second["carry"]}


@dataclass
class LogicCircuit:
    """Each gate takes IDs of other gates; INPUT gates take user-supplied bits."""
    gates: dict = field(default_factory=dict)
    positions: dict = field(default_factory=dict)

    def add_gate(self, gate_id: str, kind: str, inputs: list[str] | None = None,
                 value: int = 0, x: float = 0, y: float = 0) -> None:
        if not gate_id or gate_id in self.gates:
            raise ValueError("逻辑门 ID 必须非空且唯一")
        kind = kind.upper()
        if kind not in ("INPUT", "OUTPUT", "AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR"):
            raise ValueError("未知逻辑门")
        self.gates[gate_id] = {"kind": kind, "inputs": list(inputs or []), "value": _bit(value)}
        self.positions[gate_id] = {"x": float(x), "y": float(y)}

    def connect(self, source: str, target: str, slot: int | None = None) -> None:
        if source not in self.gates or target not in self.gates:
            raise ValueError("连线的两个逻辑门都必须存在")
        inputs = self.gates[target]["inputs"]
        if slot is None:
            inputs.append(source)
        elif 0 <= slot <= len(inputs):
            if slot == len(inputs):
                inputs.append(source)
            else:
                inputs[slot] = source
        else:
            raise ValueError("无效输入端口")

    def evaluate(self, inputs: dict[str, int] | None = None) -> dict:
        overrides = inputs or {}
        if any(name not in self.gates or self.gates[name]["kind"] != "INPUT" for name in overrides):
            raise ValueError("只能设置 INPUT 门的值")
        resolved, visiting, trace = {}, set(), []

        def resolve(name):
            if name in resolved:
                return resolved[name]
            if name not in self.gates:
                raise ValueError(f"连线引用不存在的门：{name}")
            if name in visiting:
                raise ValueError("组合电路包含反馈环路；请使用无环电路")
            visiting.add(name)
            gate = self.gates[name]
            kind = gate["kind"]
            arity = 0 if kind == "INPUT" else 1 if kind in ("NOT", "OUTPUT") else 2
            if len(gate["inputs"]) != arity:
                raise ValueError(f"{name} ({kind}) 需要 {arity} 个输入")
            vals = [resolve(item) for item in gate["inputs"]]
            if kind == "INPUT":
                value = _bit(overrides.get(name, gate["value"]))
            elif kind == "OUTPUT":
                value = vals[0]
            elif kind == "NOT":
                value = 1 - vals[0]
            else:
                base = {"AND": vals[0] & vals[1], "OR": vals[0] | vals[1],
                        "XOR": vals[0] ^ vals[1]}
                value = base[kind[1:] if kind in ("NAND", "NOR") else "XOR" if kind == "XNOR" else kind]
                if kind in ("NAND", "NOR", "XNOR"):
                    value = 1 - value
            visiting.remove(name)
            resolved[name] = value
            trace.append({"gate": name, "kind": kind, "inputs": vals, "output": value})
            return value

        for name in self.gates:
            resolve(name)
        return {"values": resolved, "outputs": {name: resolved[name] for name, gate in self.gates.items()
                                               if gate["kind"] == "OUTPUT"},
                "trace": trace, "teaching_model": True}

    def to_dict(self) -> dict:
        return {"gates": {name: dict(gate, inputs=list(gate["inputs"])) for name, gate in self.gates.items()},
                "positions": {name: dict(pos) for name, pos in self.positions.items()}}

    @classmethod
    def from_dict(cls, config: dict) -> "LogicCircuit":
        circuit = cls()
        for name, gate in config.get("gates", {}).items():
            pos = config.get("positions", {}).get(name, {})
            circuit.add_gate(name, gate["kind"], gate.get("inputs", []), gate.get("value", 0),
                             pos.get("x", 0), pos.get("y", 0))
        return circuit

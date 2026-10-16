import itertools
import json
import math

import pytest

from netlab.systems import LogicCircuit, alu, describe_float, describe_integer, full_adder


@pytest.mark.parametrize("value,bits,binary,signed", [
    (-1, 8, "11111111", -1), (-128, 8, "10000000", -128),
    (255, 8, "11111111", -1), (10, 8, "00001010", 10),
    (65535, 16, "1111111111111111", -1),
])
def test_integer_representations(value, bits, binary, signed):
    data = describe_integer(value, bits)
    assert data["binary"] == binary
    assert data["signed"] == signed
    assert sum(step["weight"] * step["value"] for step in data["steps"]) == data["unsigned"]


def test_minimum_negative_has_no_sign_magnitude():
    assert describe_integer(-128)["sign_magnitude"] is None
    assert describe_integer(-5)["ones_complement"] == "11111010"
    assert describe_integer(-5)["twos_complement"] == "11111011"


@pytest.mark.parametrize("value,bits", [(-129, 8), (256, 8), (1, 0), (1, 65), (1.5, 8), (True, 8)])
def test_integer_input_validation(value, bits):
    with pytest.raises(ValueError):
        describe_integer(value, bits)


@pytest.mark.parametrize("value,hex_value,classification", [
    (1.0, "3F800000", "normal"), (-0.0, "80000000", "zero"),
    (float("inf"), "7F800000", "infinity"), (2 ** -149, "00000001", "subnormal")])
def test_ieee_fields(value, hex_value, classification):
    data = describe_float(value)
    assert data["hex"] == hex_value
    assert data["classification"] == classification
    json.dumps(data, allow_nan=False)


def test_nan_and_rounding_and_width():
    assert describe_float(float("nan"))["classification"] == "NaN"
    assert describe_float(0.1)["rounded_value"] != 0.1
    assert describe_float(1.0, 64)["hex"] == "3FF0000000000000"
    with pytest.raises(ValueError):
        describe_float(1.0, 16)


def test_alu_signed_overflow_and_unsigned_carry_differ():
    signed = alu("ADD", 127, 1)
    assert signed["signed_result"] == -128 and signed["flags"]["V"]
    assert not signed["flags"]["C"]
    unsigned = alu("ADD", 255, 1)
    assert unsigned["result"] == 0 and unsigned["flags"]["C"]
    assert not unsigned["flags"]["V"]
    assert alu("SUB", 0, 1)["result"] == 255
    assert alu("AND", 0b1010, 0b1100)["result"] == 0b1000
    assert alu("NOT", 0)["result"] == 255


@pytest.mark.parametrize("amount", [-1, 8, 256])
def test_invalid_shifts_are_not_silently_wrapped(amount):
    with pytest.raises(ValueError):
        alu("SHL", 1, amount)


def test_full_adder_truth_table():
    for a, b, carry in itertools.product((0, 1), repeat=3):
        result = full_adder(a, b, carry)
        assert result["sum"] + 2 * result["carry"] == a + b + carry


def build_adder_circuit():
    circuit = LogicCircuit()
    for name in ("a", "b", "cin"):
        circuit.add_gate(name, "INPUT")
    circuit.add_gate("abxor", "XOR", ["a", "b"])
    circuit.add_gate("sumxor", "XOR", ["abxor", "cin"])
    circuit.add_gate("abcarry", "AND", ["a", "b"])
    circuit.add_gate("ccarry", "AND", ["abxor", "cin"])
    circuit.add_gate("carryor", "OR", ["abcarry", "ccarry"])
    circuit.add_gate("sum", "OUTPUT", ["sumxor"])
    circuit.add_gate("carry", "OUTPUT", ["carryor"])
    return circuit


def test_connected_gates_compute_all_adder_inputs_and_roundtrip():
    circuit = LogicCircuit.from_dict(build_adder_circuit().to_dict())
    for a, b, carry in itertools.product((0, 1), repeat=3):
        output = circuit.evaluate({"a": a, "b": b, "cin": carry})["outputs"]
        assert output["sum"] + 2 * output["carry"] == a + b + carry


def test_logic_cycles_missing_wires_and_invalid_inputs_fail():
    circuit = LogicCircuit()
    circuit.add_gate("a", "NOT", ["b"])
    circuit.add_gate("b", "NOT", ["a"])
    with pytest.raises(ValueError):
        circuit.evaluate()
    circuit.gates["b"]["inputs"] = ["missing"]
    with pytest.raises(ValueError):
        circuit.evaluate()
    with pytest.raises(ValueError):
        full_adder(2, 0)

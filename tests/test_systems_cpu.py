import json

import pytest

from netlab.systems import CPU


def test_instruction_execution_branch_memory_and_flags():
    cpu = CPU()
    cpu.load("MOV R0,5\nMOV R1,0\nloop: ADD R1,R0\nSUB R0,1\nJNZ loop\nSTORE 10,R1\nLOAD R2,10\nHALT")
    trace = cpu.run()
    assert cpu.halted
    assert cpu.registers["R1"] == 15
    assert cpu.registers["R2"] == 15 and cpu.memory[10] == 15
    assert any(row["pc_after"] < row["pc_before"] for row in trace)


def test_cpu_send_preserves_bytes_and_emits_network_pipeline():
    cpu = CPU()
    cpu.load("STORE 1,72\nSTORE 2,105\nSEND 1,2\nHALT")
    cpu.run()
    assert cpu.sent_messages[0]["payload_hex"] == "4869"
    assert {row["kind"] for row in cpu.events} >= {"os.syscall", "os.socket_buffer", "nic.dma", "network.send"}
    assert all(row["teaching_model"] for row in cpu.events)


def test_cpu_recv_teaching_loopback_and_stack():
    cpu = CPU()
    cpu.load("MOV R0,42\nPUSH R0\nMOV R0,0\nPOP R1\nSTORE 1,R1\nSEND 1,1\nRECV 10,1\nHALT")
    cpu.run()
    assert cpu.registers["R1"] == 42 and cpu.memory[10] == 42
    assert cpu.stack_pointer == cpu.memory_size


@pytest.mark.parametrize("program", ["BAD 1", "MOV R8,1", "MOV R0", "JMP missing", "foo: NOP\nfoo: HALT", "JMP 99"])
def test_invalid_assembly_is_rejected(program):
    with pytest.raises(ValueError):
        CPU().load(program)


@pytest.mark.parametrize("program", ["LOAD R0,256", "STORE -1,R0", "SEND 250,10", "POP R0", "RECV 1,1"])
def test_memory_bounds_and_invalid_runtime_operations(program):
    cpu = CPU()
    cpu.load(program)
    with pytest.raises(ValueError):
        cpu.step()


def test_infinite_loop_has_bounded_run():
    cpu = CPU()
    cpu.load("loop: JMP loop")
    assert len(cpu.run(7)) == 7
    assert not cpu.halted and cpu.pc == 0


def test_snapshot_resume_and_snapshot_copy_isolation():
    cpu = CPU()
    cpu.load("MOV R0,4\nADD R0,3\nSTORE 7,R0\nHALT")
    cpu.step()
    snapshot = json.loads(json.dumps(cpu.snapshot()))
    restored = CPU.restore(snapshot)
    snapshot["memory"][0] = 900
    assert cpu.memory[0] == restored.memory[0] == 0
    assert cpu.run() == restored.run()
    assert cpu.snapshot() == restored.snapshot()


def test_reset_clears_state_and_preserves_program():
    cpu = CPU()
    cpu.load("MOV R0,1\nHALT")
    cpu.run()
    cpu.reset()
    assert cpu.pc == 0 and cpu.registers["R0"] == 0 and not cpu.events
    cpu.run()
    assert cpu.registers["R0"] == 1


def test_external_receive_queue_is_explicit_and_preserves_unread_tail():
    cpu = CPU(receive_policy="external")
    cpu.load("RECV 10,1\nRECV 11,1\nHALT")
    cpu.queue_receive(b"AB", "virtual-reply")
    cpu.step()
    assert cpu.memory[10] == 65 and cpu.receive_queue[0]["payload_hex"] == "42"
    restored = CPU.restore(cpu.snapshot())
    restored.run()
    assert restored.memory[11] == 66 and not restored.receive_queue

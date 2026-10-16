import copy

import pytest

from netlab.core.topology import example_topology
from netlab.systems import cpu_network_experiment


def test_cpu_bytes_cross_switch_routing_nat_and_return_to_memory():
    result = cpu_network_experiment(seed=7)
    assert result["results"]["success"]
    assert result["cpu"]["memory"][128:130] == [72, 105]
    outcome = result["messages"][0]
    assert outcome["sent_hex"] == outcome["received_hex"] == "4869"
    kinds = {event["kind"] for event in result["events"]}
    assert kinds >= {"cpu.fetch", "os.syscall", "nic.dma", "ARP_REQUEST", "MAC_LEARN", "ROUTE", "NAT_OUT", "NAT_IN", "APPLICATION_ECHO", "memory.receive"}
    send_event = next(event for event in result["events"] if event["kind"] == "network.send")
    assert send_event["packet_id"] == outcome["request_packet_id"]
    assert any(event["kind"] == "NAT_IN" and event["packet_id"] == outcome["reply_packet_id"] for event in result["events"])
    assert len({event["id"] for event in result["events"]}) == len(result["events"])
    assert [event["time"] for event in result["events"]] == sorted(event["time"] for event in result["events"])


def test_link_failure_does_not_fabricate_echo():
    topology = example_topology("home")
    topology["links"][2]["up"] = False
    result = cpu_network_experiment(topology=topology)
    assert not result["results"]["success"]
    assert result["results"]["messages_received"] == 0
    assert not any(event["kind"] in ("APPLICATION_ECHO", "memory.receive") for event in result["events"])
    assert "received_hex" not in result["messages"][0]


def test_arbitrary_binary_payload_and_same_seed_reproducibility():
    program = "STORE 1,0\nSTORE 2,255\nSEND 1,2\nHALT"
    first = cpu_network_experiment(program, seed=12)
    second = cpu_network_experiment(program, seed=12)
    assert first == second
    assert first["messages"][0]["received_hex"] == "00ff"
    assert first["cpu"]["memory"][128:130] == [0, 255]


def test_no_send_and_bad_target_are_not_success():
    assert not cpu_network_experiment("HALT")["results"]["success"]
    with pytest.raises(ValueError):
        cpu_network_experiment(target="missing")


def test_mutable_topology_not_changed_and_multiple_messages():
    topology = example_topology("home")
    before = copy.deepcopy(topology)
    result = cpu_network_experiment("STORE 1,65\nSEND 1,1\nSTORE 1,66\nSEND 1,1\nHALT", topology=topology)
    assert topology == before
    assert result["results"]["messages_received"] == 2
    assert [item["received_hex"] for item in result["messages"]] == ["41", "42"]


def test_recv_instruction_consumes_only_network_delivered_bytes():
    program = "STORE 1,65\nSEND 1,1\nRECV 20,1\nLOAD R1,20\nHALT"
    result = cpu_network_experiment(program)
    assert result["results"]["success"]
    assert result["cpu"]["registers"]["R1"] == 65
    assert not result["cpu"]["receive_queue"]
    reply_id = result["messages"][0]["reply_packet_id"]
    assert any(event["kind"] == "os.wakeup" and event["packet_id"] == reply_id for event in result["events"])


def test_recv_blocks_after_network_drop_instead_of_local_loopback():
    topology = example_topology("home")
    topology["links"][2]["up"] = False
    result = cpu_network_experiment("STORE 1,65\nSEND 1,1\nRECV 20,1\nHALT", topology=topology)
    assert result["results"]["blocked"] and not result["results"]["success"]
    assert not result["results"]["execution_limit_reached"]
    assert result["cpu"]["memory"][20] == 0
    assert not any(event["kind"] == "os.wakeup" for event in result["events"])

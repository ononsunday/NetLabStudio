import json

import pytest

from netlab.core.events import EventEngine
from netlab.core.routing import bellman_ford, bgp_propagate, dijkstra, fragment_datagram, longest_prefix_match, path_mtu_experiment, route_protocol
from netlab.core.services import DHCPServer, DNSResolver, NATTable, evaluate_firewall, wifi_associate
from netlab.core.topology import NetworkSimulator, Topology, example_topology


def test_scheduler_same_time_order_and_snapshot_replay():
    engine = EventEngine(12)
    engine.schedule(2, "second")
    engine.schedule(1, "first")
    engine.schedule(1, "third")
    restored = EventEngine.restore(json.loads(json.dumps(engine.snapshot())))
    assert [restored.pop().kind for _ in range(3)] == ["first", "third", "second"]
    assert engine.rng.random() == restored.rng.random()
    with pytest.raises(ValueError):
        engine.schedule(-1, "past")
    with pytest.raises(ValueError):
        engine.schedule(float("nan"), "invalid")


def test_arp_mac_learning_and_second_ping_uses_cache():
    sim = NetworkSimulator.from_dict(example_topology())
    packet_id = sim.send("PC1", "PC2")
    result = sim.run()
    assert sim.packets[packet_id]["status"] == "delivered"
    assert result["stats"]["delivered"] == 2
    assert sim.topology.nodes["PC1"].arp["192.168.1.20"]["mac"] == sim.topology.nodes["PC2"].interfaces[0].mac
    table = sim.topology.nodes["SW1"].mac_table
    assert any(entry["port"] == "p1" for entry in table.values())
    first_requests = sum(e["kind"] == "ARP_REQUEST" for e in result["events"])
    sim.send("PC1", "PC2")
    result = sim.run()
    assert sum(e["kind"] == "ARP_REQUEST" for e in result["events"]) == first_requests


def test_neighbor_cache_expiry_causes_new_resolution():
    sim = NetworkSimulator.from_dict(example_topology())
    sim.send("PC1", "PC2")
    sim.run()
    sim.engine.time = 61
    sim.send("PC1", "PC2")
    result = sim.run()
    assert sum(e["kind"] == "ARP_REQUEST" for e in result["events"]) == 2


def test_vlan_isolation_is_not_a_fake_success():
    topology = example_topology()
    topology["nodes"][1]["interfaces"][0]["vlan"] = 20
    topology["nodes"][2]["interfaces"][1]["vlan"] = 20
    sim = NetworkSimulator.from_dict(topology)
    packet = sim.send("PC1", "PC2")
    result = sim.run()
    assert sim.packets[packet]["status"] == "dropped"
    assert result["stats"]["delivered"] == 0


def test_router_ttl_and_nat_return_path():
    sim = NetworkSimulator.from_dict(example_topology())
    packet_id = sim.send("PC1", "WEB")
    result = sim.run()
    assert sim.packets[packet_id]["path"] == ["PC1", "R1", "WEB"]
    reply = next(packet for packet in result["packets"] if packet.get("reply"))
    assert reply["path"] == ["WEB", "R1", "PC1"]
    assert reply["status"] == "delivered"
    assert any(e["kind"] == "NAT_IN" for e in result["events"])
    sim.reset()
    packet = sim.send("PC1", "WEB", ttl=1)
    assert sim.run()["stats"]["dropped"] == 1
    assert sim.packets[packet]["ttl"] == 0


def test_ipv6_neighbor_discovery_and_routing():
    sim = NetworkSimulator.from_dict(example_topology("ipv6"))
    sim.send("PC1", "WEB")
    result = sim.run()
    assert result["stats"]["delivered"] == 2
    assert any(e["kind"] == "ND_REQUEST" for e in result["events"])
    assert not any(e["kind"] == "ARP_REQUEST" for e in result["events"])


def test_snapshot_mid_frame_reproduces_result_exactly():
    topology = example_topology()
    for link in topology["links"]:
        link.update(jitter_ms=2, loss=0.04)
    sim = NetworkSimulator.from_dict(topology, 43)
    sim.send("PC1", "WEB")
    for _ in range(8):
        sim.step()
    clone = NetworkSimulator.restore(json.loads(json.dumps(sim.snapshot())))
    assert sim.run() == clone.run()


def test_snapshot_preserves_learned_mac_tables_in_spanning_tree_topology():
    nodes = [{"id": f"S{i}", "type": "switch", "interfaces": [{"name": "a"}, {"name": "b"}, {"name": "c"}]} for i in range(3)]
    nodes.extend([{"id": "A", "interfaces": [{"name": "eth0", "ip": "192.0.2.1/24"}]},
                  {"id": "B", "interfaces": [{"name": "eth0", "ip": "192.0.2.2/24"}]}])
    links = [{"id": "x", "a": "S0:a", "b": "S1:a"}, {"id": "y", "a": "S1:b", "b": "S2:a"},
             {"id": "z", "a": "S2:b", "b": "S0:b", "cost": 2},
             {"id": "a", "a": "A:eth0", "b": "S0:c"}, {"id": "b", "a": "B:eth0", "b": "S2:c"}]
    sim = NetworkSimulator.from_dict({"nodes": nodes, "links": links})
    sim.send("A", "B")
    sim.run()
    sim.send("A", "B")
    sim.step()
    clone = NetworkSimulator.restore(json.loads(json.dumps(sim.snapshot())))
    assert sim.topology.nodes["S0"].mac_table
    assert sim.topology.nodes["S0"].mac_table == clone.topology.nodes["S0"].mac_table
    assert sim.run() == clone.run()


def test_failed_link_and_mtu_produce_reason():
    sim = NetworkSimulator.from_dict(example_topology())
    sim.set_link("L3", False)
    packet = sim.send("PC1", "WEB")
    result = sim.run()
    assert sim.packets[packet]["status"] == "dropped"
    assert any("无应答" in e["explanation"] for e in result["events"])
    sim.reset()
    packet = sim.send("PC1", "PC2", size=2000)
    result = sim.run()
    assert sim.packets[packet]["status"] == "dropped"
    assert any("MTU" in e["explanation"] for e in result["events"])


def test_tcp_topology_three_way_handshake():
    sim = NetworkSimulator.from_dict(example_topology())
    sim.send("PC1", "WEB", "TCP", destination_port=443)
    result = sim.run()
    assert result["stats"]["delivered"] == 3
    assert {packet.get("tcp_flags") for packet in result["packets"] if packet["protocol"] == "TCP"} == {"SYN", "SYN,ACK", "ACK"}
    assert result["stats"]["dropped"] == 0


def test_longest_prefix_beats_default_and_metric_breaks_tie():
    routes = [{"network": "0.0.0.0/0", "interface": "wan"},
              {"network": "10.0.0.0/8", "interface": "lan", "metric": 1},
              {"network": "10.1.0.0/16", "interface": "a", "metric": 10},
              {"network": "10.1.0.0/16", "interface": "b", "metric": 2}]
    assert longest_prefix_match("10.1.2.3", routes)["interface"] == "b"
    assert longest_prefix_match("8.8.8.8", routes)["interface"] == "wan"
    assert longest_prefix_match("2001:db8::1", routes) is None


def test_shortest_paths_and_negative_cycle():
    graph = {"A": {"B": 2, "C": 9}, "B": {"C": 3}, "C": {}}
    for fn in (dijkstra, bellman_ford):
        result = fn(graph, "A")
        assert result["paths"]["C"] == ["A", "B", "C"]
        assert result["distances"]["C"] == 5
    with pytest.raises(ValueError):
        bellman_ford({"A": {"B": -2}, "B": {"A": 1}}, "A")
    with pytest.raises(ValueError):
        dijkstra({"A": {"B": -1}}, "A")


def test_route_protocol_link_failure_recomputes_reachability():
    topology = example_topology()
    result = route_protocol(topology, "OSPF")
    assert next(row for row in result["tables"]["PC1"] if row["destination"] == "WEB")["path"] == ["PC1", "SW1", "R1", "WEB"]
    topology["links"][2]["up"] = False
    result = route_protocol(topology, "RIP")
    assert not any(row["destination"] == "WEB" for row in result["tables"]["PC1"])


@pytest.mark.parametrize("protocol", ["RIP", "OSPF", "BGP"])
def test_dynamic_routes_install_into_shared_forwarding_state(protocol):
    sim = NetworkSimulator.from_dict(example_topology("routed"))
    failed = sim.send("PC1", "WEB")
    sim.run()
    assert sim.packets[failed]["status"] == "dropped"
    convergence = sim.configure_routing(protocol)
    assert any(route["network"] == "10.20.0.0/24" and route["gateway"] == "203.0.113.2"
               for route in convergence["tables"]["R1"])
    packet = sim.send("PC1", "WEB")
    result = sim.run()
    assert sim.packets[packet]["status"] == "delivered"
    assert sim.packets[packet]["path"] == ["PC1", "R1", "R2", "WEB"]
    assert next(p for p in result["packets"] if p.get("reply"))["path"] == ["WEB", "R2", "R1", "PC1"]
    sim.set_link("L4", False)
    sim.configure_routing(protocol)
    assert not any(route.get("protocol") == protocol for route in sim.topology.nodes["R1"].routes)


def test_stp_blocks_loop_and_recovers_tree():
    nodes = [{"id": f"S{i}", "type": "switch", "interfaces": [{"name": "a"}, {"name": "b"}]} for i in range(3)]
    links = [{"id": "x", "a": "S0:a", "b": "S1:a", "cost": 1},
             {"id": "y", "a": "S1:b", "b": "S2:a", "cost": 1},
             {"id": "z", "a": "S2:b", "b": "S0:b", "cost": 2}]
    sim = NetworkSimulator.from_dict({"nodes": nodes, "links": links})
    assert sim.blocked_links == {"z"}
    sim.set_link("x", False)
    assert not sim.blocked_links


@pytest.mark.parametrize("name", ["vlan_routed", "trunk"])
def test_inter_vlan_routing_and_trunk_tags(name):
    sim = NetworkSimulator.from_dict(example_topology(name))
    sim.send("PC1", "PC2")
    result = sim.run()
    assert result["stats"]["delivered"] == 2
    assert result["stats"]["dropped"] == 0
    assert next(packet for packet in result["packets"] if packet["protocol"] == "ICMP" and not packet.get("reply"))["path"] == ["PC1", "R1", "PC2"]
    if name == "trunk":
        assert any(e["kind"] == "FRAME_SEND" and e["data"]["tagged"] for e in result["events"])


def test_bgp_actual_neighbor_propagation_and_as_loop_rejection():
    graph = {"A": {"B": 1}, "B": {"A": 1, "C": 1}, "C": {"B": 1, "D": 1}, "D": {"C": 1}}
    result = bgp_propagate(graph, {"A": 1, "B": 1, "C": 2, "D": 3})
    row = next(row for row in result["tables"]["A"] if row["destination"] == "D")
    assert row["path"] == ["A", "B", "C", "D"]
    assert row["as_path"] == [1, 2, 3]
    assert result["steps"][2]["updates"]
    looped = bgp_propagate(graph, {"A": 1, "B": 2, "C": 1, "D": 3})
    assert any(event["kind"] == "BGP_AS_LOOP_REJECT" for event in looped["events"])
    assert not any(row["destination"] == "D" for row in looped["tables"]["A"])


def test_ipv4_fragment_alignment_offsets_mf_and_reassembly_lengths():
    result = fragment_datagram(4000, 1500)
    fragments = result["fragments"]
    assert [row["fragment_offset"] for row in fragments] == [0, 185, 370]
    assert [row["more_fragments"] for row in fragments] == [True, True, False]
    assert [row["total_length"] for row in fragments] == [1500, 1500, 1040]
    assert sum(row["payload_size"] for row in fragments) == 3980
    assert all(row["payload_size"] % 8 == 0 for row in fragments[:-1])
    for previous, current in zip(fragments, fragments[1:]):
        assert previous["offset_bytes"] + previous["payload_size"] == current["offset_bytes"]


def test_df_and_ipv6_router_fragmentation_fail_without_fake_fragments():
    for version, df in [(4, True), (6, False), (6, True)]:
        result = fragment_datagram(4000, 1500, version, df)
        assert result["error"]
        assert not result["fragments"]
    assert fragment_datagram(1500, 1500)["fragmented"] is False
    result = path_mtu_experiment(4000, [1500, 1400, 1280], 6)
    assert result["successful_probe_size"] == 1280
    assert result["probes"] == 4
    assert sum(e["kind"] == "PACKET_TOO_BIG" for e in result["events"]) == 3
    with pytest.raises(ValueError):
        fragment_datagram(4000, 1000, 6)


def test_dhcp_unique_pool_renewal_expiry_and_exhaustion():
    dhcp = DHCPServer(start=100, end=101, lease_seconds=10)
    first, second = dhcp.allocate("AA", 0), dhcp.allocate("BB", 0)
    assert first["address"] != second["address"]
    with pytest.raises(RuntimeError):
        dhcp.allocate("CC", 0)
    assert dhcp.request("AA", first["address"], 5)["expires"] == 15
    third = dhcp.allocate("CC", 11)
    assert third["address"] == second["address"]
    assert dhcp.request("DD", first["address"], 11)["message"] == "NAK"


def test_dhcp_applies_actual_client_state():
    sim = NetworkSimulator.from_dict(example_topology())
    lease = sim.request_dhcp("PC1", "R1")
    assert sim.topology.nodes["PC1"].interfaces[0].ip == lease["address"] + "/24"
    sim.send("PC1", "WEB")
    assert sim.run()["stats"]["delivered"] == 2


def test_dhcp_refuses_disconnected_client_vlan_and_closed_server():
    sim = NetworkSimulator.from_dict(example_topology())
    sim.set_link("L3", False)
    with pytest.raises(RuntimeError):
        sim.request_dhcp("PC1", "R1")
    sim.reset()
    sim.set_device("R1", False)
    with pytest.raises(RuntimeError):
        sim.request_dhcp("PC1", "R1")
    sim.reset()
    sim.topology.nodes["SW1"].interfaces[0].vlan = 20
    with pytest.raises(RuntimeError):
        sim.request_dhcp("PC1", "R1")


@pytest.mark.parametrize("fail_target", ["link", "device"])
def test_in_flight_frames_recheck_failure_at_arrival(fail_target):
    sim = NetworkSimulator.from_dict(example_topology())
    packet = sim.send("PC1", "PC2")
    sim.step()  # queues an ARP frame on the PC1→SW1 link
    if fail_target == "link":
        sim.set_link("L1", False)
    else:
        sim.set_device("SW1", False)
    result = sim.run()
    assert sim.packets[packet]["status"] == "dropped"
    assert result["stats"]["delivered"] == 0
    assert any("帧到达前" in e["explanation"] for e in result["events"])


def test_nat_expiry_protocol_separation_and_port_forward():
    table = NATTable(timeout=10)
    udp = table.outbound("192.168.1.2", 5000, "UDP")
    tcp = table.outbound("192.168.1.2", 5000, "TCP")
    assert udp["public_port"] != tcp["public_port"]
    assert table.inbound(udp["public_port"], "UDP", 5)["private_ip"] == "192.168.1.2"
    assert table.inbound(udp["public_port"], "TCP", 5) is None
    assert table.inbound(udp["public_port"], "UDP", 11) is None
    table.add_forward(25565, "192.168.1.3", 25565)
    assert table.inbound(25565, "TCP", 100)["forward"] is True
    assert NATTable.from_dict(json.loads(json.dumps(table.to_dict()))).inbound(25565, "TCP")["private_ip"] == "192.168.1.3"


def test_dns_ttl_and_firewall_and_wifi_roaming():
    resolver = DNSResolver()
    assert resolver.query("example.test", now=0)["cached"] is False
    assert resolver.query("example.test", now=10)["cached"] is True
    assert resolver.query("example.test", now=121)["cached"] is False
    assert resolver.query("absent.test")["rcode"] == "NXDOMAIN"
    packet = {"protocol": "TCP", "destination_port": 443, "source_ip": "192.168.1.3", "destination_ip": "203.0.113.10"}
    assert evaluate_firewall(packet, [{"protocol": "TCP", "port": 443, "action": "allow"}])["action"] == "allow"
    assert evaluate_firewall(packet, [])["action"] == "deny"
    ui_packet = {"protocol": "TCP", "source": "10.0.0.2", "destination": "10.0.0.8", "dport": 23}
    assert evaluate_firewall(ui_packet, [{"action": "allow", "protocol": "TCP", "dport": 443},
                                         {"action": "deny", "protocol": "TCP", "dport": 23}])["matched_rule"] == 1
    aps = [{"id": "A", "x": 0, "y": 0}, {"id": "B", "x": 100, "y": 0}]
    assert wifi_associate(aps, (1, 0))["associated"] == "A"
    assert wifi_associate(aps, (99, 0), "A")["associated"] == "B"


@pytest.mark.parametrize("updates", [{"loss": 1.1}, {"bandwidth_mbps": 0}, {"delay_ms": -1}, {"loss": float("nan")}])
def test_invalid_link_rejected(updates):
    topology = example_topology()
    topology["links"][0].update(updates)
    with pytest.raises(ValueError):
        NetworkSimulator.from_dict(topology)


def test_virtual_packet_bytes_are_analyzable_without_sending():
    scapy = pytest.importorskip("scapy.all")
    sim = NetworkSimulator.from_dict(example_topology())
    identifier = sim.send("PC1", "PC2", "UDP", "sample", destination_port=12345)
    sim.run()
    frame = scapy.Ether(sim.packet_bytes(identifier))
    assert frame[scapy.IP].src == "192.168.1.10"
    assert frame[scapy.UDP].dport == 12345
    assert frame[scapy.Raw].load == b"sample"
    assert frame[scapy.IP].len == 34
    assert frame[scapy.UDP].len == 14
    assert len(bytes(frame)) == 60  # Ethernet padding is outside the IP datagram.


def test_virtual_ipv6_tcp_size_and_explicit_payload_padding():
    scapy = pytest.importorskip("scapy.all")
    sim = NetworkSimulator.from_dict(example_topology("ipv6"))
    identifier = sim.send("PC1", "PC2", "TCP")
    sim.run()
    assert sim.packets[identifier]["size"] == 60
    frame = scapy.Ether(sim.packet_bytes(identifier))
    assert len(bytes(frame[scapy.IPv6])) == 60
    sim = NetworkSimulator.from_dict(example_topology())
    identifier = sim.send("PC1", "PC2", "UDP", "sample", size=500)
    sim.run()
    frame = scapy.Ether(sim.packet_bytes(identifier))
    assert frame[scapy.IP].len == 500
    assert bytes(frame[scapy.Raw]).startswith(b"sample")
    with pytest.raises(ValueError):
        sim.send("PC1", "PC2", "TCP", size=28)

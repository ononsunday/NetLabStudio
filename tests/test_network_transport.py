import pytest

from netlab.core.experiments import fault_experiment, game_experiment, home_experiment, nat_traversal, performance_experiment, website_experiment
from netlab.core.transport import internet_checksum, simulate_connection_control, simulate_quic, simulate_tcp, simulate_udp


def test_tcp_handshake_close_sequence_and_ack_bytes():
    result = simulate_tcp(loss=0, jitter_ms=0, bytes_total=3000)
    assert result["metrics"]["success"] is True
    assert result["metrics"]["acknowledged_bytes"] == 3000
    assert result["states"] == {"client": "CLOSED", "server": "CLOSED"}
    states = [row["to"] for row in result["state_history"]]
    assert "SYN_SENT" in states and "SYN_RECEIVED" in states
    assert "ESTABLISHED" in states and "FIN_WAIT_1" in states and "TIME_WAIT" in states
    data = [event["data"] for event in result["events"] if event["kind"] == "TCP_SEND" and event["data"]["flag"] == "DATA"]
    assert sum(row["size"] for row in data) == 3000
    assert data[0]["sequence"] == 1001


def test_tcp_loss_retransmits_and_ack_completes_deterministically():
    result = simulate_tcp(loss=0.15, seed=4)
    assert result == simulate_tcp(loss=0.15, seed=4)
    assert result["metrics"]["lost_packets"] > 0
    assert result["metrics"]["retransmissions"] > 0
    assert result["metrics"]["success"] is True
    assert any(event["kind"] in {"RETRANSMIT_TIMEOUT", "FAST_RETRANSMIT"} for event in result["events"])


def test_tcp_total_loss_fails_and_receive_window_limits_flight():
    result = simulate_tcp(loss=1, bytes_total=1024)
    assert result["metrics"]["success"] is False
    assert result["metrics"]["delivered_bytes"] == 0
    constrained = simulate_tcp(loss=0, receive_window=512, bytes_total=4096)
    assert all(row["in_flight"] <= 512 for row in constrained["window_history"])
    assert constrained["metrics"]["success"] is True


def test_delay_and_bandwidth_change_stateful_results():
    fast = simulate_tcp(loss=0, delay_ms=1, jitter_ms=0, bandwidth_mbps=100)
    slow = simulate_tcp(loss=0, delay_ms=100, jitter_ms=0, bandwidth_mbps=0.1)
    assert slow["metrics"]["duration_ms"] > fast["metrics"]["duration_ms"]
    assert slow["metrics"]["goodput_mbps"] < fast["metrics"]["goodput_mbps"]


def test_udp_loss_no_retransmission_vs_application_reliability():
    unreliable = simulate_udp(loss=0.3, seed=1)
    reliable = simulate_udp(loss=0.3, seed=1, reliable=True)
    assert unreliable["metrics"]["delivered_bytes"] < unreliable["metrics"]["requested_bytes"]
    assert unreliable["metrics"]["retransmissions"] == 0
    assert reliable["metrics"]["delivered_bytes"] == reliable["metrics"]["requested_bytes"]
    assert reliable["metrics"]["retransmissions"] > 0
    assert reliable["metrics"]["out_of_order"] > 0


def test_quic_independent_stream_recovery_and_handshake_failure():
    result = simulate_quic(loss=0.15, seed=4, streams=3)
    assert result["metrics"]["success"] is True
    assert sum(result["stream_bytes"]) == 8192
    assert result["metrics"]["retransmissions"] > 0
    assert any(event["kind"] == "PATH_CHALLENGE" for event in result["events"])
    assert {event["data"]["stream_id"] for event in result["events"] if event["kind"] == "STREAM_DELIVER"} == {0, 1, 2}
    failed = simulate_quic(loss=1)
    assert failed["metrics"]["success"] is False
    assert failed["metrics"]["delivered_bytes"] == 0
    assert failed["states"]["connection"] == "HANDSHAKE_FAILED"


def test_checksum_and_invalid_parameters():
    assert internet_checksum(bytes.fromhex("0001f203f4f5f6f7")) == 0x220D
    assert internet_checksum(b"\x01") == 0xFEFF
    for fn in [simulate_tcp, simulate_udp, simulate_quic]:
        with pytest.raises(ValueError):
            fn(loss=-0.1)
        with pytest.raises(ValueError):
            fn(bytes_total=0)
        with pytest.raises(ValueError):
            fn(delay_ms=float("nan"))


def test_integrated_home_dhcp_and_routed_echo():
    result = home_experiment()
    assert result["results"]["success"] is True
    assert len(result["results"]["leases"]) == 2
    assert result["stats"]["delivered"] == 4
    assert any(event["kind"] == "DHCP_ACK" for event in result["events"])
    assert any(event["kind"] == "NAT_OUT" for event in result["events"])


@pytest.mark.parametrize("fault", ["gateway", "link", "vlan", "dns", "route"])
def test_fault_generation_has_real_failure_evidence(fault):
    result = fault_experiment(fault)
    assert result["fault"] == fault
    if fault == "dns":
        assert result["dns"]["rcode"] == "NXDOMAIN"
    else:
        assert result["stats"]["dropped"] >= 1
        assert result["evidence"]["drop_reasons"]


def test_website_failure_does_not_show_success_response():
    result = website_experiment("https://example.test", loss=1)
    assert result["results"]["success"] is False
    assert not any(event["kind"] == "HTTP_RESPONSE" for event in result["events"])
    good = website_experiment("https://example.test", loss=0)
    assert good["results"]["success"] is True
    assert any(event["kind"] == "TLS13_STEP" for event in good["events"])
    with pytest.raises(ValueError):
        website_experiment("file:///private")


def test_website_tls_request_application_response_close_order():
    tcp = website_experiment("https://example.test", loss=0)
    events = tcp["events"]
    tls_finished = max(e["time"] for e in events if e["kind"] == "TLS13_STEP")
    request = next(e["time"] for e in events if e["kind"] == "HTTP_REQUEST")
    payload = min(e["time"] for e in events if e["kind"] == "TCP_SEND" and e["data"]["flag"] == "DATA")
    response = next(e["time"] for e in events if e["kind"] == "HTTP_RESPONSE")
    final_ack = max(e["time"] for e in events if e["kind"] == "ACK_PROGRESS")
    fin = min(e["time"] for e in events if e["kind"] == "TCP_SEND" and e["data"]["flag"] == "FIN")
    assert tls_finished <= request < payload < final_ack < response < fin
    quic = website_experiment("https://example.test", "QUIC", loss=0)
    events = quic["events"]
    established = next(e["time"] for e in events if e["kind"] == "QUIC_ESTABLISHED")
    request = next(e["time"] for e in events if e["kind"] == "HTTP_REQUEST")
    payload = min(e["time"] for e in events if e["kind"] == "QUIC_STREAM_SEND")
    response = next(e["time"] for e in events if e["kind"] == "HTTP_RESPONSE")
    delivered = max(e["time"] for e in events if e["kind"] == "STREAM_DELIVER")
    assert established <= request < payload < delivered < response


@pytest.mark.parametrize("transport", ["TCP", "QUIC"])
def test_website_equal_time_phases_order_correctly_at_zero_delay(transport):
    result = website_experiment("https://example.test", transport, loss=0, delay_ms=0, jitter_ms=0)
    events = result["events"]
    established = next(i for i,e in enumerate(events) if e["kind"] == "QUIC_ESTABLISHED" or
                       e["kind"] == "TCP_STATE" and e.get("data", {}).get("side") == "client" and e.get("data", {}).get("to") == "ESTABLISHED")
    request = next(i for i,e in enumerate(events) if e["kind"] == "HTTP_REQUEST")
    data = next(i for i,e in enumerate(events) if e["kind"] == "QUIC_STREAM_SEND" or
                e["kind"] == "TCP_SEND" and e["data"].get("flag") == "DATA")
    assert established < request < data
    if transport == "TCP":
        tls = [i for i,e in enumerate(events) if e["kind"] == "TLS13_STEP"]
        assert established < min(tls) < max(tls) < request


def test_game_parameters_change_authoritative_and_render_states():
    fast = game_experiment(delay_ms=10, loss=0, duration=2, jitter_ms=0)
    slow = game_experiment(delay_ms=300, loss=0.3, duration=2, jitter_ms=0)
    assert fast["frames"] != slow["frames"]
    assert slow["results"]["mean_display_error"] > fast["results"]["mean_display_error"]
    assert nat_traversal("restricted", "restricted")["path"] == "direct"
    assert nat_traversal("symmetric", "restricted")["path"] == "relay"


def test_packet_processing_limited_buffer_and_cpu_effect():
    fast = performance_experiment(cpu_mhz=1000, packet_size=1024, buffer_size=4096)
    slow = performance_experiment(cpu_mhz=0.1, packet_size=1024, buffer_size=1024)
    assert fast["results"]["processed"] == 32
    assert slow["results"]["dropped"] > 0
    assert slow["results"]["throughput_mbps"] < fast["results"]["throughput_mbps"]
    batch = performance_experiment(io_mode="batch")
    assert batch["results"]["cpu_cycles"] < fast["results"]["cpu_cycles"]


def test_keepalive_probe_sequence_and_timeout_local_state():
    result = simulate_connection_control()
    assert result["states"] == {"client": "ESTABLISHED", "server": "ESTABLISHED"}
    assert result["metrics"]["probes"] == 1
    probe = next(e for e in result["events"] if e["kind"] == "KEEPALIVE_TIMER")
    assert probe["data"]["sequence"] == probe["data"]["next_sequence"] - 1
    dead = simulate_connection_control(peer_alive=False)
    assert dead["states"]["client"] == "CLOSED"
    assert dead["metrics"]["probes"] == 3
    lost = simulate_connection_control(loss=1)
    assert lost["states"]["client"] == "CLOSED"
    assert lost["states"]["server"] == "ESTABLISHED"


def test_rst_valid_invalid_and_lost_have_distinct_state():
    valid = simulate_connection_control("reset")
    assert valid["states"] == {"client": "CLOSED", "server": "CLOSED"}
    invalid = simulate_connection_control("reset", valid_sequence=False)
    assert invalid["states"]["client"] == "ESTABLISHED"
    assert any(e["kind"] == "TCP_CHALLENGE_ACK" for e in invalid["events"])
    lost = simulate_connection_control("reset", loss=1)
    assert lost["states"] == {"client": "ESTABLISHED", "server": "CLOSED"}

"""Behavior regressions through actual Qt controls, using one local window.

These tests never contact an external network. Engines behind the GUI must
produce the result being displayed, saved and restored.
"""
import copy
import json
import time

import pytest
from PySide6.QtCore import QAbstractAnimation, QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from netlab.core.topology import example_topology
from netlab.storage import Database
from netlab.ui.window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def wait_jobs(window, timeout=15):
    deadline = time.monotonic() + timeout
    while window.jobs and time.monotonic() < deadline:
        QApplication.processEvents()
        QTest.qWait(10)
    assert not window.jobs, "The bounded local GUI task did not complete."
    QApplication.processEvents()


@pytest.fixture(scope="module")
def shared_window(qapp, tmp_path_factory):
    folder = tmp_path_factory.mktemp("ui-regressions")
    window = MainWindow(Database(folder / "regression.sqlite3"), folder)
    window.show()
    qapp.processEvents()
    yield window
    wait_jobs(window)
    window.close()
    qapp.processEvents()


@pytest.fixture
def window(shared_window):
    wait_jobs(shared_window)
    yield shared_window
    wait_jobs(shared_window)
    # Stop only animation/monitor timers belonging to this test window.
    for timer in shared_window.findChildren(QTimer):
        timer.stop()
    for animation in shared_window.findChildren(QAbstractAnimation):
        animation.stop()


def click(page, text):
    matches = [button for button in page.findChildren(QPushButton) if button.text() == text]
    assert len(matches) == 1, f"Expected a single actual button labeled {text!r}."
    assert matches[0].isEnabled()
    QTest.mouseClick(matches[0], Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def save_template(page, name, monkeypatch):
    monkeypatch.setattr("netlab.ui.common.QInputDialog.getText", lambda *args, **kwargs: (name, True))
    click(page, "保存为模板")
    return next(row["config"] for row in page.window.db.list_templates() if row["name"] == name)


def test_gate_drag_after_numeric_tool_preserves_actual_circuit(window):
    page = window.pages["binary"]
    window.navigate("binary")
    click(page, "全加器示例")
    before = json.loads(page.circuit.toPlainText())
    assert before["gates"] and page.gate_items
    assert len(page.scene.items()) >= 32
    assert all(gate.label.toPlainText().strip() for gate in page.gate_items.values())
    click(page, "原码 / 反码 / 补码")
    item = page.gate_items["a"]
    old_position = item.pos()
    page.view.centerOn(item)
    QApplication.processEvents()
    start = page.view.mapFromScene(item.sceneBoundingRect().center())
    end = start + QPoint(32, 17)
    QTest.mousePress(page.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(page.view.viewport(), end, 20)
    QTest.mouseRelease(page.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    QApplication.processEvents()
    assert item.pos() != old_position, "The actual gate did not move on the graphics canvas."
    after = json.loads(page.circuit.toPlainText())
    assert after["gates"] == before["gates"]
    assert after["positions"]["a"] == {"x": item.pos().x(), "y": item.pos().y()}
    click(page, "计算电路")
    assert page.result["outputs"]["sum_out"] == 0
    assert page.result["outputs"]["carry_out"] == 1
    assert len(page.scene.items()) >= 32
    assert all(gate.label.toPlainText().strip() for gate in page.gate_items.values())


def test_cpu_template_then_editor_change_runs_current_assembly(window):
    page = window.pages["cpu"]
    window.navigate("cpu")
    page.apply_config({"assembly": "MOV R0, 17\nHALT"})
    click(page, "运行")
    assert page.result["registers"]["R0"] == 17
    page.code.setPlainText("MOV R0, 99\nHALT")
    click(page, "运行")  # The user does not have to reset/assemble after every edit.
    assert page.result["halted"] is True
    assert page.result["registers"]["R0"] == 99
    assert page.config["assembly"] == page.code.toPlainText()


@pytest.mark.parametrize("protocol", ["UDP", "QUIC"])
def test_saved_transport_protocol_matches_clicked_operation(window, protocol, monkeypatch):
    page = window.pages["transport"]
    window.navigate("transport")
    page.protocol.setCurrentText(protocol)
    page.size.setValue(1536)
    page.loss.setValue(0)
    click(page, "运行协议实验")
    # Changing the selector while the worker runs must not alter saved provenance.
    page.protocol.setCurrentText("TCP")
    wait_jobs(window)
    assert page.result["protocol"] == protocol
    assert page.config["protocol"] == protocol
    assert page.config["bytes_total"] == 1536
    config = save_template(page, "transport-" + protocol, monkeypatch)
    page.apply_config(config)
    assert page.protocol.currentText() == protocol
    click(page, "运行协议实验")
    wait_jobs(window)
    assert page.result["protocol"] == protocol
    assert page.result["metrics"]["delivered_bytes"] == 1536


def test_vlsm_template_restores_base_and_requested_hosts(window, monkeypatch):
    page = window.pages["subnet"]
    window.navigate("subnet")
    page.cidr.setText("10.44.0.0/24")
    page.hosts.setText("20, 6")
    click(page, "规划子网")
    expected = [row["cidr"] for row in page.result]
    assert page.config == {"base": "10.44.0.0/24", "hosts": [20, 6]}
    config = save_template(page, "vlsm-base-and-hosts", monkeypatch)
    page.cidr.setText("192.0.2.0/24")
    page.hosts.setText("50, 30")
    page.apply_config(config)
    assert page.cidr.text() == "10.44.0.0/24"
    assert [int(value.strip()) for value in page.hosts.text().split(",")] == [20, 6]
    click(page, "规划子网")
    assert [row["cidr"] for row in page.result] == expected


def test_fragment_template_restores_checkbox_and_actual_behavior(window, monkeypatch):
    page = window.pages["subnet"]
    window.navigate("subnet")
    page.packet_size.setValue(4000)
    page.mtu.setValue(1400)
    page.ip_version.setCurrentText("4")
    page.df.setChecked(True)
    click(page, "计算分片")
    assert page.result["error"] and not page.result["fragments"]
    config = save_template(page, "fragment-df-checked", monkeypatch)
    page.packet_size.setValue(100)
    page.df.setChecked(False)
    page.apply_config(config)
    assert page.packet_size.value() == 4000
    assert page.df.isChecked() is True
    click(page, "计算分片")
    assert page.result["error"] and not page.result["fragments"]
    page.apply_config({**config, "df": False})
    assert page.df.isChecked() is False
    click(page, "计算分片")
    assert page.result["error"] is None
    assert len(page.result["fragments"]) > 1


def test_dhcp_sync_and_live_link_edit_keep_existing_state(window, monkeypatch):
    page = window.pages["topology"]
    window.navigate("topology")
    page.set_config(example_topology("home"))
    page.source.setCurrentText("PC1")
    page.target.setCurrentText("R1")
    click(page, "申请 DHCP")
    lease = page.result["address"]
    actual = page.sim.topology.nodes["PC1"].interfaces[0].ip
    configured = next(row for row in page.config_dict()["nodes"] if row["id"] == "PC1")["interfaces"][0]["ip"]
    assert actual == configured == lease + "/24"
    assert page.nodes["PC1"].node["interfaces"][0]["ip"] == actual
    page.target.setCurrentText("PC2")
    click(page, "发送虚拟包")
    while page.sim.engine.queue:
        page.step()
    original_sim = page.sim
    arp = copy.deepcopy(page.sim.topology.nodes["PC1"].arp)
    mac = copy.deepcopy(page.sim.topology.nodes["SW1"].mac_table)
    history = copy.deepcopy(page.sim.engine.history)
    assert arp and mac and page.sim.stats["delivered"] == 2
    item, link = next((item, link) for item, link in page.edges if link["id"] == "L3")
    page.scene.clearSelection()
    item.setSelected(True)
    monkeypatch.setattr(page, "json_editor", lambda *args: {**link, "up": False})
    click(page, "配置选中项")
    assert page.sim is original_sim
    assert page.sim.topology.nodes["PC1"].arp == arp
    assert page.sim.topology.nodes["SW1"].mac_table == mac
    assert page.sim.engine.history == history
    assert next(link for link in page.sim.topology.links if link.id == "L3").up is False
    page.source.setCurrentText("PC1")
    page.target.setCurrentText("WEB")
    click(page, "发送虚拟包")
    identifier = next(reversed(page.sim.packets))
    page.sim.run()
    assert page.sim.packets[identifier]["status"] == "dropped"
    assert page.sim.stats["delivered"] == 2  # Prior successful traffic was retained.


def test_virtual_capture_source_filter_and_timestamp_clear_stale_timeline(window):
    page = window.pages["topology"]
    capture = window.pages["capture"]
    page.set_config(example_topology("home"))
    page.source.setCurrentText("PC1")
    page.target.setCurrentText("PC2")
    page.send()
    page.sim.run()
    capture.timeline.set_events([{"time": 5, "kind": "OLD_REAL_CAPTURE", "source": "A", "target": "B"}])
    capture.timeline.all()
    capture.filter.setCurrentText("全部")
    page.analyze_packets()
    assert capture.packets
    assert all(row["kind"] == "simulation" and row["time_unit"] == "模拟秒" for row in capture.packets)
    assert all(row["hex"] and "不是本机实测" in row["origin_note"] for row in capture.packets)
    assert not capture.timeline.events
    request = next(row for row in capture.packets if row["simulation_state"]["protocol"] == "ICMP" and not row["simulation_state"].get("reply"))
    reply = next(row for row in capture.packets if row["simulation_state"].get("reply"))
    assert request["time"] < reply["time"] < 0.1
    capture.filter.setCurrentText("IPv4")
    assert {row["index"] for row in capture.filtered} == {row["index"] for row in capture.packets if "IP" in row["protocols"]}
    assert capture.table.rowCount() == 2


@pytest.mark.parametrize("experiment", ["B", "E", "F"])
def test_integrated_experiments_display_computed_model_results(window, experiment):
    page = window.pages["integrated"]
    window.navigate("integrated")
    page.experiment.setCurrentIndex("ABCDEF".index(experiment))
    page.packet_size.setValue(1024)
    page.buffer_size.setValue(4096)
    page.io_mode.setCurrentText("batch")
    click(page, "开始综合实验")
    wait_jobs(window)
    result = page.result
    assert result["mode"] == "teaching_simulation"
    assert result["events"] and page.timeline.events
    assert {event["kind"] for event in page.timeline.events} == {event["kind"] for event in result["events"]}
    if experiment == "B":
        assert result["results"]["success"] is True
        assert result["stats"]["delivered"] == 4
        assert len(result["results"]["leases"]) == 2
        assert any(event["kind"] == "NAT_IN" for event in result["events"])
        assert window.pages["topology"].config_dict()["nodes"] == result["topology"]["nodes"]
    elif experiment == "E":
        assert result["results"]["network_success"] is True
        assert result["messages"][0]["echo_received"] is True
        assert result["cpu"]["memory"][128:130] == [72, 105]
        packet_ids = {packet["id"] for packet in result["packets"]}
        assert any(event["kind"] == "memory.receive" and event["packet_id"] in packet_ids for event in result["events"])
    else:
        assert result["results"]["processed"] == 32
        assert result["results"]["packet_size"] == 1024
        assert result["results"]["io_mode"] == "batch"
        assert result["results"]["cpu_cycles"] > 0
        assert {"NIC_RECEIVE", "DMA_WRITE", "OS_DISPATCH", "APP_RECEIVE"} <= {event["kind"] for event in result["events"]}

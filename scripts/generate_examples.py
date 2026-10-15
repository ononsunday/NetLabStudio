"""Reproduce local teaching fixtures; this script never transmits packets."""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scapy.all import ARP, DNS, DNSQR, DNSRR, Ether, IP, Raw, TCP, UDP, wrpcap

from netlab.core.topology import example_topology
from netlab.core.transport import simulate_tcp
from netlab.systems import cpu_network_experiment
from netlab.systems.integrated import DEFAULT_NETWORK_ASSEMBLY


CAPTURE_README = """# 教学抓包与实验结果示例

`teaching.pcap` 是生成脚本在内存中构造的 15 个教学以太网帧，包含 ARP 请求与响应、DNS 查询与应答、TCP 三次握手、HTTP 请求与响应以及 TCP 关闭。文件没有来自本机网卡的实测数据，生成过程不会发送数据包。

示例使用文档地址 192.0.2.0/24、198.51.100.0/24 和 203.0.113.0/24、局部管理 MAC 地址，以及域名 `example.test`。HTTP 正文是 `Hello NetLab!`。这些地址、名称和内容均由脚本指定。

PCAP 时间从 Unix 时间戳 `1700000000.000000` 开始。此值只是固定的示例起点，不代表实际抓包日期；帧间时间也由脚本指定，不能用来评估真实网络性能。以太网帧补齐到至少 60 字节，不包含网卡生成的 FCS。示例省略了完整路由与 DNS 服务器地址发现过程。

在抓包分析页面选择导入 PCAP，可以查看字段、原始字节、协议过滤与 TCP 时序。HTTPS 未出现在此文件中。

相邻的 `../experiments/tcp_loss.json` 和 `../experiments/cpu_network.json` 由应用的独立教学核心实际计算，均含 `source: teaching_simulation`、完整输入配置和原始计算结果。TCP 示例使用 10% 丢包率和固定随机种子 4。CPU 示例执行汇编指令，把 `Hi` 经虚拟 UDP、ARP、交换、路由和 NAT 发送到虚拟服务端，再将回显写入教学 CPU 的接收内存。JSON 事件时间以模拟秒表示，从 0 开始；CPU 周期、延迟和链路参数属于教学模型。

在项目根目录运行下面的命令，可重新生成这些文件。脚本只更新这份说明、指定 PCAP 和上述两份 JSON。

```powershell
.\\.venv\\Scripts\\python.exe scripts\\generate_examples.py
```
"""


def teaching_frames():
    """Build a small, internally consistent excerpt with explicit fixture times."""
    client_mac, gateway_mac = "02:00:00:00:00:10", "02:00:00:00:00:01"
    client_ip, gateway_ip = "192.0.2.10", "192.0.2.1"
    dns_ip, server_ip = "198.51.100.53", "203.0.113.80"
    outgoing = Ether(src=client_mac, dst=gateway_mac)
    incoming = Ether(src=gateway_mac, dst=client_mac)
    request = b"GET / HTTP/1.1\r\nHost: example.test\r\nConnection: close\r\n\r\n"
    body = b"Hello NetLab!\n"
    response = (b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
                + str(len(body)).encode("ascii") + b"\r\nConnection: close\r\n\r\n" + body)
    client_next, server_next = 1001 + len(request), 9001 + len(response)
    frames = [
        Ether(src=client_mac, dst="ff:ff:ff:ff:ff:ff") / ARP(
            op=1, hwsrc=client_mac, psrc=client_ip, hwdst="00:00:00:00:00:00", pdst=gateway_ip),
        incoming / ARP(op=2, hwsrc=gateway_mac, psrc=gateway_ip, hwdst=client_mac, pdst=client_ip),
        outgoing / IP(src=client_ip, dst=dns_ip, id=1) / UDP(sport=53000, dport=53) / DNS(
            id=1234, rd=1, qd=DNSQR(qname="example.test", qtype="A")),
        incoming / IP(src=dns_ip, dst=client_ip, id=2) / UDP(sport=53, dport=53000) / DNS(
            id=1234, qr=1, rd=1, ra=1, qd=DNSQR(qname="example.test", qtype="A"),
            an=DNSRR(rrname="example.test", type="A", ttl=60, rdata=server_ip)),
        outgoing / IP(src=client_ip, dst=server_ip, id=3) / TCP(
            sport=51000, dport=80, flags="S", seq=1000, window=8192, options=[("MSS", 1460)]),
        incoming / IP(src=server_ip, dst=client_ip, id=4) / TCP(
            sport=80, dport=51000, flags="SA", seq=9000, ack=1001, window=8192, options=[("MSS", 1460)]),
        outgoing / IP(src=client_ip, dst=server_ip, id=5) / TCP(
            sport=51000, dport=80, flags="A", seq=1001, ack=9001, window=8192),
        outgoing / IP(src=client_ip, dst=server_ip, id=6) / TCP(
            sport=51000, dport=80, flags="PA", seq=1001, ack=9001, window=8192) / Raw(request),
        incoming / IP(src=server_ip, dst=client_ip, id=7) / TCP(
            sport=80, dport=51000, flags="A", seq=9001, ack=client_next, window=8192),
        incoming / IP(src=server_ip, dst=client_ip, id=8) / TCP(
            sport=80, dport=51000, flags="PA", seq=9001, ack=client_next, window=8192) / Raw(response),
        outgoing / IP(src=client_ip, dst=server_ip, id=9) / TCP(
            sport=51000, dport=80, flags="A", seq=client_next, ack=server_next, window=8192),
        incoming / IP(src=server_ip, dst=client_ip, id=10) / TCP(
            sport=80, dport=51000, flags="FA", seq=server_next, ack=client_next, window=8192),
        outgoing / IP(src=client_ip, dst=server_ip, id=11) / TCP(
            sport=51000, dport=80, flags="A", seq=client_next, ack=server_next + 1, window=8192),
        outgoing / IP(src=client_ip, dst=server_ip, id=12) / TCP(
            sport=51000, dport=80, flags="FA", seq=client_next, ack=server_next + 1, window=8192),
        incoming / IP(src=server_ip, dst=client_ip, id=13) / TCP(
            sport=80, dport=51000, flags="A", seq=server_next + 1, ack=client_next + 1, window=8192),
    ]
    offsets = [0, 1000, 5000, 25000, 30000, 60000, 61000, 62000,
               92000, 100000, 130000, 140000, 170000, 171000, 201000]
    for frame, micros in zip(frames, offsets, strict=True):
        # Serialize once to materialize checksums; Ethernet padding is outside IP.
        encoded = bytes(frame)
        frame = Ether(encoded + b"\x00" * max(0, 60 - len(encoded)))
        frame.time = Decimal(1700000000) + Decimal(micros) / Decimal(1000000)
        yield frame


def write_result(path, experiment, config, result):
    record = {
        "source": "teaching_simulation",
        "experiment": experiment,
        "time_unit": "simulated_seconds",
        "time_note": "事件时间从 0 开始，表示教学模型的模拟秒；不是实测时间。",
        "config": config,
        "result": result,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    captures = ROOT / "examples" / "captures"
    experiments = ROOT / "examples" / "experiments"
    captures.mkdir(parents=True, exist_ok=True)
    experiments.mkdir(parents=True, exist_ok=True)
    frames = list(teaching_frames())
    wrpcap(str(captures / "teaching.pcap"), frames)
    (captures / "README.md").write_text(CAPTURE_README, encoding="utf-8")

    tcp_config = {
        "bytes_total": 8192, "loss": 0.1, "delay_ms": 30, "jitter_ms": 5,
        "bandwidth_mbps": 10, "receive_window": 4096, "seed": 4,
    }
    tcp = simulate_tcp(**tcp_config)
    write_result(experiments / "tcp_loss.json", "TCP_loss_recovery", tcp_config, tcp)

    cpu_config = {
        "assembly": DEFAULT_NETWORK_ASSEMBLY, "topology": example_topology("home"),
        "source": "PC1", "target": "WEB", "seed": 1,
        "max_steps": 1000, "receive_address": 128,
    }
    cpu = cpu_network_experiment(**cpu_config)
    write_result(experiments / "cpu_network.json", "CPU_virtual_network_echo", cpu_config, cpu)
    print(f"teaching.pcap: {len(frames)} constructed Ethernet frames")
    print("tcp_loss.json: " + json.dumps(tcp["metrics"], ensure_ascii=False))
    print("cpu_network.json: " + json.dumps(cpu["results"], ensure_ascii=False))


if __name__ == "__main__":
    main()

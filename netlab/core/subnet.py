"""IPv4/IPv6 calculations using Python's validated address arithmetic."""
from __future__ import annotations

import ipaddress
import math
from typing import Iterable


def analyze_network(cidr: str) -> dict:
    interface = ipaddress.ip_interface(cidr.strip())
    network = interface.network
    bits = network.max_prefixlen
    first = network.network_address
    last = network.broadcast_address
    if network.version == 4 and network.prefixlen < 31:
        first += 1
        last -= 1
        usable = network.num_addresses - 2
    else:
        usable = network.num_addresses
    ip_bits = f"{int(interface.ip):0{bits}b}"
    mask_bits = f"{int(network.netmask):0{bits}b}"
    network_bits = f"{int(network.network_address):0{bits}b}"
    group = 8 if network.version == 4 else 16
    grouped = lambda value: " ".join(value[i:i + group] for i in range(0, bits, group))
    special = []
    for attr, label in [("is_loopback", "回环"), ("is_link_local", "链路本地"),
                        ("is_multicast", "多播"), ("is_private", "非全局可达地址"),
                        ("is_reserved", "保留"), ("is_unspecified", "未指定")]:
        if getattr(interface.ip, attr):
            special.append(label)
    return {
        "input": cidr, "ip": str(interface.ip), "version": network.version,
        "network": str(network.network_address), "cidr": str(network),
        "broadcast": str(network.broadcast_address) if network.version == 4 else None,
        "first_host": str(first), "last_host": str(last),
        "num_addresses": network.num_addresses, "usable_hosts": usable,
        "prefix": network.prefixlen, "mask": str(network.netmask),
        "host_bits": bits - network.prefixlen, "special": special,
        "binary_steps": [
            {"label": "地址", "value": grouped(ip_bits)},
            {"label": "掩码", "value": grouped(mask_bits)},
            {"label": "逐位 AND 得网络地址", "value": grouped(network_bits)},
            {"label": "主机位范围", "value": f"{bits - network.prefixlen} 位；地址数 2^{bits - network.prefixlen} = {network.num_addresses}"},
        ],
        "note": "IPv6 没有广播地址；范围是地址空间范围，不代表地址均可分配。" if network.version == 6
                else "IPv4 /31 按点到点链路计算；/32 表示单个地址。",
    }


def mask_to_prefix(mask: str) -> int:
    return ipaddress.ip_network(f"0.0.0.0/{mask}").prefixlen


def vlsm_plan(base: str, hosts: Iterable[int]) -> list[dict]:
    network = ipaddress.ip_network(base.strip(), strict=False)
    if network.version != 4:
        raise ValueError("VLSM 主机数量规划目前针对 IPv4；IPv6 请按前缀划分。")
    requested = list(hosts)
    if not requested or any(not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= (1 << 32) - 2 for n in requested):
        raise ValueError("每个子网的主机数必须是正整数。")
    cursor = int(network.network_address)
    end = int(network.broadcast_address)
    allocations = []
    for original_index, count in sorted(enumerate(requested), key=lambda item: -item[1]):
        host_bits = max(2, math.ceil(math.log2(count + 2)))
        if host_bits > 32:
            raise ValueError("请求的主机数量超过 IPv4 空间。")
        size = 1 << host_bits
        start = ((cursor + size - 1) // size) * size
        if start + size - 1 > end:
            raise ValueError("基础网络空间不足以容纳全部子网。")
        subnet = ipaddress.ip_network((start, 32 - host_bits))
        row = analyze_network(str(subnet))
        row.update(requested_hosts=count, request_index=original_index)
        allocations.append(row)
        cursor = start + size
    return allocations


def conflicts(addresses: Iterable[str]) -> dict:
    items = [ipaddress.ip_interface(value.strip()) for value in addresses]
    duplicate = []
    overlapping = []
    for i, a in enumerate(items):
        for j, b in enumerate(items[i + 1:], i + 1):
            if a.ip == b.ip:
                duplicate.append({"indices": [i, j], "address": str(a.ip)})
            if a.version == b.version and a.network.overlaps(b.network):
                overlapping.append({"indices": [i, j], "networks": [str(a.network), str(b.network)]})
    return {"duplicate_addresses": duplicate, "overlapping_networks": overlapping,
            "note": "同一子网内地址重叠正常；重复主机地址才是地址冲突。"}


def convert_number(value: str, base: int = 10, bits: int = 8) -> dict:
    if base not in (2, 10, 16) or not 1 <= bits <= 128:
        raise ValueError("进制仅支持 2、10、16；位宽应为 1 至 128。")
    number = int(value.strip(), base)
    masked = number & ((1 << bits) - 1)
    return {"decimal": number, "binary": f"{masked:0{bits}b}",
            "hexadecimal": f"{masked:0{(bits + 3) // 4}X}",
            "unsigned": masked, "signed": masked - (1 << bits) if masked & (1 << (bits - 1)) else masked,
            "overflow": number < -(1 << (bits - 1)) or number >= (1 << bits)}


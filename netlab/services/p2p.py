"""A bounded STUN binding experiment against one explicitly configured server."""
from __future__ import annotations

import os
import socket
import struct

from .common import host, port, result, timeout

COOKIE = 0x2112A442


def stun_probe(target, target_port=3478, seconds=3):
    target, target_port, seconds = host(target), port(target_port), timeout(seconds)
    def perform():
        address = socket.getaddrinfo(target,target_port,type=socket.SOCK_DGRAM)[0]
        transaction = os.urandom(12)
        request = struct.pack("!HHI",0x0001,0,COOKIE)+transaction
        with socket.socket(address[0],socket.SOCK_DGRAM) as connection:
            connection.settimeout(seconds)
            connection.connect(address[4])
            connection.send(request)
            data = connection.recv(2048)
            local = connection.getsockname()
        if len(data)<20:
            raise ValueError("STUN 响应头被截断")
        type_, length, cookie = struct.unpack("!HHI",data[:8])
        if type_ != 0x0101 or cookie != COOKIE or data[8:20] != transaction or len(data) < 20+length:
            raise ValueError("无效的 STUN 成功响应/事务 ID")
        offset, mapped = 20, None
        while offset+4 <= 20+length:
            attribute, size = struct.unpack("!HH",data[offset:offset+4])
            value = data[offset+4:offset+4+size]
            if len(value)!=size:
                raise ValueError("STUN 属性被截断")
            if attribute in {0x0020,0x0001} and size>=8:
                family = value[1]
                mapped_port = struct.unpack("!H",value[2:4])[0]
                encoded = value[4:8] if family==1 else value[4:20]
                if attribute==0x0020:
                    mapped_port ^= COOKIE >> 16
                    mask = struct.pack("!I",COOKIE)+transaction
                    encoded = bytes(a^b for a,b in zip(encoded,mask))
                mapped = {"address": socket.inet_ntop(socket.AF_INET if family==1 else socket.AF_INET6,encoded), "port": mapped_port}
            offset += 4+((size+3)//4)*4
        if not mapped:
            raise ValueError("STUN 响应不包含映射地址")
        return {"local": list(local), "mapped": mapped, "note": "一个映射地址不能确定 NAT 类型，也不能保证 P2P 穿透成功；TURN 实际中继需另行配置认证服务器。"}
    return result("STUN",f"{target}:{target_port}",perform)

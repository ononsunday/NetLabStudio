"""Local cryptographic exercises and VPN teaching events; never configure VPNs."""
from __future__ import annotations

import hashlib
import ipaddress
import os


def crypto_demo(message="NetLab 加密消息", tamper=False):
    """Actual mature-library key agreement, AEAD, signing and verification."""
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import x25519,ed25519
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.exceptions import InvalidSignature,InvalidTag
    if len(message.encode("utf-8"))>65536:
        raise ValueError("加密教学消息限 64 KiB")
    plaintext = message.encode("utf-8")
    alice,bob = x25519.X25519PrivateKey.generate(),x25519.X25519PrivateKey.generate()
    alice_secret = alice.exchange(bob.public_key())
    bob_secret = bob.exchange(alice.public_key())
    def derive(secret):
        return HKDF(algorithm=hashes.SHA256(),length=32,salt=None,info=b"NetLab local cryptographic exercise").derive(secret)
    alice_key,bob_key = derive(alice_secret),derive(bob_secret)
    nonce = os.urandom(12)
    associated = b"NetLab-v1"
    ciphertext = AESGCM(alice_key).encrypt(nonce,plaintext,associated)
    signing_key = ed25519.Ed25519PrivateKey.generate()
    signature = signing_key.sign(plaintext)
    candidate = ciphertext[:-1]+bytes([ciphertext[-1]^1]) if tamper else ciphertext
    decoded,error = None,None
    try:
        decoded = AESGCM(bob_key).decrypt(nonce,candidate,associated).decode("utf-8")
    except InvalidTag:
        error = "认证标签校验失败：密文、关联数据或密钥被改变"
    signature_verified = True
    try:
        signing_key.public_key().verify(signature,plaintext+b"!" if tamper else plaintext)
    except InvalidSignature:
        signature_verified = False
    public = lambda key:key.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()
    return {"ok":True,"kind":"measured","operation":"本机密码学实验","plaintext":message,"sha256":hashlib.sha256(plaintext).hexdigest(),
            "key_agreement":{"algorithm":"X25519 + HKDF-SHA256","alice_public":public(alice.public_key()),"bob_public":public(bob.public_key()),"derived_keys_match":alice_key==bob_key},
            "encryption":{"algorithm":"AES-256-GCM","nonce":nonce.hex(),"ciphertext_and_tag":candidate.hex(),"associated_data":associated.decode(),"decrypted":decoded,"authenticated":error is None,"error":error},
            "signature":{"algorithm":"Ed25519","public_key":public(signing_key.public_key()),"signature":signature.hex(),"verified":signature_verified},
            "tampered":bool(tamper),"note":"使用 cryptography/OpenSSL 的真实本机密码运算。每次创建临时密钥；这些步骤并非 TLS 或 WireGuard 协议的完整实现。"}


def tls_handshake_model(resumed=False):
    """TLS 1.3 state model: compact teaching representation, not packet capture."""
    from netlab.core.events import EventEngine
    engine = EventEngine()
    choices = [("CLIENT_HELLO","客户端","服务器","发送支持的版本、算法和临时密钥共享。",{"key_share":True,"psk":bool(resumed)}),
               ("SERVER_HELLO","服务器","客户端","选择 TLS 1.3 算法，完成临时密钥协商。",{"encrypted":False}),
               ("ENCRYPTED_EXTENSIONS","服务器","客户端","从握手密钥导出后，加密传送协商扩展。",{"encrypted":True})]
    if not resumed:
        choices.extend([("CERTIFICATE","服务器","客户端","发送证书链，客户端检查信任链与主机名。",{"encrypted":True}),
                        ("CERTIFICATE_VERIFY","服务器","客户端","签名绑定握手上下文，证明持有对应私钥。",{"encrypted":True})])
    choices.extend([("FINISHED","服务器","客户端","验证握手完整性。",{"encrypted":True}),
                    ("FINISHED","客户端","服务器","确认客户端握手完整性。",{"encrypted":True}),
                    ("APPLICATION_DATA","客户端","服务器","使用应用流量密钥保护 HTTP 等应用数据。",{"encrypted":True})])
    for index,(kind,source,target,explanation,data) in enumerate(choices):
        engine.schedule(index*0.1,kind,source,target,explanation=explanation,data=data)
    while engine.queue:
        engine.record(engine.pop())
    return {"ok":True,"kind":"simulation","events":engine.history,"resumed":bool(resumed),"tls_version":"TLS 1.3",
            "note":"教学状态模型；真实证书验证请运行 TLS 探测。恢复握手省略证书不代表身份没有通过已验证的 PSK 会话继承。"}


def vpn_demo(destination="10.1.2.3",split_prefixes=None,full_tunnel=False,encrypted=True,message="private lab message",endpoint="203.0.113.10",source="10.0.0.2"):
    """Compute split-route decision, encapsulation and receive-side decapsulation."""
    from netlab.core.events import EventEngine
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    destination_ip,source_ip,endpoint_ip = ipaddress.ip_address(destination),ipaddress.ip_address(source),ipaddress.ip_address(endpoint)
    networks = [ipaddress.ip_network(prefix,strict=False) for prefix in (split_prefixes if split_prefixes is not None else ["10.0.0.0/8"])]
    if len(networks)>1000 or len(message.encode())>65536:
        raise ValueError("教学路由限 1000 条，消息限 64 KiB")
    matches = sorted((network for network in networks if destination_ip.version==network.version and destination_ip in network),key=lambda net:net.prefixlen,reverse=True)
    tunnel = bool(full_tunnel or matches)
    route = str(matches[0]) if matches else ("0.0.0.0/0" if destination_ip.version==4 else "::/0") if full_tunnel else "物理接口默认路由"
    engine = EventEngine()
    packet_id = "vpn-inner-1"
    payload = message.encode("utf-8")
    inner_header_bytes = (20 if destination_ip.version==4 else 40)+8
    outer_header_bytes = (20 if endpoint_ip.version==4 else 40)+8
    inner = {"source":str(source_ip),"destination":str(destination_ip),"protocol":"UDP","payload":message,"payload_bytes":len(payload),
             "header_bytes_model":inner_header_bytes,"bytes_model":len(payload)+inner_header_bytes}
    outer = None
    auth = None
    def emit(kind,source_,target,explanation,data=None):
        event = engine.schedule(0.05,kind,source_,target,packet_id,explanation,data or {})
        engine.record(engine.pop())
    emit("APP_SEND","应用","操作系统","应用生成虚拟数据报。",inner)
    emit("ROUTE_LOOKUP","操作系统","路由表",f"最长前缀匹配选择 {route}。",{"selected_route":route,"via_tunnel":tunnel,"full_tunnel":bool(full_tunnel)})
    if tunnel:
        if encrypted:
            key,nonce = ChaCha20Poly1305.generate_key(),os.urandom(12)
            aad = (str(source_ip)+"|"+str(destination_ip)).encode()
            cipher = ChaCha20Poly1305(key).encrypt(nonce,payload,aad)
            body = cipher.hex()
            auth = ChaCha20Poly1305(key).decrypt(nonce,cipher,aad)==payload
            emit("TUNNEL_ENCRYPT","虚拟接口","隧道端点","教学封装使用成熟库的 ChaCha20-Poly1305 认证加密。",{"ciphertext_hex":body,"nonce":nonce.hex(),"overhead_bytes":16})
        else:
            body = message
            emit("TUNNEL_PLAINTEXT","虚拟接口","隧道端点","隧道封装本身不会自动提供机密性。",{"visible_payload":message})
        outer = {"source":"198.51.100.20","destination":str(endpoint_ip),"protocol":"UDP","source_port":51820,"destination_port":51820,
                 "encrypted":bool(encrypted),"payload":body,"inner_destination_visible":not bool(encrypted),
                 "bytes_model":inner["bytes_model"]+(16 if encrypted else 0)+outer_header_bytes,"outer_header_bytes_model":outer_header_bytes}
        emit("ENCAPSULATE","隧道客户端","虚拟互联网","外层地址用于到达隧道服务器；内层地址描述原始目的地。",outer)
        emit("TUNNEL_RECEIVE","虚拟互联网","隧道服务器","虚拟链路交付封装包。",{"outer_destination":str(endpoint_ip)})
        emit("DECAPSULATE","隧道服务器","内层路由器","验证认证标签后恢复原始教学数据报。" if encrypted else "去掉外层头部，恢复未加密的数据报。",{"authenticated":auth,"inner":inner})
    else:
        emit("DIRECT_SEND","物理接口","目标网络","地址未匹配分流网段，虚拟包走直连路径。",inner)
    emit("APP_RECEIVE","协议栈","接收应用","接收应用获得原始虚拟消息。",{"message":message})
    return {"ok":True,"kind":"simulation","events":engine.history,"route":route,"via_tunnel":tunnel,"inner":inner,"outer":outer,
            "encryption_authenticated":auth,"note":"通用 VPN 封装与分流教学模型，使用文档示例地址；不会配置系统 VPN 或发送真实包。WireGuard 实际还包含 Noise 握手、重放保护与密钥轮换，本模型不实现其协议。"}

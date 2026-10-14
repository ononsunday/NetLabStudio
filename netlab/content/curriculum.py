"""Original concise lessons with targeted questions and primary-source references.

Prose reviewed using the installed humanizer skill. References are reading links,
not a claim that every teaching model implements the complete referenced standard.
"""
from __future__ import annotations

TOPICS = []

LEARNING_MODES = {
    "free": {"title": "自由实验", "description": "自行选择拓扑和参数，保存配置并对比结果。"},
    "guided": {"title": "教学引导", "description": "按综合实验步骤运行，记录观察证据并回答练习。"},
    "challenge": {"title": "挑战模式", "description": "先提出故障假设，用探测与协议事件验证，再提交答案。"},
}

GUIDES = {
    "A": {"title": "访问一个网站", "goal": "按层解释域名解析、连接建立、TLS 和 HTTP 响应。",
          "steps": ["使用教学域名或明确指定的测试网址。", "查询 DNS A/AAAA，区分缓存和新查询。", "在 TCP/QUIC 时序中观察建立过程。", "检查 TLS 证书和 HTTP 状态。", "保存记录，说明每项属于实测还是模拟。"],
          "topics": ["dns", "tcp_handshake", "tls13", "http3"], "experiment": "web"},
    "B": {"title": "建立家庭局域网", "goal": "通过共享设备配置完成 DHCP、ARP、交换和路由。",
          "steps": ["创建路由器、交换机和两台电脑，并连接端口。", "配置路由器网段、DHCP 池和租约。", "客户端申请地址，核对网关与掩码。", "发送 Ping，查看 ARP 表和交换机 MAC 表。", "改变 VLAN 或关闭链路，比较数据包路径。"],
          "topics": ["dhcp", "arp", "mac_learning", "default_route"], "experiment": "topology"},
    "C": {"title": "游戏联机", "goal": "比较直接通信、NAT 映射和中继，观察延迟与丢包。",
          "steps": ["使用两个虚拟家庭网络及服务器。", "检查 NAT 映射的内部与外部连接元组。", "观察 STUN 所解释的外部地址；检查映射是否允许对端回包。", "比较直接路径与 TURN 中继的教学路径。", "改变丢包和抖动，观察玩家状态同步。"],
          "topics": ["p2p", "stun", "turn", "prediction"], "experiment": "gaming"},
    "D": {"title": "网络故障排查", "goal": "用配置、邻居表、路由和协议事件定位已有明确原因的故障。",
          "steps": ["加载故障挑战，先记录现象。", "检查接口状态、IP 和子网。", "测试本地邻居及默认网关。", "检查路由与 DNS，再检查目标端口。", "修复虚拟配置并重新运行，用证据验证。"],
          "topics": ["diagnostic_order", "arp_cache", "static_route", "dns_failure"], "experiment": "challenge"},
    "E": {"title": "CPU 发送网络消息", "goal": "将汇编、内存、系统调用和虚拟消息连接起来。",
          "steps": ["用 MOV/STORE 将消息字节写入教学内存。", "执行 SEND 起始地址,长度。", "单步观察 CPU 取指与 os.syscall 事件。", "查看 Socket 缓冲区、DMA 和 network.send 事件。", "把消息交给虚拟网络并观察接收方向。"],
          "topics": ["cpu", "syscall", "dma", "socket_buffer"], "experiment": "cpu"},
    "F": {"title": "网络性能与操作系统", "goal": "比较教学包大小、缓冲区和通知策略对 CPU 开销及吞吐量的影响。",
          "steps": ["固定总载荷与链路带宽。", "分别测试小块和大块数据。", "降低 Socket 缓冲区，观察发送阻塞或接收丢弃。", "比较逐包中断与批量轮询的模型周期。", "保存参数和结果，说明模型没有代表本机性能。"],
          "topics": ["bandwidth", "dma", "interrupt", "async_io"], "experiment": "performance"},
}


def search_topics(query: str = "", category: str | None = None) -> list[dict]:
    terms = str(query).strip().casefold().split()
    return [topic for topic in TOPICS if (category is None or topic["category"] == category) and
            all(term in " ".join(str(topic.get(key, "")) for key in
                                  ("id", "title", "category", "concept", "mechanism", "example", "fields")).casefold()
                for term in terms)]


def get_topic(topic_id: str) -> dict | None:
    return next((topic for topic in TOPICS if topic["id"] == topic_id), None)


def _group(category, sources, rows):
    for row in rows:
        topic_id, title, concept, mechanism, example, fields, experiment, question, correct, wrong1, wrong2 = row
        choices = [correct, wrong1, wrong2]
        rotation = sum(ord(letter) for letter in topic_id) % 3
        choices = choices[rotation:] + choices[:rotation]
        TOPICS.append({"id": topic_id, "title": title, "category": category,
                       "concept": concept, "mechanism": mechanism, "example": example,
                       "fields": fields.split("；"), "experiment": experiment,
                       "question": question, "options": choices, "answer": choices.index(correct),
                       "explanation": mechanism, "related": [], "sources": sources,
                       "data_source": "educational", "difficulty": "基础"})


_group("网络基础", ["https://www.rfc-editor.org/info/rfc1122", "https://www.rfc-editor.org/info/rfc8200"], [
    ("osi", "OSI 七层模型", "OSI 将网络功能分为物理、数据链路、网络、传输、会话、表示和应用七层。", "分层让相邻层通过接口协作。现实协议不一定与七层一一对应。", "网卡传输比特，IP 负责寻址，浏览器处理 HTTP。", "层次；服务接口", "topology", "IP 通常属于 OSI 的哪一层？", "网络层", "传输层", "表示层"),
    ("tcpip", "TCP/IP 体系结构", "TCP/IP 常按链路、互联网、传输和应用四层描述。", "IP 跨网络转发；TCP 或 UDP 为应用提供传输服务。教学也可将物理层单独列出。", "HTTP 数据经 TCP、IP 和以太网发送。", "IP Protocol；EtherType", "topology", "TCP 为哪一层提供服务？", "应用层", "物理层", "只为 DNS 提供服务"),
    ("encapsulation", "封装与解封装", "封装是逐层附加协议头部，解封装是接收侧逐层解释字段。", "应用数据变成传输层报文，再进入 IP 包和链路帧；路由器更换链路帧而保留端到端载荷。", "同一 IP 包经过两段以太网时，源和目标 MAC 可以变化。", "Ethernet；IP；TCP；payload", "packet", "路由器转发时通常会重新构造哪一部分？", "链路层帧", "完整应用正文", "服务器证书"),
    ("units", "比特、字节与协议数据单元", "比特表示 0 或 1，一个字节通常为 8 比特。帧、数据报和报文段属于不同层。", "速率单位 bit/s 和数据量 byte 需要乘除 8；协议头部也占用链路容量。", "100 Mbit/s 的理论字节速率是 12.5 MB/s，应用速率还受开销影响。", "bit；byte；frame；datagram；segment", "performance", "80 Mbit/s 在不计开销时是多少 MB/s？", "10 MB/s", "80 MB/s", "640 MB/s"),
    ("addressing", "IP、MAC 与端口", "IP 标识网络层位置，MAC 用于链路通信，端口帮助传输层区分应用。", "跨网段通信先选 IP 路由，再找下一跳 MAC；接收系统按协议和端口分用。", "浏览器连接服务器 TCP 443，本地以太网帧先交给网关 MAC。", "src IP；dst IP；src MAC；dst MAC；port", "topology", "跨网段帧的目标 MAC 通常是谁？", "本地下一跳网关", "远端网站的永久 MAC", "DNS 的 MAC"),
    ("ipv4", "IPv4 地址", "IPv4 地址为 32 位，常写成四个十进制字节。", "前缀决定网络部分；接口地址和路由配合决定可达范围。", "192.168.1.10/24 与 192.168.1.20/24 属于同一 IPv4 前缀。", "address；prefix length", "subnet", "IPv4 地址总长是多少位？", "32 位", "48 位", "128 位"),
    ("ipv6", "IPv6 地址", "IPv6 地址为 128 位，以十六进制分组表示。", "前导零可省略；连续零组可用一次 :: 压缩。IPv6 不使用广播。", "2001:db8::1 是文档示例地址，不表示本机公网地址。", "128-bit address；prefix", "subnet", "一个 IPv6 地址中 :: 最多可出现几次？", "一次", "两次", "任意次数"),
    ("cidr", "子网掩码与 CIDR", "CIDR 用前缀长度表示地址的网络位数。", "IPv4 网络地址由地址与连续掩码按位与计算；主机位用于区分前缀内地址。", "192.168.1.130/25 的网络地址为 192.168.1.128。", "netmask；prefix；network", "subnet", "IPv4 /24 的掩码是什么？", "255.255.255.0", "255.255.0.0", "255.255.255.255"),
    ("vlsm", "VLSM 子网规划", "VLSM 让同一地址块按不同主机需求分配不同长度的前缀。", "从较大的需求开始，按二进制边界分配，检查地址块是否重叠或越界。", "60 台和 20 台主机分别可使用 /26 和 /27 的普通 IPv4 子网。", "host demand；aligned network；prefix", "subnet", "普通 IPv4 /27 子网可用主机地址通常有多少？", "30 个", "32 个", "27 个"),
    ("reserved", "特殊与保留地址", "私有、回环、链路本地、组播和文档地址有不同用途。", "地址分类决定使用范围。私有 IPv4 地址不应作为普通公网目的地址直接路由。", "127.0.0.1 用于本机回环，192.0.2.0/24 用于文档。", "is_private；is_loopback；is_multicast", "subnet", "127.0.0.1 通常到达哪里？", "本机", "默认网关", "全球任意主机"),
    ("delivery", "单播、广播与多播", "单播发送给一个目的端，多播发送给订阅组，广播面向广播域内所有端。", "交换机按目的 MAC 决定转发范围；路由器通常隔离二层广播。", "ARP 请求通过本地广播寻找 IPv4 地址对应的 MAC。", "destination MAC；multicast group", "lan", "IPv6 是否使用广播地址？", "不使用，相关功能常由多播完成", "使用 255.255.255.255", "只在 HTTPS 使用广播"),
    ("bandwidth", "带宽与吞吐量", "带宽描述可用传输容量，吞吐量描述实际传输的数据速率。", "协议开销、拥塞、磁盘速度、CPU 和服务端限制都可降低应用吞吐量。", "千兆网卡不保证一次下载能达到千兆。", "capacity；goodput；overhead", "performance", "网卡标称速率能否保证应用下载速率？", "不能，还受路径和应用限制", "一定保证", "只由 DNS 决定"),
    ("latency", "延迟、RTT 与抖动", "单向延迟是数据到达所需时间，RTT 是往返时间，抖动是延迟的变化。", "发送、传播、排队和处理共同组成延迟；没有时钟同步不能直接把 RTT 当准确单向延迟。", "语音通话中延迟忽高忽低会造成播放不连续。", "RTT；queue delay；jitter", "gaming", "RTT/2 是否总等于单向延迟？", "不是，往返路径可能不对称", "总是相等", "只要用 UDP 就相等"),
    ("loss", "丢包与乱序", "丢包是数据未到达，乱序是到达次序和发送次序不同。", "链路错误、拥塞丢弃和路径差异均可影响到达；协议可选择重传或容忍缺失。", "旧语音帧迟到后可能没有播放价值。", "loss ratio；sequence；arrival time", "transport", "有 100 次探测，10 次超时，观测丢失比例是多少？", "10%", "90%", "100%"),
    ("mtu", "MTU 与分片", "MTU 是某链路可承载的网络层包大小上限。", "IPv4 可按条件分片；IPv6 路由器不分片，由发送方处理。传输层分段与 IP 分片不同。", "隧道增加头部后，原有大包可能超过外层路径 MTU。", "MTU；DF；Fragment Header", "routing", "IPv6 路由器会直接把过大的包分片吗？", "不会，会返回 Packet Too Big", "总会", "只要是 TCP 就会"),
    ("pmtud", "路径 MTU 发现", "路径 MTU 是端到端路径上最小的链路 MTU。", "发送方结合报文过大反馈或探测调整大小；必要 ICMP 被丢弃时可能出现黑洞。", "能 Ping 小包却打不开大页面可能与 MTU 有关，但需要进一步验证。", "ICMP Packet Too Big；DF", "routing", "只允许小包通过时能否直接断定 DNS 故障？", "不能，还需检查 MTU 等证据", "一定是 DNS", "一定是网卡损坏"),
    ("ethernet", "以太网基础", "以太网用 MAC 地址传送帧，现代交换式网络常采用全双工链路。", "交换机学习源地址并查找目的地址。帧通常包含地址、类型、载荷和校验字段。", "网线把电脑接到交换机，以太网帧承载 IP 包。", "Destination；Source；EtherType；FCS", "lan", "交换机通常依据什么地址转发二层帧？", "目的 MAC 地址", "HTTP URL", "进程编号"),
    ("wifi4", "Wi-Fi 4 与 Wi-Fi 5", "Wi-Fi 4 对应 802.11n，Wi-Fi 5 对应 802.11ac。", "Wi-Fi 4 可工作于 2.4 或 5 GHz；Wi-Fi 5 工作于 5 GHz。实际连接取决于双方能力和环境。", "旧设备连到新路由器也可能协商为旧标准。", "radio type；band；channel width；MIMO", "observe", "Wi-Fi 5 的主要工作频段是什么？", "5 GHz", "只有 2.4 GHz", "只有 6 GHz"),
    ("wifi6", "Wi-Fi 6 与 Wi-Fi 6E", "Wi-Fi 6 对应 802.11ax；Wi-Fi 6E 将其能力扩展到 6 GHz 频段。", "OFDMA 分配资源单元，MU-MIMO 支持多用户传输；6 GHz 的可用范围取决于当地法规。", "支持 6E 的客户端和接入点才能协商相应的 6 GHz 连接。", "OFDMA；RU；TWT；6 GHz", "observe", "Wi-Fi 6E 中的 E 主要表示什么？", "扩展到 6 GHz 频段", "每次连接都加倍速率", "不需要接入点"),
    ("wifi7", "Wi-Fi 7", "Wi-Fi 7 对应 802.11be，包含多链路操作等能力。", "MLO、较宽信道和更高阶调制可在相应设备、频谱和信号条件下提高效率；具体功能依产品实现。", "路由器宣传 Wi-Fi 7 并不证明当前电脑已协商 MLO。", "802.11be；MLO；320 MHz；4096-QAM", "observe", "能否仅凭路由器标签判断当前电脑用了 Wi-Fi 7？", "不能，要查看实际连接和客户端支持", "可以", "只看 IPv6 就能判断"),
])

_group("局域网与链路层", ["https://www.rfc-editor.org/info/rfc826", "https://www.rfc-editor.org/info/rfc2131", "https://www.rfc-editor.org/info/rfc4861"], [
    ("frame", "以太网帧字段", "以太网帧头部包含目的 MAC、源 MAC 和类型等信息。", "接收端用 EtherType 判断上层协议；FCS 用于检测传输错误，抓包文件不一定包含 FCS。", "EtherType 0x0800 表示 IPv4，0x86DD 表示 IPv6。", "dst；src；type；payload；FCS", "packet", "0x86DD 表示哪种网络层协议？", "IPv6", "ARP", "TCP"),
    ("mac_learning", "交换机 MAC 学习", "交换机从收到帧的源 MAC 学习地址与端口的对应关系。", "转发表按 VLAN 和 MAC 查询；目的未知时向同 VLAN 其他可转发端口泛洪。", "第一次通信可能泛洪，学到地址后后续帧可单播。", "source MAC；ingress port；VLAN；FDB", "lan", "交换机从哪一字段学习转发表？", "源 MAC", "目的 TCP 端口", "HTTP 状态码"),
    ("switch_forward", "交换转发与泛洪", "已知单播转向查到的端口；未知单播和广播需限定范围泛洪。", "交换机不向入端口反射同一帧，STP 阻塞端口和不同 VLAN 会限制范围。", "目标位于同一入端口下时，无需再向其他端口转发。", "FDB lookup；flood；drop", "lan", "未知单播会转发到哪些端口？", "同 VLAN 的其他可转发端口", "所有 VLAN 的所有端口", "仅 DNS 端口"),
    ("arp", "ARP 请求与响应", "ARP 在 IPv4 局域链路上解析协议地址对应的 MAC 地址。", "请求通常广播，拥有目标 IPv4 地址的设备响应，发送方记录映射。", "电脑发跨网段包前，通常先解析默认网关的 MAC。", "opcode；sender IP；sender MAC；target IP", "lan", "ARP 解决哪一类映射？", "本地 IPv4 地址到链路地址", "域名到公网地址", "端口到密码"),
    ("arp_cache", "ARP 缓存与失效", "ARP 缓存减少重复地址解析，但缓存条目会过期。", "表项可经历有效、老化和重新解析等状态；真实系统的超时策略不完全一致。", "网卡更换后，过期的旧映射可能暂时影响访问。", "neighbor state；expiry；MAC", "lan", "ARP 缓存过期后通常需要做什么？", "重新解析邻居地址", "永久停止通信", "清除网站证书"),
    ("ndp", "IPv6 邻居发现", "IPv6 用 ICMPv6 邻居发现完成邻居解析及可达性检查等功能。", "NS 和 NA 替代 ARP 的解析用途，还包含路由器发现及相关状态机制。", "IPv6 设备向目标的请求节点多播地址发送 NS。", "NS；NA；ICMPv6；neighbor state", "lan", "IPv6 地址解析主要使用什么？", "ICMPv6 邻居发现", "ARP 广播", "HTTP Cookie"),
    ("dhcp", "DHCP 地址分配", "DHCPv4 为客户端分配地址和网络参数，并通过租约管理使用期限。", "典型初始交换为 Discover、Offer、Request、ACK；失败和重试也需要处理。", "家庭电脑自动获得地址、掩码、网关和 DNS。", "transaction ID；yiaddr；lease；options", "lan", "典型 DHCPv4 分配的最后一步是什么？", "ACK", "Discover", "ARP Request"),
    ("lease", "DHCP 租约续期", "租约使地址使用具有时间限制。", "客户端在 T1 尝试向原服务器续期，T2 后进入重绑定；租约失效后不能继续当作有效地址使用。", "暂时断开的电脑回网后可能重新申请地址。", "lease time；T1；T2；renewal", "lan", "租约已失效时能否继续无条件使用旧地址？", "不能，需重新获得有效配置", "能永久使用", "只要 MAC 没变就能"),
    ("vlan", "VLAN 与广播域", "VLAN 将同一物理交换网络划分为多个逻辑二层广播域。", "交换机按端口或标签归属判断 VLAN；二层广播不会直接跨 VLAN 转发。", "办公与访客网络可以使用不同 VLAN。", "VLAN ID；broadcast domain", "lan", "不同 VLAN 的主机通常需通过什么通信？", "三层路由", "直接 ARP 广播", "交换机学习源端口即可"),
    ("dot1q", "802.1Q 标签", "802.1Q 在以太网帧中携带 VLAN 标识和优先级信息。", "标签包含 PCP、DEI 和 VLAN ID；链路两端必须对 VLAN 配置达成一致。", "两台交换机之间可在同一链路上携带多个 VLAN。", "TPID；PCP；DEI；VID", "lan", "802.1Q 的 VID 用来表示什么？", "VLAN 标识", "IPv6 地址", "TCP 序列号"),
    ("access", "Access 端口", "Access 端口通常为终端提供一个 VLAN 的无标签接入。", "交换机给无标签入帧归入配置 VLAN，向终端发帧时按接入规则去除标签。", "普通办公电脑接入 VLAN 10 的 Access 端口。", "PVID；untagged ingress", "lan", "普通 Access 端口通常服务多少个终端 VLAN？", "一个", "所有 VLAN", "零个"),
    ("trunk", "Trunk 端口", "Trunk 端口承载多个 VLAN，需要配置允许列表及无标签处理规则。", "有标签帧按 VID 分类；不允许的 VLAN 不能通过该端口。", "VLAN 20 未加入 Trunk 允许列表时，其主机可能跨交换机不可达。", "allowed VLANs；native VLAN；tag", "lan", "只允许 VLAN 10 的 Trunk 能否传 VLAN 20？", "不能", "一定能", "仅 UDP 能"),
    ("inter_vlan", "VLAN 间路由", "VLAN 间通信通过三层接口或路由子接口完成。", "路由器分别在各 VLAN 接口上收发帧，检查路由并递减 TTL。", "单臂路由让多个带标签子接口共享一条 Trunk。", "SVI；subinterface；gateway", "routing", "VLAN 间路由是否需要 IP 路由决策？", "需要", "只需 FCS 校验", "只需 DNS 缓存"),
    ("stp", "STP 生成树", "STP 在有冗余二层链路时选择无环转发树。", "通过桥标识和路径代价选择根桥及端口角色，阻塞形成环路的部分路径。", "三台交换机构成三角形时，可以保留备用链路而避免广播无限循环。", "bridge ID；root；cost；port state", "lan", "STP 主要防止哪种问题？", "二层转发环路", "TLS 证书过期", "TCP 慢启动"),
    ("domains", "广播域与冲突域", "广播域决定二层广播范围；冲突域描述共享介质可能发生发送冲突的范围。", "交换机分隔传统冲突域；VLAN 分隔广播域。全双工交换链路不采用共享以太网碰撞机制。", "一个交换机 VLAN 中的广播可到达多个终端。", "half duplex；full duplex；VLAN", "lan", "VLAN 主要划分什么？", "广播域", "DNS 根区", "CPU 页框"),
    ("wifi_assoc", "Wi-Fi 接入与认证", "无线客户端需发现接入点、关联并完成对应安全认证。", "不同安全方式的消息不同；获取 IP 地址通常在二层接入成功之后进行。", "显示已关联 Wi-Fi 不代表已经获得可用网关或 DNS。", "SSID；BSSID；authentication；association", "observe", "已连上 Wi-Fi 是否证明互联网一定可达？", "不能", "能", "证明 DNSSEC 已启用"),
    ("wifi_roam", "Wi-Fi 漫游", "漫游是客户端在接入点之间切换连接。", "客户端结合信号和策略选择目标；802.11k/v/r 等能力可帮助发现和切换，须设备共同支持。", "走过校园时设备从一个 AP 转到另一个 AP。", "BSSID；RSSI；802.11r", "gaming", "漫游切换时应用是否一定完全无感？", "不一定，受切换时长和网络配置影响", "一定无感", "一定更换用户密码"),
])

_group("路由与互联网", ["https://www.rfc-editor.org/info/rfc791", "https://www.rfc-editor.org/info/rfc8200", "https://www.rfc-editor.org/info/rfc2328"], [
    ("ipv4_header", "IPv4 数据报结构", "IPv4 头部包含版本、长度、TTL、协议、地址和校验等字段。", "IHL 决定头部长度，Total Length 包含头部和数据；分片字段描述原始报文的位置。", "IP Protocol 6 表示 TCP，17 表示 UDP。", "Version；IHL；TTL；Protocol；Checksum", "packet", "IPv4 的 Protocol=17 表示什么？", "UDP", "TCP", "DNS 记录类型"),
    ("ipv6_header", "IPv6 数据包结构", "IPv6 基本头部固定为 40 字节，通过扩展头承载额外信息。", "Next Header 指向下一协议或扩展头；基本头部没有 IPv4 那样的头部校验和。", "IPv6 分片由发送方加入 Fragment 扩展头。", "Traffic Class；Flow Label；Next Header；Hop Limit", "packet", "IPv6 基本头部长度是多少？", "40 字节", "20 字节", "可任意变化"),
    ("ttl", "TTL 与 Hop Limit", "TTL 和 Hop Limit 限制数据包经历的转发次数。", "路由器转发时减一，耗尽后丢弃并可返回相应 ICMP 错误，防止环路无限持续。", "Traceroute 逐步增大 TTL 来观察中途回复。", "TTL；Hop Limit；Time Exceeded", "routing", "TTL=1 的包经过一个路由器后通常怎样？", "耗尽并被丢弃", "变成 255", "仅 TCP 能继续"),
    ("icmp", "ICMP 与 ICMPv6", "ICMP 传递网络错误和控制信息，Ping 使用 Echo 消息。", "目标不可达、超时和报文过大等消息帮助发送方诊断；没有回复不等于主机不存在。", "某服务器禁止 Echo 但仍能接受 HTTPS。", "type；code；Echo；Time Exceeded", "diagnostics", "Ping 无回复能否证明 HTTPS 不可达？", "不能，需要测试相应服务", "能", "证明 DNS 地址错误"),
    ("forwarding", "IP 转发", "路由器按目标 IP 查表并选择出口与下一跳。", "选择路由后解析下一跳链路地址，重建帧并调整 TTL 或 Hop Limit。", "192.168.1.10 的跨网段包先交给默认网关。", "destination；next hop；interface", "routing", "IP 转发主要依据哪一字段？", "目标 IP", "源 HTTP Header", "应用进程名"),
    ("lpm", "最长前缀匹配", "多条路由匹配时，先选择网络前缀最长的路由。", "更长前缀覆盖更小范围，比默认路由更具体；同长度还需比较协议或度量。", "10.1.0.0/16 优先于 10.0.0.0/8。", "prefix length；metric", "routing", "匹配 /8 和 /24 时先选哪个？", "/24", "/8", "随机选"),
    ("default_route", "默认路由", "默认路由覆盖没有更具体匹配的目的地址。", "IPv4 默认路由为 0.0.0.0/0，IPv6 为 ::/0；下一跳仍必须实际可达。", "家庭主机将外部目的地址交给路由器。", "0.0.0.0/0；::/0；gateway", "routing", "IPv6 的默认路由是什么？", "::/0", "::1/128", "ff00::/8"),
    ("static_route", "静态路由", "静态路由由管理员显式配置目标前缀、下一跳和出口。", "配置不会自动反映所有远端链路变化；错误下一跳可以造成黑洞或环路。", "实验中手动添加两个路由器之间的网段路由。", "network；gateway；metric", "routing", "下一跳配置错误最可能导致什么？", "转发失败或错误路径", "自动生成正确 DNS", "TLS 证书自动更新"),
    ("aggregation", "路由聚合", "聚合用一个较短前缀表示多个连续、对齐的地址块。", "需要共同前缀且不引入不当覆盖；更具体路由仍可优先匹配。", "192.168.0.0/24 与 192.168.1.0/24 可聚合为 192.168.0.0/23。", "supernet；common prefix", "subnet", "上述两个 /24 的正确聚合是什么？", "192.168.0.0/23", "192.168.0.0/25", "192.168.1.0/24"),
    ("rip", "RIP 与 Bellman-Ford", "RIP 是使用跳数度量的距离向量路由协议。", "节点从邻居距离更新本地表；RIP 的 16 表示不可达，教学模型可观察逐轮收敛。", "断开链路后，邻居消息会逐步改变路由。", "distance vector；hop count；next hop", "routing", "RIP 中跳数 16 通常表示什么？", "不可达", "最快路由", "16 Gbit/s"),
    ("ospf", "OSPF 与 Dijkstra", "OSPF 使用链路状态信息计算最短路径。", "路由器传播拓扑描述，对图运行最短路径算法；区域和实际邻接状态比基础模型更复杂。", "链路成本变大后，最短路径可切换到备用链路。", "LSA；link cost；SPF；area", "routing", "OSPF 常使用什么算法计算最短路径？", "Dijkstra", "随机轮询", "FIFO 页替换"),
    ("bgp", "BGP 与自治系统", "BGP 在自治系统之间传播路由，选择还受策略和路径属性影响。", "AS_PATH 记录经过的自治系统，帮助防止 AS 路径环路；真实决策不只比较路径长度。", "运营商可按商业策略选择出口，即使另一路 AS_PATH 更短。", "ASN；AS_PATH；LOCAL_PREF；NEXT_HOP", "routing", "能否把 BGP 简化成全球最低延迟算法？", "不能，它受路由策略影响", "能", "它只用于局域网 ARP"),
    ("convergence", "收敛与链路故障", "收敛是各设备逐步对可达性和路径达成稳定状态。", "故障检测、信息传播和路由计算需要时间；期间可能有丢包和临时环路。", "拔掉主链路后，备用路径不一定立刻接管。", "failure detection；update round；path", "routing", "链路故障后路由是否总瞬间稳定？", "不是，需要检测和传播", "总是", "只会改变 MAC 不改变路由"),
    ("nat", "NAT 地址转换", "NAT 在网络边界修改地址，并维护返回流量的映射关系。", "转换必须配合协议校验和更新；地址转换本身不等于完整安全策略。", "家庭设备共用路由器的公网地址访问网站。", "inside local；inside global；mapping", "topology", "NAT 本身是否等同完整防火墙？", "不等同", "完全等同", "一定提供端到端加密"),
    ("pat", "PAT 与端口映射", "PAT 使用端口区分共享外部地址的多个连接。", "映射可由出站流量动态创建，或为服务显式配置静态外部端口；冲突需处理。", "两台电脑使用不同外部源端口连接同一服务器。", "protocol；internal tuple；external port", "topology", "PAT 如何区分共享外部 IP 的连接？", "借助端口等连接元组", "只用 HTTP 标题", "只用 CPU 编号"),
    ("cgnat", "CGNAT", "CGNAT 是运营商侧的大规模地址共享。", "家庭路由器之外还有转换层，用户通常不能在运营商层自行设置入站端口映射。", "路由器 WAN 地址可能属于共享地址空间 100.64.0.0/10。", "100.64.0.0/10；mapping；WAN", "gaming", "仅在家庭路由器映射端口能否保证穿过 CGNAT？", "不能", "一定能", "开启 DHCP 就能"),
    ("slaac", "IPv6 自动配置", "SLAAC 使用路由器通告的前缀等信息生成地址。", "主机检查地址重复并跟踪有效期；DHCPv6 和 RA 的角色要分别理解，默认路由常来自 RA。", "设备可同时持有链路本地和多个全球单播地址。", "RA；prefix；DAD；valid lifetime", "lan", "IPv6 默认路由通常从什么消息获得？", "路由器通告 RA", "ARP Reply", "HTTP 302"),
])

_group("TCP、UDP 与 QUIC", ["https://www.rfc-editor.org/info/rfc9293", "https://www.rfc-editor.org/info/rfc5681", "https://www.rfc-editor.org/info/rfc9000"], [
    ("tcp_handshake", "TCP 三次握手", "TCP 建立连接时交换初始序列号并确认双向接收能力。", "典型消息为 SYN、SYN-ACK 和 ACK，SYN 占用一个序列号；丢失消息可能触发重传。", "浏览器建立新的 TCP 连接后再传应用数据。", "SYN；ACK；SEQ；ISN", "transport", "初始 SYN 的序列号为 100，确认号通常应是多少？", "101", "100", "0"),
    ("tcp_close", "TCP 关闭连接", "TCP 的两个发送方向可独立关闭。", "FIN 与 ACK 使双方确认数据流结束；ACK 与 FIN 可以合并，因此不总是恰好四个报文。", "客户端关闭发送方向后仍可接收服务器最后的数据。", "FIN；ACK；TIME_WAIT", "transport", "TCP 正常关闭是否永远恰好四个报文？", "不是，有些报文可以合并", "永远四个", "永远两个"),
    ("tcp_state", "TCP 状态转换", "TCP 端点通过状态机处理连接建立、数据传输和关闭。", "客户端主动打开常经历 CLOSED、SYN_SENT、ESTABLISHED；关闭路径依主动或被动关闭而异。", "监听服务器处于 LISTEN，单个已接入连接处于 ESTABLISHED。", "LISTEN；SYN_SENT；ESTABLISHED；CLOSE_WAIT", "transport", "监听 Socket 与已建立连接的状态相同吗？", "不同", "始终相同", "两者都一定 TIME_WAIT"),
    ("seq_ack", "序列号与确认号", "TCP 序列号按字节计算，累计确认号指向下一个期望字节。", "重复确认可提示缺失区间；SYN 和 FIN 各占用一个序列号。", "SEQ=1000 的 200 字节数据被完整接收后可 ACK=1200。", "SEQ；ACK；SACK", "transport", "收到 SEQ=1000、长度 200 的连续数据后，下一个期望字节是？", "1200", "1001", "200"),
    ("reliability", "TCP 可靠传输", "TCP 检测丢失并重传，使应用收到有序字节流。", "发送端保留未确认数据，接收端可缓存乱序段；连接中断时仍可能向应用报告失败。", "文件传输需要应用验证完整文件，而不能只看一次 send 成功。", "unacked data；receive buffer；checksum", "transport", "send 返回成功是否证明远端应用已处理全部数据？", "不能，只能说明本地提交结果", "能", "只要是 TCP 就能"),
    ("rto", "RTT 与重传超时", "RTT 样本用于估计往返时间，RTO 决定等待确认的超时阈值。", "RTO 需考虑平滑 RTT 和波动；重传后样本可能不明确，连续超时通常退避。", "高抖动链路即使平均 RTT 较低也可能需要较大 RTO。", "SRTT；RTTVAR；RTO", "transport", "超时计时器主要防止什么？", "未确认数据永久等待", "HTTP Header 太多", "IP 地址变为 IPv6"),
    ("retransmit", "超时重传", "等待确认超过 RTO 后，发送端重新发送未确认数据。", "丢失数据或 ACK 都能造成超时；重复到达的数据需避免重复交付应用。", "丢掉一次 ACK 后，接收端可能再次收到相同数据。", "RTO；duplicate data；backoff", "transport", "ACK 丢失是否也可能触发数据重传？", "可能", "不可能", "只影响 UDP"),
    ("fast_retransmit", "快速重传", "发送端可根据重复确认，在超时前判断数据段可能丢失。", "经典 Reno 常以三个重复 ACK 触发快速重传；实际实现还可能采用 SACK 和其他恢复算法。", "中间一段丢失，但后面的段到达，会促使接收端反复确认缺口。", "duplicate ACK；SACK；lost segment", "transport", "经典快速重传是否必须等到 RTO 到期？", "不必须", "必须", "必须先重新三次握手"),
    ("sliding_window", "滑动窗口", "滑动窗口允许多个尚未确认的数据字节在途。", "累计 ACK 推进发送窗口；有效发送量受接收窗口、拥塞窗口和未确认量共同限制。", "高 RTT 链路需要足够的窗口才能持续利用带宽。", "send base；next sequence；inflight", "transport", "窗口前移通常依赖什么？", "收到新的有效确认", "更改域名", "每发送一位就重置"),
    ("flow_control", "流量控制", "TCP 流量控制保护接收端缓冲区不被发送端耗尽。", "接收端通过 rwnd 通告可接收量；零窗口需要相应探测，不能当作拥塞窗口。", "应用读取数据太慢时，接收窗口可能缩小。", "rwnd；window scale；zero window", "transport", "rwnd 主要反映谁的限制？", "接收端缓冲区", "路径中的所有路由器带宽", "DNS 缓存大小"),
    ("cwnd", "拥塞窗口", "拥塞窗口限制发送端给网络的在途数据量。", "拥塞控制按反馈调整 cwnd，实际可发送窗口通常受到 cwnd 和 rwnd 的共同约束。", "增大接收窗口并不能避免瓶颈链路的拥塞。", "cwnd；ssthresh；inflight", "transport", "cwnd 与 rwnd 取较小值通常限制什么？", "允许在途的数据量", "IPv4 地址数量", "证书有效期"),
    ("slow_start", "慢启动", "慢启动在连接初期逐步增加发送能力。", "经典模型中每次新确认促进 cwnd 增长，理想条件下每 RTT 近似翻倍；达到阈值后进入另一阶段。", "新连接不会立即无限制发送整个大文件。", "cwnd；ssthresh；ACK", "transport", "经典慢启动的窗口增长在理想条件下接近怎样？", "每 RTT 指数增长", "始终固定为零", "每 RTT 自动减半"),
    ("congestion_avoidance", "拥塞避免", "拥塞避免在网络已有在途数据时谨慎探测可用容量。", "经典 Reno 用近似每 RTT 增加一个 MSS 的方式增长窗口；不同算法的行为不同。", "本软件的教学 Reno 曲线不能当作所有 Windows TCP 的实际曲线。", "MSS；AIMD；cwnd", "transport", "能否把 Reno 曲线视为所有现代 TCP 的唯一行为？", "不能", "能", "只要 IPv6 就能"),
    ("fast_recovery", "快速恢复", "快速恢复在检测到部分丢失时保留一定发送能力。", "经典 Reno 依据重复确认调整 ssthresh 和 cwnd，收到新确认后退出恢复；并非完整重建连接。", "少量丢包与完全超时可能引起不同的窗口变化。", "ssthresh；dup ACK；recovery point", "transport", "快速恢复是否等同重新建立 TCP 连接？", "不等同", "完全等同", "只在 UDP 存在"),
    ("keepalive", "TCP Keepalive", "Keepalive 是可选的空闲连接探测机制。", "配置探测间隔和失败次数后可发现部分失活情况；应用心跳仍可提供业务层检查。", "聊天室用应用心跳确认对端还能处理业务。", "idle；interval；probe count", "transport", "TCP Keepalive 是否证明业务线程正常？", "不能", "一定证明", "自动证明 TLS 合法"),
    ("reset", "TCP RST", "RST 表示连接被复位或拒绝，而不是正常有序关闭。", "端点根据状态和序列号处理复位，应用可收到连接重置错误。", "向未监听的 TCP 端口连接时可能收到 RST。", "RST；sequence validation", "transport", "RST 与 FIN 的含义相同吗？", "不同", "完全相同", "RST 只存在于 HTTP"),
    ("udp", "UDP 数据报", "UDP 提供有边界的数据报传输，不保证到达、次序或不重复。", "每次发送形成一个数据报；应用需设计丢失处理和报文大小。", "语音应用可选择丢弃过时数据而继续播放。", "source port；destination port；length", "transport", "UDP 是否保证可靠有序送达？", "不保证", "保证", "只在 Wi-Fi 保证"),
    ("udp_checksum", "UDP 校验和", "UDP 校验和检测报文和部分地址信息的错误。", "计算包括伪首部、UDP 头部和数据；IPv6 通常要求非零校验和，存在特定标准例外。", "地址或载荷损坏可导致校验失败并丢弃。", "pseudo header；checksum", "packet", "校验和通过是否证明数据来自可信用户？", "不能，它不提供身份认证", "能", "它等同数字签名"),
    ("udp_reliable", "应用层可靠性", "使用 UDP 的应用可自行加入编号、确认、重传和超时。", "可靠性与拥塞控制需要共同设计，重复报文必须能够识别。", "游戏关键指令可以确认，频繁位置更新可以采用不同策略。", "message ID；ACK；retry；dedup", "transport", "UDP 应用加入重传后是否仍需考虑拥塞？", "需要", "不需要", "只需改 MAC"),
    ("quic", "QUIC 连接建立", "QUIC 在 UDP 上提供受保护的连接及可靠流等功能。", "QUIC 的握手与 TLS 1.3 集成；连接 ID 与路径验证参与连接识别。首次和恢复连接的成本不同。", "浏览器和服务器支持 HTTP/3 时可协商使用 QUIC。", "Initial；Handshake；Connection ID", "transport", "QUIC 底层通常使用哪种传输？", "UDP", "ICMP", "ARP"),
    ("quic_stream", "QUIC 流与多路复用", "QUIC 将多个流放在一个连接中，每个流独立排序。", "一个流的数据缺口通常不阻止其他流交付已有数据；共享拥塞控制仍会影响整个连接。", "某资源丢包时，其他资源对应流可继续交付。", "Stream ID；offset；MAX_DATA；MAX_STREAM_DATA", "transport", "QUIC 是否消除了所有网络拥塞影响？", "没有，各流仍共享网络容量", "消除了", "只要开启 HTTP/3 就无限快"),
    ("quic_migration", "QUIC 连接迁移", "QUIC 可在地址改变时使用连接 ID 维持连接身份。", "新路径需验证；迁移受握手状态和实现策略限制，不能假定完全没有延迟。", "设备从 Wi-Fi 切换到移动网络时，受支持的连接可尝试迁移。", "Connection ID；PATH_CHALLENGE；PATH_RESPONSE", "transport", "地址变化后 QUIC 是否需要考虑新路径验证？", "需要", "永远不需要", "只需 ARP 缓存"),
    ("quic_recovery", "QUIC 丢包恢复", "QUIC 用包编号和确认范围检测丢失并重发相应帧数据。", "重传数据可以进入新包编号，包编号和流内字节偏移承担不同职责。", "同一流数据重发时可以出现在不同编号的 QUIC 包中。", "Packet Number；ACK ranges；PTO；offset", "transport", "QUIC 包编号与流字节偏移是否是同一概念？", "不是", "是", "都是 IPv4 ID"),
    ("transport_compare", "TCP、UDP 与 QUIC 对比", "协议能力不同，实际性能还取决于实现和条件。", "TCP 提供可靠字节流，UDP 保留数据报边界，QUIC 提供受保护的多流连接；公平比较需固定载荷和网络条件。", "低丢包短请求和高丢包多资源场景可能得到不同结果。", "RTT；loss；goodput；CPU cost", "transport", "能否断言 QUIC 在所有条件下都更快？", "不能", "能", "只看协议名称就能"),
])

_group("DNS 与现代 Web", ["https://www.rfc-editor.org/info/rfc1034", "https://www.rfc-editor.org/info/rfc9110", "https://www.rfc-editor.org/info/rfc9114"], [
    ("dns", "域名结构与解析", "DNS 是按层次管理名字和记录的系统。", "递归解析器代表客户端查询，沿委派找到权威数据或使用有效缓存。", "www.example.com 包含主机名及域的层次，不等于一个永久固定 IP。", "QNAME；QTYPE；RCODE", "web", "DNS 名称是否只能对应一个 IP？", "不是，可对应多条记录", "只能一个", "不允许 IPv6"),
    ("dns_recursive", "递归与迭代查询", "递归请求要求解析器给出最终结果；迭代响应可以返回下一步委派信息。", "客户端通常向递归解析器查询，解析器再向其他服务器获取记录。", "家庭电脑不必亲自逐个查询全球根服务器。", "RD；RA；referral", "web", "普通客户端通常把递归查询交给谁？", "递归解析器", "每次随机一台根服务器", "交换机 MAC 表"),
    ("dns_hierarchy", "根、TLD 与权威服务器", "DNS 委派层次将名字管理分散到不同服务器。", "根返回顶级域的委派，TLD 返回下级域委派，权威服务器提供所负责区的数据。", "查询 www.example.com 可涉及根、com 和 example.com 的服务器。", "NS；glue；authority", "web", "根服务器通常直接保存所有网站的 A 记录吗？", "不保存，主要提供委派", "保存全部", "只保存 HTTP 页面"),
    ("dns_cache", "DNS 缓存与 TTL", "缓存暂存 DNS 回答，TTL 限制可复用时长。", "TTL 随时间减少；缓存命中不必重复完整解析。负回答也可按规则缓存。", "域名改址后，旧记录可能在 TTL 到期前仍被使用。", "TTL；cache hit；negative caching", "web", "DNS TTL 到期后应怎样处理记录？", "重新查询有效答案", "永久使用旧地址", "清除全部网卡"),
    ("dns_records", "A、AAAA 与 CNAME", "A 表示 IPv4 地址，AAAA 表示 IPv6 地址，CNAME 表示名字别名。", "解析 CNAME 后还需继续解析其目标；别名和地址记录有各自 TTL。", "www 的别名指向 CDN 域名，随后得到地址。", "A；AAAA；CNAME；TTL", "web", "AAAA 记录表示什么？", "IPv6 地址", "四个 IPv4 地址", "邮件优先级"),
    ("dns_other", "MX、TXT 与 NS", "MX 描述邮件服务器，TXT 保存文本，NS 标识权威名字服务器。", "不同记录类型由不同应用解释；TXT 不是通用加密存储。", "邮件服务通过 MX 优先级选择目标服务器。", "MX preference；TXT；NS", "web", "邮件服务器选择主要查询哪类记录？", "MX", "AAAAA", "HTTP"),
    ("doh", "DNS over HTTPS", "DoH 将 DNS 查询放入 HTTPS 连接。", "传输加密保护客户端到解析器这一段；解析器仍可能了解查询内容。", "浏览器可向明确配置的 DoH 服务查询。", "HTTPS；DNS wire message；resolver", "security", "DoH 是否让解析器无法知道查询域名？", "不是，解析器仍能处理查询", "是", "会删除 DNS 系统"),
    ("dot", "DNS over TLS", "DoT 使用 TLS 保护 DNS 客户端与解析器通信。", "常见服务端口为 TCP 853，仍需验证服务器身份；TLS 传输保护与 DNSSEC 数据验证用途不同。", "指定的 DoT 解析器可以返回 A 或 AAAA 记录。", "TLS；853；certificate", "security", "DoT 常见端口是什么？", "TCP 853", "UDP 67", "TCP 22"),
    ("dnssec", "DNSSEC", "DNSSEC 为 DNS 数据提供来源认证和完整性验证。", "签名和信任链使验证器检查数据；DNSSEC 本身不加密查询，也不保证网站内容安全。", "签名验证失败的回答可被验证解析器拒绝。", "DNSKEY；DS；RRSIG；AD", "web", "DNSSEC 是否直接加密 DNS 查询？", "不会", "会", "只加密 HTTP 图片"),
    ("http11", "HTTP/1.1", "HTTP 用请求与响应交换资源语义，HTTP/1.1 使用文本形式头部。", "连接可以复用，但消息边界必须由长度或传输编码等规则定义。", "GET /index.html 请求网页，服务器返回状态及内容。", "method；target；Host；Content-Length", "web", "HTTP 请求是否一定包含正文？", "不一定", "一定", "只有 DNS 才有正文"),
    ("http2", "HTTP/2", "HTTP/2 在一个连接中用二进制帧承载多个流。", "流分用和头部压缩改善效率；底层 TCP 的丢失仍可能阻止后续字节交付。", "多个图片请求可同时共用同一 HTTP/2 连接。", "stream ID；frame type；HPACK", "web", "HTTP/2 多流是否完全避开 TCP 的队头阻塞？", "没有完全避开", "完全避开", "不使用传输层"),
    ("http3", "HTTP/3", "HTTP/3 将 HTTP 语义映射到 QUIC 流。", "QUIC 提供传输和 TLS 保护，HTTP/3 使用专门帧和 QPACK；双方及路径支持影响能否使用。", "一个网站同时可支持 HTTP/1.1、HTTP/2 与 HTTP/3。", "QUIC stream；QPACK；SETTINGS", "web", "HTTP/3 通常基于哪种协议？", "QUIC", "ARP", "SMTP"),
    ("http_methods", "HTTP 方法", "GET、POST、PUT、DELETE 等方法表达不同的请求意图。", "安全性和幂等性属于方法语义，服务实现还需遵守语义；诊断默认使用无破坏的读取。", "重复 PUT 应有与一次 PUT 相同的目标状态，但响应可以不同。", "GET；POST；PUT；DELETE；HEAD", "web", "哪种方法通常用于获取资源？", "GET", "ARP", "SYN"),
    ("http_status", "HTTP 状态码", "状态码描述 HTTP 层处理结果，不能单独解释所有网络故障。", "2xx 通常成功，3xx 需进一步处理重定向，4xx 表示客户端相关情况，5xx 表示服务器相关情况。", "404 说明服务器返回了未找到，区别于 DNS 解析失败。", "200；301；404；500", "web", "收到 HTTP 404 是否证明 TCP 没建立？", "不是，已有 HTTP 响应", "是", "证明网卡关闭"),
    ("http_headers", "HTTP Header", "Header 携带内容类型、缓存指令和协商等元数据。", "字段解释受 HTTP 语义约束；应用不能仅根据字符串外观判断响应正文的安全性。", "Content-Type 告诉客户端正文是 JSON 还是文本。", "Content-Type；Accept；User-Agent", "web", "Content-Type 主要描述什么？", "消息正文媒体类型", "网卡 MAC", "路由跳数"),
    ("cookies", "Cookie 与 Session", "Cookie 是浏览器保存并按规则附带的数据；Session 常在服务端维护状态。", "Session ID 可通过 Cookie 关联用户状态。Secure、HttpOnly、SameSite 等属性约束使用。", "登录后服务器以会话标识关联后续请求。", "Set-Cookie；Cookie；Secure；HttpOnly", "web", "HttpOnly 主要限制什么？", "脚本访问 Cookie", "DNS 查询", "所有网络通信"),
    ("http_cache", "HTTP 缓存", "HTTP 缓存复用满足条件的响应，并在必要时重新验证。", "Cache-Control 控制新鲜度，ETag 和 If-None-Match 可支持条件请求。", "资源未改变时服务器可返回 304，客户端复用正文。", "Cache-Control；ETag；304", "web", "HTTP 304 通常表示什么？", "可复用已有缓存正文", "DNS 没找到", "TCP 已重置"),
    ("tls13", "TLS 1.3", "TLS 1.3 为传输提供加密、完整性和认证能力。", "握手协商密钥及参数，证书认证需要检查身份和信任；恢复和早期数据有额外安全条件。", "HTTPS 客户端必须验证证书所对应的主机名。", "ClientHello；ServerHello；Finished；ALPN", "security", "连接加密是否足以证明服务器身份正确？", "不足，还需验证身份和信任", "足够", "只要握手快就足够"),
    ("certificate", "数字证书与 CA", "证书把身份信息与公钥关联，并由签发者签名。", "客户端验证有效期、主机名、用途和信任链等条件；真实验证由成熟 TLS 库负责。", "自签名证书用于本地实验时需要明确实验信任配置。", "SAN；issuer；validity；public key", "security", "证书主机名不匹配时应如何？", "报告身份验证失败", "静默当作成功", "仅修改本机 IP"),
    ("cdn", "CDN", "CDN 通过分布式边缘节点缓存或代理内容。", "DNS、Anycast 或应用调度可引导请求；命中率和位置等因素影响实际响应。", "同一域名在不同网络查询可能得到不同地址。", "edge；cache；origin；Anycast", "web", "CDN 地址是否固定等于源站物理位置？", "不是", "是", "只要 IPv4 就是"),
    ("websocket", "WebSocket", "WebSocket 提供持续的双向消息通信。", "在常见 HTTP/1.1 场景先升级连接，再按帧规则传输；客户端帧遮罩不是加密。", "实时聊天室推送消息无需每次新建 HTTP 请求。", "Upgrade；frame；opcode；mask", "programming", "WebSocket 的遮罩是否等同 TLS 加密？", "不是", "是", "比 TLS 更强"),
    ("proxy", "反向代理与负载均衡", "反向代理代表后端接收请求，负载均衡在多个后端间分配流量。", "代理可处理 TLS 和缓存；健康检查帮助避免把请求交给故障实例。", "同一入口域名后面可能有多台应用服务器。", "upstream；health check；forwarded headers", "web", "负载均衡入口是否必须只有一个后端？", "不必须", "必须", "只能使用 UDP"),
])

_group("网络安全与 VPN", ["https://www.rfc-editor.org/info/rfc8446", "https://www.wireguard.com/protocol/", "https://www.rfc-editor.org/info/rfc4253"], [
    ("tls_handshake", "TLS 握手", "TLS 握手让双方协商参数、建立密钥并验证对方身份。", "ClientHello 提供能力与密钥份额，服务端选择参数；Finished 验证握手完整性。", "本地 TLS 实验可比较受信任证书与身份不匹配错误。", "key share；Certificate；Finished；ALPN", "security", "TLS Finished 的主要作用是什么？", "验证握手完整性", "分配 DHCP 地址", "设置路由器端口"),
    ("cert_chain", "证书链验证", "证书链把服务器证书连接到客户端接受的信任锚。", "验证包括签名关系、用途、有效期和主机身份；仅列出证书不等于验证通过。", "少一个中间证书可能导致某些客户端无法建立信任链。", "leaf；intermediate；trust anchor", "security", "看到证书文本是否等同信任链验证成功？", "不等同", "等同", "只要证书文件较大就等同"),
    ("symmetric", "对称加密", "对称加密使用共享密钥保护数据。", "认证加密同时提供机密性和完整性；密钥和 nonce 的使用需要满足算法规则，由成熟库处理。", "TLS 记录常使用协商后的对称算法保护传输。", "key；nonce；AEAD；tag", "security", "共享密钥泄露主要破坏什么？", "该密钥保护的机密性或完整性", "只改变 DNS TTL", "只影响 MAC 表"),
    ("asymmetric", "非对称密码学", "非对称算法使用成对密钥，公钥与私钥承担不同操作。", "签名、密钥协商和加密不是同一个操作；TLS 1.3 不应简单讲成用 RSA 加密所有数据。", "服务器用私钥完成身份相关证明，客户端根据证书公钥验证。", "public key；private key；key exchange", "security", "私钥应当怎样管理？", "保密保存，不能当普通公钥分发", "公开到所有客户端", "放入 ARP 缓存"),
    ("hash", "哈希与数字签名", "哈希产生数据摘要，数字签名支持验证签名者与内容完整性。", "普通哈希没有秘密，攻击者也能重算；签名验证需要正确的公钥和算法。", "下载文件对比摘要可以发现变化，但摘要来源也需可信。", "SHA-256；digest；signature", "security", "单独一个公开哈希能证明作者身份吗？", "不能", "能", "长度够长就能"),
    ("ssh", "SSH 基础", "SSH 提供受保护的远程登录、命令和隧道等功能。", "客户端验证主机密钥，服务端验证用户；首次主机信任需核对来源。", "本软件的 SSH 读取实验需要用户指定自有服务器，不自动探测公网。", "host key；user authentication；port 22", "security", "主机密钥突然变化应怎样处理？", "检查原因并核对服务器身份", "永远忽略", "自动关闭防火墙"),
    ("firewall", "防火墙规则", "防火墙按方向、协议、地址、端口和连接状态控制流量。", "规则优先级及默认策略因系统而异；教学按明确顺序判定，读取真实规则不修改它们。", "允许本地测试端口与允许整个公网地址段具有不同范围。", "direction；protocol；port；action", "security", "查看 Windows 防火墙规则是否需要自动修改规则？", "不需要", "需要全部关闭", "需要删除所有路由"),
    ("vpn", "VPN 隧道", "VPN 在现有网络上建立逻辑通道，常对内部数据进行认证和加密。", "内层包被封装为外层包，路径 MTU 和路由会受影响；保护范围取决于隧道终点和配置。", "公司 VPN 将办公网流量交给虚拟接口。", "inner packet；outer packet；tunnel", "security", "VPN 连接后是否保证所有网站服务都可信？", "不保证", "保证", "自动消除钓鱼网站"),
    ("wireguard", "WireGuard 原理", "WireGuard 使用公钥识别对等方，以 UDP 承载加密隧道。", "握手使用成熟密码学组合，AllowedIPs 同时参与选路与源地址限制。此处只教学，不创建商业 VPN。", "为办公子网配置 AllowedIPs 可以形成分流隧道。", "peer public key；AllowedIPs；UDP endpoint", "security", "WireGuard 的 AllowedIPs 只表示说明文字吗？", "不是，它参与选路与限制", "是", "它是 HTTP 状态码"),
    ("split_tunnel", "VPN 路由与分流", "分流按目的前缀决定走隧道还是普通路径。", "最长前缀匹配仍适用；DNS 和默认路由配置也影响业务路径。", "办公网走 VPN，普通网站走本地默认路由。", "route prefix；metric；DNS", "security", "分流是否仍需要检查路由表？", "需要", "不需要", "只看 SSID 即可"),
    ("plaintext", "明文与加密的观察边界", "明文载荷可直接阅读；加密载荷通常不能仅凭抓包还原。", "加密流量仍可能暴露端点、长度和时序等元数据；解密需合法获得对应密钥和工具支持。", "抓到 HTTPS 包不等于能直接看到账号密码。", "payload；metadata；traffic keys", "packet", "未知密钥的 HTTPS 抓包能否直接解密正文？", "通常不能", "一定能", "按颜色分类即可"),
])

_group("游戏网络与 P2P", ["https://www.rfc-editor.org/info/rfc8489", "https://www.rfc-editor.org/info/rfc8656", "https://www.rfc-editor.org/info/rfc8445"], [
    ("client_server", "游戏客户端与服务器", "服务器模式通常由权威服务器决定游戏状态。", "客户端发送输入并接收状态更新；服务器校验和同步策略决定一致性。", "角色移动输入到服务器后再广播新的状态。", "tick；input；snapshot；authority", "gaming", "权威服务器主要承担什么？", "确定并分发可信游戏状态", "自动降低所有物理延迟", "生成网卡 MAC"),
    ("p2p", "P2P 通信", "P2P 让对等端直接或通过辅助设施交换数据。", "对等连接可能需要发现、身份验证、NAT 协商和中继，不能只靠两个私有地址通信。", "两台家庭电脑可能通过候选地址检查选择直连路径。", "peer；candidate；connectivity check", "gaming", "两个不同家庭的私有 IPv4 地址能否直接作为公网直连目标？", "通常不能", "始终可以", "只要端口相同就可以"),
    ("prediction", "客户端预测", "客户端预测提前根据本地输入估计状态，减少等待反馈的感觉。", "收到权威状态后校正误差，并可能重放未确认输入；预测不改变实际 RTT。", "按下移动键后先本地移动，再与服务端位置对齐。", "input sequence；predicted state；reconciliation", "gaming", "预测是否直接减少网络传播时延？", "没有，只改善响应体验", "有", "会把所有 RTT 设为零"),
    ("interpolation", "状态插值", "插值在已收到的状态样本之间估算平滑显示的位置。", "适度延后播放可吸收抖动，但增加显示延迟；外推是基于历史向未来估计，含义不同。", "其他玩家的动作可以在两个快照之间平滑呈现。", "snapshot time；interpolation delay", "gaming", "插值缓冲通常需要哪种取舍？", "平滑程度与显示延迟", "IPv4 与 MAC 长度", "证书与 DHCP 租约"),
    ("stun", "STUN", "STUN 帮助客户端发现服务端观察到的地址，并用于连接检查等流程。", "映射地址不是通用可达保证；NAT 的映射和过滤行为可能随目的端变化。", "STUN 得到外部端口后，仍需检查对等端是否能回包。", "Binding；XOR-MAPPED-ADDRESS；transaction ID", "gaming", "得到 STUN 外部地址是否保证任意对等端都能连接？", "不保证", "保证", "保证不需认证"),
    ("turn", "TURN 中继", "TURN 在直接路径不可用时提供受控中继。", "客户端获取分配并建立权限或通道，通过中继传递数据；路径长度和服务器成本影响性能。", "严格 NAT 环境下，两端可能都经中继通信。", "allocation；permission；channel", "gaming", "TURN 的主要用途是什么？", "中继通信", "修改本机 MAC", "替代 TLS 证书"),
    ("nat_traversal", "NAT 穿透", "NAT 穿透是建立可返回的映射和通过过滤检查的组合过程。", "打洞依赖 NAT 行为、时序和协议；部分情况需要中继，不应承诺所有网络都直连。", "双层 NAT 的玩家可能无法通过单层端口映射直连。", "mapping；filtering；hole punching", "gaming", "UDP 打洞是否一定成功？", "不一定，受 NAT 和防火墙影响", "一定", "只要 IPv4 就一定"),
    ("virtual_lan", "虚拟局域网联机", "虚拟局域网工具将某类流量通过隧道或中继连接到远端。", "实际支持二层广播还是三层路由取决于实现；发现协议可能需要额外转发。", "游戏的局域网发现广播不一定能自动穿过三层 VPN。", "tunnel；discovery；subnet", "gaming", "三层 VPN 是否总能转发局域网广播发现？", "不总能", "总能", "与实现完全无关"),
    ("minecraft", "Minecraft 联机", "Minecraft 的联机方式取决于版本、服务器设置和网络环境。", "Java 版常见服务器使用 TCP 25565，Bedrock 常见 UDP 19132，管理员可以改端口；还需检查绑定地址和授权。", "本机能连服务器不代表公网端口已经可达。", "listen address；edition；configured port", "gaming", "本机回环测试成功是否证明外网可连接？", "不能", "能", "等于 CGNAT 已消失"),
    ("stability", "网络稳定性报告", "稳定性报告应注明目标、样本量、时间、超时规则和统计方法。", "平均 RTT、变化和超时比例描述本次探测；ICMP 结果不能直接等同某款游戏业务流。", "探测自有服务器并记录 RTT 图，而不是虚构第三方游戏服务器数据。", "samples；mean RTT；jitter；timeout ratio", "diagnostics", "ICMP 超时比例能否直接代表全部游戏业务丢包？", "不能，需要协议和目标一致的测量", "能", "与测量方法完全无关"),
])

_group("抓包与协议分析", ["https://scapy.readthedocs.io/en/latest/usage.html", "https://npcap.com/guide/", "https://www.rfc-editor.org/info/rfc9293"], [
    ("pcap", "PCAP 与 PCAPNG", "抓包文件保存观测到的报文和时间等元数据。", "链路类型、截断长度及接口信息影响解析，时间戳不保证所有接口严格同步。", "导入教学 PCAP 后可按协议筛选，并保留原始字节。", "timestamp；link type；captured length", "packet", "抓包中 captured length 小于原始长度说明什么？", "可能被截断", "一定解密成功", "一定没有载荷"),
    ("packet_fields", "逐层字段解析", "协议分析器按链路头和上层类型解释字段。", "先确认链路类型，再解释 EtherType、IP Protocol 或 Next Header，不能固定把所有偏移当以太网。", "无以太网头的回环捕获需要按其链路类型处理。", "linktype；EtherType；Protocol；Next Header", "packet", "所有抓包都能直接按以太网头解析吗？", "不能", "能", "只要扩展名相同就能"),
    ("hex", "原始十六进制视图", "十六进制视图显示实际捕获字节，便于核对字段偏移。", "每两位十六进制代表一个字节，字段端序按协议规则解释。", "端口 443 的网络字节序为 01 BB。", "offset；byte；network byte order", "packet", "01 BB 按大端整数解释为多少？", "443", "47873", "1"),
    ("session", "TCP 会话时序", "会话分析按端点和协议关联双向报文。", "序列号、ACK、标志及时间帮助发现重传和关闭；抓包点可能漏掉部分报文。", "两次相同字节区间出现可提示重传，但需结合方向和上下文。", "5-tuple；SEQ；ACK；flags", "packet", "抓包未看到握手是否一定说明没有握手？", "不一定，捕获可能晚开始或漏包", "一定", "证明 UDP 自动变 TCP"),
    ("traffic_stats", "流量统计", "流量统计统计捕获范围内的包数、字节数和端点分布。", "捕获过滤、丢包和截断会影响统计，不能把文件样本当作所有网卡总流量。", "一分钟文件中的 TCP 包比例只代表这份捕获。", "packet count；captured bytes；time span", "packet", "离线 PCAP 统计是否自动等于本机全部历史流量？", "不是", "是", "只要文件够大就是"),
    ("live_capture", "授权实时抓包", "实时抓包读取所选接口上的可见报文，Windows 通常需要 Npcap。", "驱动或权限不可用时应明确报错，同时保留离线分析；不自动安装或扩大授权接口范围。", "用户明确选择一个接口并设定有限抓包时间。", "interface；BPF；duration；permissions", "packet", "未安装 Npcap 时软件应怎样？", "正常启动，保留离线分析", "假装抓到了包", "自动关闭安全设置"),
    ("capture_scope", "抓包证据与隐私", "抓包只代表指定位置和时段所观察到的数据。", "共享文件前应清理敏感载荷和标识。仅隐藏 IP 的摘要不会抹除原始包中的秘密。", "实验报告可脱敏地址，但不应随意分发含登录信息的 PCAP。", "capture point；payload；redaction", "packet", "报告隐藏 IP 是否足以使原始 PCAP 完全匿名？", "不足", "足够", "可以删除所有风险"),
])

_group("真实网络诊断", ["https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/ping", "https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tracert"], [
    ("adapters", "网卡状态与地址", "网卡启用、已连接及具备地址是不同状态。", "诊断先检查接口和 IPv4/IPv6 配置，再看网关与 DNS；不支持的信息显示不可用。", "Wi-Fi 信号正常但只获得链路本地地址时应继续检查地址分配。", "oper status；IP；prefix；gateway", "observe", "网卡显示启用是否等于已连接互联网？", "不等于", "等于", "等于有公网 IPv4"),
    ("ping", "Ping 实测", "Ping 通过 Echo 请求和回复测量目标响应及往返时间。", "目标或中间设备可限制 ICMP；必须显示超时和命令实际结果，不能补造时延。", "先探测自有网关，再探测用户指定目标。", "target；count；RTT；timeout", "diagnostics", "Ping 结果中的 RTT 属于哪种数据？", "该次目标的观测结果", "全世界网络速度", "所有游戏的固定延迟"),
    ("traceroute", "Traceroute 路径观察", "Traceroute 利用逐步增长的 TTL 观察中间回复。", "某些路由器不回复，负载均衡可改变路径；跳点地址不是精确地理位置。", "某跳显示 *，之后仍有目标回复，说明不必把该跳当作故障终点。", "TTL；hop；Time Exceeded", "diagnostics", "中间跳超时而最终目标有回复说明什么？", "中间设备可能不回应探测", "目标一定断网", "证书一定过期"),
    ("dns_failure", "DNS 故障诊断", "域名解析失败应区分无回答、超时、服务器错误和无对应记录。", "比较明确配置的解析器和记录类型，结合 TCP/HTTPS 证据；访问 IP 的失败也可能涉及虚拟主机或证书。", "同一域名的 A 成功而 AAAA 缺失不等于 DNS 完全不可用。", "RCODE；A；AAAA；resolver；timeout", "diagnostics", "AAAA 无记录但 A 正常是否必然是 DNS 服务故障？", "不是", "是", "说明网卡无 MAC"),
    ("tcp_probe", "TCP 端口连通性", "TCP 探测尝试连接明确目标和端口。", "连接成功表示传输层连接建立，不保证业务协议成功；拒绝和超时代表不同证据。", "443 能建立 TCP，但 TLS 主机名验证可能失败。", "host；port；connect time；error", "diagnostics", "TCP 443 连接成功是否保证 HTTPS 验证通过？", "不能保证", "保证", "表示 DNSSEC 已通过"),
    ("https_probe", "HTTPS 连接检查", "HTTPS 检查需要分别观察 DNS、连接、TLS 和 HTTP 结果。", "证书验证失败、HTTP 500 和连接超时对应不同层次；不以禁用验证掩盖错误。", "服务端返回 503 时，应保留状态码，而不能显示网络完全断开。", "TLS version；certificate；HTTP status；timing", "diagnostics", "HTTP 503 与 TCP 超时应合并成相同成功结果吗？", "不应，应分别报告", "应该", "只显示绿色即可"),
    ("rates", "上传与下载速率", "接口速率监控用累计字节计数在时间区间内的差值计算。", "速率 = 字节差/时间差；计数复位、接口变化或暂停采样需要重新建立基准。", "后台下载时选中接口的接收速率会上升。", "bytes sent；bytes received；sample interval", "observe", "累计收包字节能直接当作瞬时下载速率吗？", "不能，需要时间差分", "能", "乘 MAC 长度即可"),
    ("connections", "连接、监听端口与进程", "系统连接表显示本地和远端端点、状态及可见的进程关联。", "权限和连接生命周期影响是否能读取进程信息；监听端口不一定开放给所有网络。", "只监听 127.0.0.1 的服务器通常不能直接从远端连接。", "local address；remote address；PID；LISTEN", "observe", "只监听 127.0.0.1 是否通常接受远端直接连接？", "不接受", "接受所有远端", "等于监听公网全部地址"),
    ("diagnostic_order", "分层故障排查", "排障按证据逐步缩小范围，先检查本地配置再检查目标服务。", "可依次检查接口、地址、网关、路径、DNS、TCP 和 HTTPS；每一步保留失败与不可测原因。", "Wi-Fi 已连但网页打不开时，先检查有效地址，不直接修改全部设置。", "interface；gateway；DNS；TCP；HTTPS", "diagnostics", "诊断向导发现故障后应自动修改用户 DNS 吗？", "不应，修改需另外明确授权", "应立即修改", "应关闭全部防火墙"),
])

_group("Socket 与网络编程", ["https://docs.python.org/3/library/socket.html", "https://docs.python.org/3/library/select.html", "https://docs.python.org/3/library/asyncio.html"], [
    ("socket", "Socket 与端点", "Socket 是程序使用操作系统网络服务的接口。", "地址族、套接字类型和协议共同决定使用方式；绑定与连接承担不同操作。", "AF_INET + SOCK_STREAM 通常构造 IPv4 TCP Socket。", "family；type；bind；connect", "programming", "bind 通常把什么关联到 Socket？", "本地地址和端口", "远端密码", "CPU 指令长度"),
    ("tcp_server", "TCP 客户端与服务器", "TCP 服务器监听连接，accept 返回用于该客户端通信的新 Socket。", "监听 Socket 持续接入，已接入 Socket 收发数据；错误和关闭需各自处理。", "本地回显服务器读到数据后原样返回。", "listen；accept；sendall；recv", "programming", "accept 返回的通信 Socket 与监听 Socket 相同吗？", "不是同一个", "完全相同", "只在 IPv6 不同"),
    ("stream_framing", "TCP 字节流与消息边界", "TCP 不保留应用一次 send 的边界。", "一次 recv 可能返回部分消息或多条消息，因此需要长度字段、分隔符或固定格式。", "聊天程序可用长度前缀或逐行 JSON 区分消息。", "length prefix；delimiter；buffer", "programming", "一次 send 是否保证对应一次完整 recv？", "不保证", "保证", "只要数据小于 MTU 就保证"),
    ("udp_server", "UDP 客户端与服务器", "UDP 服务通过 sendto 和 recvfrom 交换带地址的数据报。", "接收端需要足够缓冲区，检查发送者并处理超时；无回应不能无限阻塞整个 GUI。", "回环 UDP 回显验证数据报边界和对端地址。", "sendto；recvfrom；datagram", "programming", "recvfrom 相比普通字节读取还能返回什么？", "发送方地址", "完整路由表", "服务器私钥"),
    ("chatroom", "多客户端聊天室", "聊天室需同时管理多个连接和消息分发。", "使用线程或事件循环处理客户端，断开时移除连接并关闭资源，消息需明确编码与边界。", "两个本地客户端同时向服务器发送文字。", "client registry；broadcast；disconnect", "programming", "客户端断开后服务器应如何处理？", "移除连接并释放资源", "永久保留失效 Socket", "删除系统网卡"),
    ("file_transfer", "文件传输", "文件传输需约定长度、名称、安全存储和完整性检查。", "循环读写处理部分传输，禁止把远端任意路径直接写入文件系统；接收端核对实际字节数。", "传输一个临时测试文件并比较 SHA-256。", "length；chunk；digest；safe filename", "programming", "接收远端文件名时可直接写任意绝对路径吗？", "不应，应限制到授权目录", "可以", "只要 TCP 就安全"),
    ("local_http", "本地 HTTP/HTTPS 服务器", "本地测试服务器为请求和证书实验提供可控制的目标。", "默认绑定回环地址，设定请求路径并正确关闭；本地自签名证书需明确测试信任策略。", "对 127.0.0.1 发 GET 并观察状态与响应头。", "bind address；GET；TLS context", "programming", "本地实验默认应绑定什么地址？", "本机回环地址", "所有公网地址", "随机第三方服务器"),
    ("nonblocking", "非阻塞 Socket", "非阻塞操作在暂时无法完成时返回相应状态而不是无限等待。", "程序等待读写就绪，保留未发送的数据，再尝试后续操作；就绪也不代表不会发生错误。", "慢客户端不应阻塞整个聊天服务器。", "BlockingIOError；send buffer；readiness", "programming", "非阻塞 send 未发送全部数据时应怎样？", "保留余下数据等待再次可写", "当作全部成功", "直接丢掉剩余字节"),
    ("select_io", "select 与 I/O 多路复用", "select 等工具等待多个 Socket 的读写状态。", "事件循环根据就绪集合处理 I/O；Windows 的 select 支持范围与 Unix 文件描述符模型不同。", "一个线程管理多个回环客户端连接。", "readable；writable；timeout", "programming", "select 的主要目的是什么？", "同时等待多个 I/O 对象就绪", "执行 CPU 汇编", "修改 DNS 密码"),
    ("socket_threads", "多线程服务器", "多线程可让不同连接的阻塞 I/O 独立等待。", "共享客户端表需要同步，关闭时通知并等待线程退出；线程数量和资源仍需限制。", "每个本地回显连接由一个有超时的工作线程处理。", "thread；lock；stop event；join", "programming", "共享客户端集合是否需要考虑并发修改？", "需要", "永远不需要", "只要 Python 就无并发风险"),
    ("timeouts", "连接超时与异常", "超时约束等待时间，异常说明不同的失败类型。", "解析失败、拒绝连接、超时和协议错误应分别记录；finally 或上下文管理器负责关闭 Socket。", "对不存在的本地服务连接可验证拒绝处理。", "timeout；OSError；try/finally", "programming", "GUI 网络操作能否无限等待目标回复？", "不应，需超时并在后台执行", "应该", "只要目标是本机就能"),
    ("c_socket", "C 语言 Winsock", "Windows C 网络程序使用 Winsock API 和对应初始化。", "WSAStartup 初始化环境，程序使用 SOCKET 类型并链接 ws2_32，结束时关闭 Socket 和清理。", "使用已安装编译器运行本地 TCP 回显；缺编译器应报告不可运行。", "WSAStartup；SOCKET；closesocket；ws2_32", "programming", "Windows Winsock 程序通常先调用什么？", "WSAStartup", "fork", "chmod"),
])

_group("计算机组成原理", ["https://docs.python.org/3/library/struct.html", "https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html"], [
    ("binary", "二进制、十进制与十六进制", "相同整数可以用不同进制表示，数值本身不变。", "二进制每位权重为 2 的幂，十六进制每位对应四个二进制位。", "十进制 10 等于二进制 1010 和十六进制 A。", "bit weight；radix；hex digit", "binary", "十六进制 F 对应多少个二进制 1？", "四个", "八个", "十五个"),
    ("complements", "原码、反码与补码", "原码以符号位和大小表示，反码按位变换负数，补码采用模 2^n 的编码。", "补码可用同一加法器处理正负数；最小负数不能用同位宽原码表示。", "8 位补码 -1 为 11111111，-128 为 10000000。", "sign；ones complement；twos complement", "binary", "8 位补码 11111111 表示什么有符号整数？", "-1", "127", "0"),
    ("bitwise", "位运算", "AND、OR、XOR、NOT 和移位逐位改变位模式。", "掩码可提取或清除某些位；固定宽度实验需截断结果并明确逻辑移位规则。", "IPv4 地址与掩码按位 AND 得到网络地址。", "AND；OR；XOR；NOT；SHL；SHR", "binary", "1010 AND 1100 的结果是什么？", "1000", "1110", "0110"),
    ("overflow", "整数溢出", "固定宽度无法表示所有整数，超出范围需要按规则处理。", "无符号进位和有符号溢出是不同标志；C 的有符号溢出不能简单当作保证回绕。", "8 位有符号 127 + 1 在教学 ALU 中得到 -128 并设置溢出标志。", "carry；overflow；Z；N", "binary", "进位与有符号溢出是否一定同时出现？", "不一定", "一定", "永不出现"),
    ("ieee754", "IEEE 754 浮点表示", "binary32 和 binary64 用符号、阶码和尾数表示浮点数。", "正常数有隐含前导 1，非正规数和特殊值使用不同规则；十进制小数不一定可精确表示。", "0.1 在二进制浮点中通常是近似值。", "sign；exponent；fraction；NaN；infinity", "binary", "binary32 的总位数是多少？", "32", "64", "128"),
    ("gates", "逻辑门与组合电路", "逻辑门根据输入位计算输出位，组合电路的输出由当前输入决定。", "按连线依赖求值；教学组合电路若含反馈环路会报错，不能假装已经实现时序存储。", "用 XOR 和 AND 构造半加器。", "gate；input；output；wire", "logic", "XOR 在两个输入相同时输出什么？", "0", "1", "输入和为十进制 2"),
    ("adder", "半加器与全加器", "半加器处理两位相加，全加器还接收低位进位。", "半加器和为 XOR、进位为 AND；串联全加器可组成多位加法器。", "1 + 1 + 1 得到和位 1、进位 1。", "sum；carry-in；carry-out", "logic", "全加器 1、1、1 的和位与进位分别是什么？", "1 和 1", "0 和 1", "1 和 0"),
    ("alu", "ALU 与状态标志", "ALU 执行整数运算和逻辑运算，并产生状态标志。", "教学模型按指定位宽计算结果、零、负、进位或借位和溢出标志；真实 ISA 的标志语义不同。", "SUB 相等操作数得到零，条件跳转可读取 Z 标志。", "opcode；operand；Z；N；C；V", "cpu", "结果为零时教学 ALU 的哪一标志为真？", "Z", "永远 V", "永远 C"),
    ("cpu", "教学 CPU 与指令集", "CPU 模型包含 PC、通用寄存器、标志、指令存储、数据存储和 ALU。", "MOV、LOAD、STORE、ADD、SUB、JMP 等指令改变独立状态，SEND 生成虚拟网络事件。", "MOV R0,72 后 STORE 10,R0 将一个字写入教学地址 10。", "PC；R0-R7；flags；instruction；memory", "cpu", "教学 STORE 10,R0 将什么写到哪里？", "R0 的值写入地址 10", "地址 10 写入 R0", "向公网端口 10 发包"),
    ("fetch_decode", "取指、译码与执行", "指令周期包含取得指令、解释操作和改变状态的步骤。", "PC 指向下一指令，跳转可改变其推进方向；教学模型不是现代 CPU 流水线或微架构仿真。", "JZ 读取零标志，成立时改 PC。", "fetch；decode；execute；PC", "cpu", "跳转指令主要改变什么？", "PC", "DNS TTL", "网卡 MAC"),
    ("register_memory", "寄存器与数据存储", "寄存器是指令直接访问的少量状态，数据存储通过地址读写。", "LOAD 从存储读入寄存器，STORE 把值写回；地址与地址处的值必须区分。", "地址 10 的值为 72，不代表地址本身是 72。", "LOAD；STORE；address；value", "cpu", "LOAD R0,10 读取的是哪一项？", "内存地址 10 处的值", "把 R0 变为 10", "第 10 个端口的 IP"),
    ("cache", "Cache 命中与缺失", "Cache 保存主存数据块的副本以减少部分访问成本。", "命中可直接使用缓存块；缺失需装入数据并可能替换已有块。教学周期由参数给定。", "访问同一块内多个字节可能都命中同一个 Cache 行。", "block；tag；valid；hit；miss", "cache", "第一次读取从未装入的块通常是什么？", "缺失", "命中", "TCP 超时"),
    ("cache_mapping", "直接映射与组相联", "直接映射每个块仅有一个候选行，组相联在指定组内有多个候选行。", "组号由块号对组数取模，Tag 区分映射到同组的块；全相联只有一组。", "直接映射中两个热点块竞争同一行可造成反复缺失。", "block offset；set index；tag；ways", "cache", "四路组相联的一个组有多少候选行？", "四个", "一个", "无限个"),
    ("cache_replace", "FIFO 与 LRU 替换", "FIFO 替换最早装入项，LRU 替换最长时间未使用项。", "命中会更新 LRU 的使用记录，但不会改变 FIFO 的装入次序；脏块替换还可能写回。", "访问 A、B、A、C 时，在两行全相联 Cache 中两策略可能替换不同块。", "loaded time；last used；dirty；writeback", "cache", "一次命中通常会更新哪种替换策略的次序？", "LRU", "FIFO 必须重装全部行", "两者都完全不变"),
    ("stack_heap", "栈与堆", "栈按后进先出管理调用相关数据，堆支持动态分配与释放。", "教学内存让堆向上、栈向下增长并检查冲突；真实系统分配器与虚拟地址布局更复杂。", "先 push 10 再 push 20，第一次 pop 得到 20。", "SP；push；pop；malloc；free", "memory", "先入栈 10、20，再出栈一次得到什么？", "20", "10", "30"),
    ("cpu_network", "CPU 与网络接口协作", "网络发送需要应用、CPU、内核、内存和网卡等部件协作。", "教学 SEND 触发系统调用、缓冲区和 DMA 事件，再交给虚拟网络；这些事件不操作真实网卡。", "汇编写入 Hi 后用 SEND 10,2 可观察每层消息去向。", "syscall；socket buffer；DMA；packet", "integrated", "教学 CPU 的 SEND 是否会自动向真实公网发送？", "不会，只发给虚拟模型", "会扫描全部公网", "会修改本机路由"),
])

_group("操作系统", ["https://pages.cs.wisc.edu/~remzi/OSTEP/", "https://docs.python.org/3/library/asyncio.html", "https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html"], [
    ("process_thread", "进程与线程", "进程通常拥有独立资源与地址空间，线程在进程内共享部分资源并独立调度。", "共享数据需要同步；不同系统的实现细节不能由基础教学模型推断。", "多线程服务器可以在同一进程中处理多个连接。", "PID；TID；address space；shared data", "os", "同一进程的线程是否可能访问共享数据？", "可能", "绝不可能", "只有 UDP 线程可以"),
    ("process_state", "进程状态转换", "进程可以处于新建、就绪、运行、阻塞和结束等教学状态。", "等待 I/O 进入阻塞，I/O 完成回就绪，调度器选择就绪进程运行。", "服务器等待 Socket 输入时可阻塞，数据到达后被唤醒。", "new；ready；running；blocked；terminated", "os", "阻塞进程的 I/O 完成后通常先进入什么状态？", "就绪", "永远结束", "自动占用所有 CPU"),
    ("scheduling", "FCFS、SJF 与轮转调度", "FCFS 按到达次序，SJF 按下一 CPU 段长度，RR 按时间片轮转。", "不同算法影响等待与响应；SJF 需要已知或估计执行量，教学模型使用已给定时长。", "RR 能让多个客户端轮流获得 CPU 时间。", "arrival；burst；quantum；waiting；turnaround", "os", "RR 的时间片用完但任务没结束时通常怎样？", "回到就绪队列等待", "删除进程", "永久占有 CPU"),
    ("user_kernel", "用户态与内核态", "处理器权限机制限制应用直接执行受保护的系统操作。", "系统调用通过受控入口进入内核处理，再返回用户程序；教学事件只表示这种过程。", "普通应用调用 send，由内核管理 Socket 和设备。", "privilege level；kernel entry", "os", "普通应用为何不能任意直接操作所有硬件？", "权限与资源管理约束", "因为没有域名", "因为 IPv4 只有 32 位"),
    ("syscall", "系统调用", "系统调用是应用请求操作系统服务的受控接口。", "内核验证参数、管理资源并返回结果；应用仍需处理失败、短读和超时。", "recv 请求读取数据，可能返回部分数据或连接结束。", "send；recv；return value；errno", "integrated", "系统调用参数是否需要验证？", "需要", "不需要", "只验证中文字符"),
    ("paging", "分页与地址转换", "分页把虚拟地址空间分为页，并将页映射到物理页框。", "地址由页号和页内偏移组成，页表与 TLB 帮助转换；页不存在时可触发缺页处理。", "4 KiB 页内偏移需要 12 位。", "virtual page；frame；offset；page table；TLB", "memory", "4 KiB 页内偏移需要多少位？", "12 位", "4 位", "32 位固定不变"),
    ("virtual_memory", "虚拟内存", "虚拟内存为进程提供受管理的地址视图，而非所有地址都同时驻留物理内存。", "映射、权限和按需装入共同参与访问；实际系统还包含共享映射和文件映射。", "访问尚未驻留的合法页可触发缺页并装入数据。", "mapping；protection；resident page", "memory", "虚拟地址是否必须等于物理地址？", "不必须", "必须", "由 TCP 序列号决定"),
    ("page_replacement", "页面置换", "页框不足时，系统选择驻留页让位给需要装入的页。", "FIFO、LRU 和 OPT 使用不同准则；OPT 需要未来访问序列，只作为理论比较。", "同一引用序列可在不同页框数下产生不同缺页次数。", "page fault；resident frames；FIFO；LRU；OPT", "memory", "OPT 为何难以作为通用实际策略？", "需要知道未来访问", "无法比较页号", "必须使用 IPv6"),
    ("interrupt", "中断与轮询", "中断由事件通知 CPU，轮询由 CPU 主动检查状态。", "批量和负载影响开销；实际驱动可能混合使用中断与轮询，不能认为一种方式永远更快。", "高包率下批量处理可减少逐包通知开销。", "interrupt；poll；batch；CPU cycles", "performance", "中断与轮询能否只凭名称判断性能高低？", "不能，需要负载与实现条件", "能", "轮询永远没有 CPU 开销"),
    ("dma", "DMA", "DMA 让设备按配置在内存和设备之间传输数据，减少 CPU 逐字节搬运。", "CPU 和驱动仍需设置描述符、管理缓冲区并处理完成；真实硬件还有一致性及 IOMMU 等约束。", "网卡从发送缓冲区读数据，再通知完成。", "descriptor；buffer；completion；IOMMU", "integrated", "DMA 是否表示 CPU 完全无需参与网络发送？", "不是，仍需配置与处理", "是", "只用于 DNS"),
    ("socket_buffer", "Socket 缓冲区", "Socket 缓冲区在应用和协议处理之间暂存数据。", "发送端不足可造成阻塞或暂时不可写，接收端来不及读取可能触发流控或数据丢弃，取决于协议。", "UDP 接收过慢时，队列已满的数据报可能丢弃。", "send buffer；receive buffer；backpressure", "performance", "无限增大缓冲区是否无条件降低延迟？", "不是，排队也可能增加延迟", "是", "等于增加物理带宽"),
    ("async_io", "异步 I/O", "异步 I/O 让程序等待 I/O 时可以处理其他任务。", "事件循环协调任务，阻塞计算仍可能卡住循环；异步接口不自动取消超时和资源管理需求。", "服务器等待一个客户端时仍可响应另一客户端。", "event loop；task；await；cancellation", "programming", "在事件循环内做很久的阻塞计算会怎样？", "可能阻碍其他任务响应", "一定自动并行到无限 CPU", "只影响 DNS TTL"),
    ("network_cpu_cost", "吞吐量与 CPU 工作量", "吞吐量同时受网络容量和主机处理能力等因素限制。", "固定载荷下，小包增大逐包开销比例；缓冲和批量策略可改变排队、通知与 CPU 周期。", "同样 1 MiB 数据用 64 字节块比用 1024 字节块需要更多包处理次数。", "packet size；pps；CPU cycles；goodput", "performance", "固定总字节数时，小包通常增加哪一项？", "包处理次数", "IPv4 地址位数", "证书公钥长度"),
])

# Select concrete nearby concepts; every link points to a lesson in this catalog.
_links = {
    "osi": ["tcpip", "encapsulation", "addressing"],
    "tcpip": ["osi", "encapsulation", "socket"],
    "encapsulation": ["frame", "ipv4_header", "seq_ack"],
    "ipv4": ["cidr", "arp", "nat"], "ipv6": ["ndp", "slaac", "ipv6_header"],
    "cidr": ["vlsm", "lpm", "aggregation"], "vlsm": ["cidr", "aggregation"],
    "arp": ["arp_cache", "mac_learning", "ndp"], "ndp": ["ipv6", "slaac", "arp"],
    "dhcp": ["lease", "arp", "default_route"],
    "vlan": ["access", "trunk", "inter_vlan"], "stp": ["switch_forward", "convergence"],
    "lpm": ["static_route", "default_route", "aggregation"],
    "rip": ["ospf", "convergence", "ttl"], "ospf": ["rip", "bgp", "convergence"],
    "nat": ["pat", "cgnat", "nat_traversal"],
    "tcp_handshake": ["tcp_state", "seq_ack", "quic"], "tcp_close": ["tcp_state", "reset"],
    "rto": ["retransmit", "latency", "fast_retransmit"],
    "flow_control": ["socket_buffer", "cwnd", "sliding_window"],
    "quic": ["quic_stream", "tls13", "http3"],
    "dns": ["dns_recursive", "dns_hierarchy", "dns_cache"],
    "doh": ["dot", "dnssec", "tls13"], "http2": ["http11", "http3", "quic_stream"],
    "tls13": ["tls_handshake", "certificate", "cert_chain"],
    "vpn": ["wireguard", "split_tunnel", "mtu"],
    "p2p": ["stun", "turn", "nat_traversal"],
    "prediction": ["interpolation", "latency", "client_server"],
    "pcap": ["packet_fields", "hex", "capture_scope"],
    "diagnostic_order": ["adapters", "dns_failure", "tcp_probe"],
    "socket": ["tcp_server", "udp_server", "syscall"],
    "cpu": ["register_memory", "fetch_decode", "cpu_network"],
    "cpu_network": ["syscall", "dma", "socket_buffer"],
    "cache": ["cache_mapping", "cache_replace", "virtual_memory"],
    "paging": ["virtual_memory", "page_replacement", "cache"],
    "dma": ["interrupt", "cpu_network", "network_cpu_cost"],
    "network_cpu_cost": ["socket_buffer", "bandwidth", "interrupt"],
}
for _topic in TOPICS:
    _topic["related"] = _links.get(_topic["id"], [item["id"] for item in TOPICS
                                               if item["category"] == _topic["category"] and item["id"] != _topic["id"]][:3])

# References are kept close to each subject so the UI reading links are relevant.
_specific_sources = {
    "wifi4": ["https://www.intel.com/content/dam/www/central-libraries/us/en/documents/2022-06/wi-fi-tutorial-long.pdf"],
    "wifi6": ["https://www.intel.com/content/www/us/en/products/details/wireless/wi-fi-6-series.html", "https://www.intel.com/content/www/us/en/products/docs/wireless/2-4-vs-5ghz.html"],
    "wifi7": ["https://www.intel.com/content/www/us/en/products/details/wireless/wi-fi-7-series.html"],
    "vlan": ["https://standards.ieee.org/ieee/802.1Q/10323/"],
    "dot1q": ["https://standards.ieee.org/ieee/802.1Q/10323/"],
    "access": ["https://standards.ieee.org/ieee/802.1Q/10323/"],
    "trunk": ["https://standards.ieee.org/ieee/802.1Q/10323/"],
    "stp": ["https://standards.ieee.org/ieee/802.1Q/10323/"],
    "bgp": ["https://www.rfc-editor.org/info/rfc4271"],
    "rip": ["https://www.rfc-editor.org/info/rfc2453"],
    "cgnat": ["https://www.rfc-editor.org/info/rfc6598"],
    "rto": ["https://www.rfc-editor.org/info/rfc6298"],
    "doh": ["https://www.rfc-editor.org/info/rfc8484"],
    "dot": ["https://www.rfc-editor.org/info/rfc7858"],
    "dnssec": ["https://www.rfc-editor.org/info/rfc4033"],
    "websocket": ["https://www.rfc-editor.org/info/rfc6455"],
    "firewall": ["https://learn.microsoft.com/en-us/powershell/module/netsecurity/get-netfirewallrule"],
    "c_socket": ["https://learn.microsoft.com/en-us/windows/win32/winsock/initializing-winsock"],
    "ieee754": ["https://standards.ieee.org/ieee/754/6210/"],
    "minecraft": ["https://www.minecraft.net/en-us/download/server", "https://www.minecraft.net/en-us/download/server/bedrock"],
}
for _topic in TOPICS:
    if _topic["id"] in _specific_sources:
        _topic["sources"] = _specific_sources[_topic["id"]]

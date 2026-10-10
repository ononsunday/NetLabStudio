# 依赖、驱动与参考资料

版本取自本项目 `.venv` 的已安装包元数据，核对时间为 2026-10-04。它们是本次环境的版本，不表示各项目的最新版本。完整锁定清单见项目根目录 `requirements-lock.txt`，兼容安装范围见 `requirements.txt`。

## 已核对的运行环境

| 项目 | 当前版本/环境 | 用途与来源 |
|---|---|---|
| Python | 3.13.14，64 位 AMD64 | 源码运行环境；[Python Windows 下载](https://www.python.org/downloads/windows/)、[Python 3.13 许可证](https://docs.python.org/3.13/license.html) |
| 操作系统 | Windows 11，系统报告 10.0.26200 | 当前开发/验证环境；其他系统版本的结果见验证文档 |
| SQLite | 3.50.4 | Python `sqlite3` 的本地存储；[SQLite 版权说明](https://sqlite.org/copyright.html) |
| Python SSL | OpenSSL 3.0.21 | Python TLS 功能；[OpenSSL 许可证](https://openssl-library.org/source/license/index.html) |

SQLite 为公有领域项目。Python 使用 PSF 许可及随附第三方声明，OpenSSL 3 使用 Apache-2.0；这些运行库的第三方组成以各自发行包的声明为准。cryptography 自身使用的加密运行库不应仅根据 Python `ssl.OPENSSL_VERSION` 推断。

## 直接依赖与重要运行依赖

许可证名称来自安装包的 `License-Expression`、`License` 或随附许可证文件。`OR` 表示发行方提供的许可选择，不能理解为程序已完成某种商业授权。

| 包 | 已安装版本 | 许可标识 | 用途/官方资料 |
|---|---|---|---|
| PySide6、PySide6 Essentials/Addons、shiboken6 | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only（元数据）；另有 Qt 商业授权路径 | 原生 Qt Widgets、Graphics View；[Qt for Python](https://doc.qt.io/qtforpython-6/)、[许可证说明](https://doc.qt.io/qtforpython-6/licenses.html) |
| psutil | 7.2.2 | BSD-3-Clause | 适配器、接口计数、进程/连接；[项目文档](https://psutil.readthedocs.io/) |
| Scapy | 2.8.0 | GPL-2.0-only | PCAP/PCAPNG、协议解析和虚拟字节编码；[Scapy 文档](https://scapy.readthedocs.io/) |
| dnspython | 2.8.0 | ISC | DNS、DoH、DoT；[官方文档](https://dnspython.readthedocs.io/) |
| httpx | 0.28.1 | BSD-3-Clause | 实际 HTTP/HTTPS 客户端；[官方文档](https://www.python-httpx.org/) |
| httpcore | 1.0.9 | BSD-3-Clause | HTTP 连接与有界传输；[官方文档](https://www.encode.io/httpcore/) |
| h2 | 4.4.1 | MIT | HTTP/2 协议状态与本地 HTTP/2 服务；[官方项目](https://github.com/python-hyper/h2) |
| aioquic | 1.3.0 | BSD-3-Clause | 实际 QUIC/HTTP3 客户端和回环服务；[官方文档](https://aioquic.readthedocs.io/) |
| pylsqpack | 0.3.24 | BSD-3-Clause | aioquic 使用的 QPACK 库；[官方项目](https://github.com/aiortc/pylsqpack) |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | 证书、密钥交换、认证加密、签名；[官方文档](https://cryptography.io/) |
| pyOpenSSL | 26.4.0 | Apache-2.0 | TLS 相关间接依赖；[官方文档](https://www.pyopenssl.org/) |
| service-identity | 26.1.0 | MIT | TLS 身份验证相关间接依赖；[官方文档](https://service-identity.readthedocs.io/) |
| websockets | 17.2 | BSD-3-Clause | 实际 WebSocket 回显；[官方文档](https://websockets.readthedocs.io/) |
| AsyncSSH | 2.24.1 | EPL-2.0 OR GPL-2.0-or-later | SSH 密钥交换与可信回环教学命令；[官方文档](https://asyncssh.readthedocs.io/) |
| certifi | 2026.7.22 | MPL-2.0 | HTTP 客户端所用证书根文件；[官方项目](https://github.com/certifi/python-certifi) |
| pytest | 9.1.1 | MIT | 自动化测试；[官方文档](https://docs.pytest.org/) |
| PyInstaller | 6.22.3 | GPL-2.0-or-later，附构建/分发例外 | Windows 便携包；[许可证与例外](https://pyinstaller.org/en/stable/license.html) |
| pyinstaller-hooks-contrib | 2026.8 | 常规 hooks：GPL-2.0-or-later；运行时 hooks：Apache-2.0 | 构建钩子；[官方项目](https://github.com/pyinstaller/pyinstaller-hooks-contrib) |

`pytest`、PyInstaller 和构建钩子用于开发/构建，并非用户启动应用的前提。打包结果需要保留整个生成目录，Qt DLL、插件、协议库和证书根文件不能只用一个 EXE 替代。

## 其余锁定包

以下也是本次安装环境的一部分。安装工具的包不一定进入最终 EXE，实际打包清单由 PyInstaller 分析结果决定。

| 包 | 版本 | 许可标识 |
|---|---|---|
| altgraph | 0.17.5 | MIT |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| cffi | 2.1.1 | MIT-0 |
| colorama | 0.4.6 | BSD-3-Clause（随附 LICENSE.txt） |
| h11 | 0.16.0 | MIT |
| hpack | 4.2.0 | MIT |
| hyperframe | 6.1.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.0 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pefile | 2024.8.26 | MIT |
| pluggy | 1.6.0 | MIT |
| pycparser | 3.0 | BSD-3-Clause |
| Pygments | 2.21.0 | BSD-2-Clause |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause |
| setuptools | 84.0.0 | MIT（其内置第三方包另有声明） |
| typing_extensions | 4.16.0 | PSF-2.0 |
| pip | 26.1.2 | MIT（安装工具，不在 requirements-lock.txt 中固定） |

本表用于识别依赖，不能替代许可证原文。本地包随附的许可文本已复制到 [许可证目录与清单](licenses/README.md)，文件来源、长度和 SHA-256 保存在 `licenses/manifest.json`。文本通常来自 `.venv\Lib\site-packages\<包名>-<版本>.dist-info\licenses` 或该目录的 `LICENSE/COPYING` 文件。当前安装的 PySide6 四个包只附有商业许可引用，因此另外从 Qt 官方 `v6.11.2` 源码补入 LGPL/GPL、许可例外和 Qt Base 第三方许可/归属说明；这些补充文件在清单中单独标为官方网络来源。

Qt 本身还包含其他第三方组件，参见 [Qt 第三方许可入口](https://doc.qt.io/qt-6/licenses-used-in-qt.html)。本次仅进行本地构建和验证，没有公开上传，也没有声称已经完成面向公众的整体许可兼容性审查、商业 Qt 授权或代码签名。未来公开重分发仍需用户审核实际打包组件，保留版权/许可证并完成相应许可要求；不能因为 PyInstaller 有分发例外，就忽略 Scapy、Qt 或 AsyncSSH 的独立许可。

## 可选驱动、权限与编译器

| 组件/条件 | 何时需要 | 当前情况与使用方法 |
|---|---|---|
| Npcap | Windows 实时抓包 | 当前电脑未安装；离线 PCAP 和教学模拟可正常使用。从 [Npcap 官方站点](https://npcap.com/)自行安装，完成后在抓包页检查接口与权限 |
| 抓包权限 | Npcap 配置为 Admin-only，或系统限制驱动访问时 | 应用普通启动不要求管理员；驱动能否被账户使用需实际抓包确认，参见 [Npcap 参考指南](https://npcap.com/guide/index.html) |
| Windows WLAN、PowerShell NetTCPIP/NetSecurity | Wi-Fi、网关/DNS、路由与防火墙只读采集 | 服务、隐私设置、模块或访问策略可能使部分字段不可用，应用保留错误/原始返回，不修改安全设置 |
| 外部 Python | 从源码启动，或需要安装额外的 Python 包时 | 便携版的内置示例由随包练习子进程运行；源码版用自己的 `.venv`。推荐 Python 3.12/3.13 |
| GCC 或 Clang | C Socket 示例编译与执行 | 当前发现路径 `C:\Tools\w64devkit\bin\gcc.exe`；安装 [w64devkit](https://github.com/skeeto/w64devkit)、[MSYS2](https://www.msys2.org/) 或 [LLVM](https://llvm.org/) 并配置 PATH。Windows 示例链接 `ws2_32`，不需要 C 扩展来启动应用 |
| 明确授权的服务器、网络路径、证书 | 外部 DNS/TCP/HTTPS/HTTP3/SSH/STUN 检查 | 本地回环测试不需要外网；外部失败可能来自目标、路由、UDP 限制、DNS 或证书，不用成功示例替代 |

Npcap 不随本项目打包或自动安装。它有单独的许可与重分发条件，不能作为普通开源 Python 包直接附带；详见 [Npcap 许可说明](https://npcap.com/guide/index.html#npcap-license)。本地临时 HTTPS/DoT/HTTP3 证书只用于回环测试，不安装到 Windows 根证书库。

## 协议与系统资料

下表是实现和课程的核对入口。引用规范并不表示教学模型实现了规范的全部内容。每个课程条目还有自己的 `sources` 链接。

| 主题 | 原始规范或官方资料 |
|---|---|
| IPv4、IPv6、ICMPv6 | [RFC 791](https://www.rfc-editor.org/rfc/rfc791.html)、[RFC 8200](https://www.rfc-editor.org/rfc/rfc8200.html)、[RFC 4443](https://www.rfc-editor.org/rfc/rfc4443.html) |
| ARP、IPv6 邻居发现、DHCP | [RFC 826](https://www.rfc-editor.org/rfc/rfc826.html)、[RFC 4861](https://www.rfc-editor.org/rfc/rfc4861.html)、[RFC 2131](https://www.rfc-editor.org/rfc/rfc2131.html) |
| TCP、拥塞控制、RTO、UDP | [RFC 9293](https://www.rfc-editor.org/rfc/rfc9293.html)、[RFC 5681](https://www.rfc-editor.org/rfc/rfc5681.html)、[RFC 6298](https://www.rfc-editor.org/rfc/rfc6298.html)、[RFC 768](https://www.rfc-editor.org/rfc/rfc768.html) |
| QUIC、QUIC TLS、HTTP/3 | [RFC 9000](https://www.rfc-editor.org/rfc/rfc9000.html)、[RFC 9001](https://www.rfc-editor.org/rfc/rfc9001.html)、[RFC 9002](https://www.rfc-editor.org/rfc/rfc9002.html)、[RFC 9114](https://www.rfc-editor.org/rfc/rfc9114.html) |
| HTTP、HTTP/2、TLS 1.3、WebSocket | [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)、[RFC 9113](https://www.rfc-editor.org/rfc/rfc9113.html)、[RFC 8446](https://www.rfc-editor.org/rfc/rfc8446.html)、[RFC 6455](https://www.rfc-editor.org/rfc/rfc6455.html) |
| DNS、DoH、DoT、DNSSEC | [RFC 1034](https://www.rfc-editor.org/rfc/rfc1034.html)、[RFC 1035](https://www.rfc-editor.org/rfc/rfc1035.html)、[RFC 8484](https://www.rfc-editor.org/rfc/rfc8484.html)、[RFC 7858](https://www.rfc-editor.org/rfc/rfc7858.html)、[RFC 4033](https://www.rfc-editor.org/rfc/rfc4033.html) |
| RIP、OSPF、BGP | [RFC 2453](https://www.rfc-editor.org/rfc/rfc2453.html)、[RFC 2328](https://www.rfc-editor.org/rfc/rfc2328.html)、[RFC 4271](https://www.rfc-editor.org/rfc/rfc4271.html) |
| NAT 行为、STUN、TURN | [RFC 4787](https://www.rfc-editor.org/rfc/rfc4787.html)、[RFC 8489](https://www.rfc-editor.org/rfc/rfc8489.html)、[RFC 8656](https://www.rfc-editor.org/rfc/rfc8656.html) |
| WireGuard 与 SSH | [WireGuard 协议说明](https://www.wireguard.com/protocol/)、[RFC 4251](https://www.rfc-editor.org/rfc/rfc4251.html) |
| 以太网、桥接/VLAN、Wi-Fi | [IEEE 802.3](https://www.ieee802.org/3/)、[IEEE 802.1](https://1.ieee802.org/)、[IEEE 802.11](https://www.ieee802.org/11/) |
| Python Socket、SSL 与异步 I/O | [socket](https://docs.python.org/3.13/library/socket.html)、[ssl](https://docs.python.org/3.13/library/ssl.html)、[asyncio](https://docs.python.org/3.13/library/asyncio.html) |
| Windows 网络系统工具 | [Get-NetIPConfiguration](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-netipconfiguration)、[Get-NetRoute](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-netroute)、[Get-NetFirewallRule](https://learn.microsoft.com/en-us/powershell/module/netsecurity/get-netfirewallrule)、[netsh wlan](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netsh-wlan) |
| CPU、内存、调度与分页 | [Intel 软件开发手册](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html)、[OSTEP 作者教材](https://pages.cs.wisc.edu/~remzi/OSTEP/) |

协议课程用短例子解释原理，CPU/Cache/OS 使用自定义教学模型。示例拓扑中的 `203.0.113.0/24`、`198.51.100.0/24` 与 `2001:db8::/32` 为文档示例地址；它们不会被当成本机采集结果。


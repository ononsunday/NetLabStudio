# 实际验证记录

验证日期：2026-10-04 至 2026-10-05。以下结果来自本机执行，不表示其他电脑或所有 Windows 版本都已验证。

## 环境与结果

| 检查 | 实际结果 |
|---|---|
| Windows | Windows 11，系统版本 10.0.26200，64 位；当前进程没有提升到管理员权限 |
| Python / Qt | Python 3.13.14、PySide6 6.11.2；具体依赖见锁定文件 |
| 完整自动化测试 | **237 passed，0 failed，0 skipped；71.33 秒** |
| 原生窗口 | 源码与打包 EXE 均实际启动、显示并正常关闭 |
| EXE 本地验证 | **16/16 通过，2.94 秒；进程退出码 0** |
| EXE 内置 Python 示例 | **11/11 实际执行并检查通信输出，3.06 秒；没有使用外部解释器** |
| 便携 ZIP 独立解压 | 在另一个目录、不同工作目录启动，**16/16 检查和 11/11 Python 示例通过**；临时解压目录已清理 |
| 驱动缺失处理 | 本机没有 Npcap；支持检测返回不可用，离线 PCAP 与教学实验仍运行 |
| 打包 | PyInstaller 6.22.3 已生成 `dist/NetLabStudio/NetLabStudio.exe` 及完整依赖目录 |

测试报告为 [JUnit XML](validation/test-results.xml)。[EXE 验证 JSON](validation/exe-verification.json)、[内置示例执行记录](validation/bundled-examples.json) 和 [独立解压验证](validation/portable-verification.json) 保留实际结果、输出、来源和耗时。验证不会把失败改写成成功，也没有通过访问外网来填充结果。

## 自动化测试覆盖

237 项中，网络核心 66 项，系统/课程/存储 77 项，真实服务、练习运行器和启动验证 74 项，原生 Qt 交互 20 项。

网络测试检查 IPv4/IPv6、地址与参数校验、VLSM、ARP/邻居发现、MAC 学习、VLAN/Trunk、DHCP 到达条件、NAT/PAT、静态路由与最长前缀、动态路由及链路故障、TCP 状态/窗口/重传、UDP/QUIC 模型，以及确定性队列和快照恢复。

系统与数据测试检查 CPU 指令、分支、越界和运行上限、Cache FIFO/LRU、堆栈、进程/IO 调度、分页、缓冲区背压，以及 SQLite 初始化、迁移、事务导入、重开恢复、脱敏、报告和课程关联。

服务测试使用本机客户端和服务器进行真实通信，包含超时、断开、取消、总时限、失败证据、TLS 证书验证、HTTP/2 多帧正文、加密与篡改、Python 示例运行、C TCP/UDP 编译通信，以及 Windows 子进程后代终止。PCAP 测试还启动全新的 Python 进程，仅导入文件解析模块，验证第一份文件能正确识别以太网和 TCP，而不是依赖前面测试已经注册的协议。

Qt 测试实际创建窗口并操作控件，覆盖全部 19 个工作区、主题、搜索、练习保存、协议参数、模板恢复、DF 复选框、电路文字/拖动、CPU 修改后运行、DHCP 配置同步、运行中故障、虚拟帧过滤/时序、本地 HTTPS，以及 B/E/F 综合实验。局部协议状态使用事件点，不画成发送到其他设备的数据包。

## EXE 的 16 项检查

| 类型 | 检查内容 |
|---|---|
| 真实回环通信，11 项 | TCP、UDP、HTTPS/TLS 1.3 与本地可信 CA、HTTP/2、HTTP/3、WebSocket、SSH 固定主机密钥、DNS、DoH、DoT、STUN |
| 合成文件，1 项 | 已明确标注的 PCAP 字节、TCP SEQ/ACK 与载荷长度；没有发送这些帧 |
| 教学模型，2 项 | 子网、ARP/交换和事件快照；CPU 指令执行与快照 |
| 本地存储，1 项 | 临时 SQLite 迁移、保存、关闭、重新读取 |
| 内置 Python 子进程，1 项 | 用打包 EXE 执行可编辑的 TCP 回显示例，检查实际收到的中文文本；不用外部 Python |

每个服务只绑定 `127.0.0.1`。测试使用的证书、PCAP 和数据库放在独立临时目录；验证结果确认所有服务已关闭、临时文件已删除。已有应用数据不用于这组验证。另一次检查逐个运行全部 11 个 Python 示例，验证 TCP、UDP、asyncio、select、文件哈希、HTTP、线程服务、缓冲区、超时、聊天室和 WebSocket 的实际输出。完整 pytest 还实际编译并运行了 C TCP/UDP 两个示例。

可以自行复验：

```powershell
# 源码完整测试
.\.venv\Scripts\python.exe -m pytest -q

# EXE 验证；完成后写 JSON 并关闭窗口
.\dist\NetLabStudio\NetLabStudio.exe --verify qa\check.json --data-dir qa\check-data

# 用 EXE 逐个执行内置 Python 示例
.\.venv\Scripts\python.exe scripts\verify_bundled_examples.py
```

`--verify` 执行应用自己的检查函数，不能代替完整 pytest。它保留失败和跳过结果，失败时返回非零退出码。源码版本执行 15 项；冻结 EXE 增加内置练习子进程检查，共 16 项。

## 视觉与本机信息检查

已查看原生窗口截图：工作台、拓扑、TCP 时序、CPU 寄存器、全加器，以及浅色主题和 1100×720 窗口。电路文字和连线实际显示；小窗口自动收起知识面板，复杂工作区使用滚动区域，结果仍可访问。截图来自 QWidget 渲染，未制作静态界面替代软件。

已实际读取本机适配器、路由、防火墙规则及 Wi-Fi 驱动提供的信息，结果未被复制进示例拓扑或抓包文件。未报告的硬件字段保持不可用。没有执行系统配置修改。

## 打包中修复的问题

初次 EXE 启动发现环境 PATH 中 Poppler 的 ICU 库被误收，导出函数与 Qt 所需的 Windows ICU 不匹配。打包配置排除了这组库，使用系统 ICU，未复制 Windows 系统 DLL。另一个打包问题是 dnspython 的 DoH 检查需要 httpcore/h2 的版本元数据；已在配置中加入这些元数据。编程实验改用随包运行的独立子进程，避免选到 Windows 的 Python 商店别名。最终 EXE 的 16 项验证及全部 Python 示例检查在重新构建后通过。

便携目录需要完整保留 `_internal`。依赖许可证副本随 `docs/licenses` 提供；可执行文件未签名，没有安装向导或自动更新器。

## 尚未验证与未实现的范围

尚未验证：安装 Npcap 后的真实网卡抓包、需要提升权限的捕获环境、Wi-Fi 6E/7 各类硬件、跨家庭公网 NAT/IPv6、外部 HTTP3/SSH 服务、其他电脑及 Windows 10 的完整部署。没有为了验收而扫描公网或修改本机网络设置。

尚未实现的协议细节包括完整 STP/BPDU、OSPF 邻接/LSA/多区域、BGP 商业策略与实际会话、拓扑中的 IP 分片重组、完整生产 TCP/QUIC 协议栈、真实 TURN 中继服务、商业 VPN/WireGuard 服务与完整真实硬件 CPU/OS。对应教学算法、状态与部分真实协议库实验已实现；逐模块边界见 [功能及限制](FEATURES.md)。这些限制来自模型范围、驱动缺失或缺少可验证的外部环境，不能作为已完成的生产功能。

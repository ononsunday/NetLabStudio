# 教学抓包与实验结果示例

`teaching.pcap` 是生成脚本在内存中构造的 15 个教学以太网帧，包含 ARP 请求与响应、DNS 查询与应答、TCP 三次握手、HTTP 请求与响应以及 TCP 关闭。文件没有来自本机网卡的实测数据，生成过程不会发送数据包。

示例使用文档地址 192.0.2.0/24、198.51.100.0/24 和 203.0.113.0/24、局部管理 MAC 地址，以及域名 `example.test`。HTTP 正文是 `Hello NetLab!`。这些地址、名称和内容均由脚本指定。

PCAP 时间从 Unix 时间戳 `1700000000.000000` 开始。此值只是固定的示例起点，不代表实际抓包日期；帧间时间也由脚本指定，不能用来评估真实网络性能。以太网帧补齐到至少 60 字节，不包含网卡生成的 FCS。示例省略了完整路由与 DNS 服务器地址发现过程。

在抓包分析页面选择导入 PCAP，可以查看字段、原始字节、协议过滤与 TCP 时序。HTTPS 未出现在此文件中。

相邻的 `../experiments/tcp_loss.json` 和 `../experiments/cpu_network.json` 由应用的独立教学核心实际计算，均含 `source: teaching_simulation`、完整输入配置和原始计算结果。TCP 示例使用 10% 丢包率和固定随机种子 4。CPU 示例执行汇编指令，把 `Hi` 经虚拟 UDP、ARP、交换、路由和 NAT 发送到虚拟服务端，再将回显写入教学 CPU 的接收内存。JSON 事件时间以模拟秒表示，从 0 开始；CPU 周期、延迟和链路参数属于教学模型。

在项目根目录运行下面的命令，可重新生成这些文件。脚本只更新这份说明、指定 PCAP 和上述两份 JSON。

```powershell
.\.venv\Scripts\python.exe scripts\generate_examples.py
```

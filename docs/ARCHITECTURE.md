# 架构

应用使用原生 PySide6 Qt Widgets。Qt Graphics View 绘制拓扑、电路与时序，QPainter 绘制数据曲线和玩家位置。没有浏览器外壳，也没有云端数据服务。

```text
netlab/app.py               启动、参数、本地目录、滚动日志
netlab/ui/                 窗口、页面、Graphics View、Worker、结果展示
netlab/core/events.py       确定性事件调度与随机状态快照
netlab/core/topology.py     设备、接口、链路、包、交换/路由状态
netlab/core/transport.py    TCP/UDP/QUIC 教学状态机
netlab/core/routing.py      前缀、最短路径、BGP、分片/PMTU
netlab/core/services.py     DHCP、NAT、DNS、虚拟防火墙与 Wi-Fi
netlab/core/experiments.py  网站、家庭网络、游戏、故障和性能
netlab/services/           本机只读采集、真实通信、抓包、代码子进程
netlab/systems/            CPU、逻辑、Cache、调度/内存、网络 I/O 联动
netlab/content/            中文课程、练习、关联和综合指导
netlab/storage.py          SQLite 迁移、事务、导入导出、报告、脱敏
tests/                     核心、服务、数据、原生窗口测试
examples/                  标注为示例的拓扑与可运行回环源码
```

## 模拟事件与数据

`EventEngine` 使用堆按模拟时间及插入序号排序。事件包含 `id`、`time`、`kind`、`source`、`target`、`packet_id`、`status`、`explanation` 和 `data`。随机数由独立种子控制，快照保存队列、历史、随机状态、包、邻居表、DHCP/NAT 表及链路队列状态。

`Topology` 中设备拥有接口与路由，链路连接明确端口。包保留地址、端口、TTL/Hop Limit、当前位置、状态及当前封装。交换机学习、邻居解析、最长前缀匹配与重传都在核心逻辑中计算，界面只渲染输出。单步会消费一个事件，播放调用相同的单步逻辑。

系统模拟使用相同的事件字段。CPU 网络综合实验逐条执行汇编，在 `SEND` 后让消息穿过共享拓扑。只有真正到达虚拟服务端的请求才会生成回显；反向 NAT 和客户端接收成功后才会更新 CPU 接收队列与内存。事件 ID 和包 ID 在合并时保持唯一。

新增协议可以扩展独立模型与服务接口，向页面返回可序列化状态和事件。真实网络模型不复用模拟发送方法；模拟编码调用 Scapy 的字节序列化功能，未调用 `send`、`sendp` 或真实 Socket。

## 后台与关闭

真实网络与代码运行通过 `QRunnable`/`QThreadPool` 执行，结果信号回到 GUI 线程。应用同时最多接纳三个后台任务，同一页面执行期间禁用操作按钮，运行参数复制后再交给 Worker。计数采样和事件播放使用 Qt Timer。

真实服务限定单个明确目标，本地服务只绑定回环地址。Socket、TLS、子进程和复合探测有超时或总时限。关闭应用时停止动画、发出诊断取消信号、等待运行任务退出，再停止服务器、关闭 Socket 和数据库。代码子进程在 Windows 使用 Job Object 管理后代；它不提供文件系统隔离。

## SQLite

数据库使用 `PRAGMA user_version` 迁移，目前结构版本 2，使用 WAL、外键、事务和 `synchronous=FULL`。导入先校验格式，再在事务中写入；错误导入不会留下部分记录。备份包含格式/版本，ID 去重，能够保存与恢复设置、实验、拓扑、进度、笔记、错题和模板。

分享导出在副本上脱敏，不改动数据库中的原始结果。它不保证识别任意自由文本或编码后的载荷，因此导出前仍须由用户检查。

## 观测边界

真实服务使用 `kind='measured'` 或 `data_kind='measured'`。模拟使用 `mode='teaching_simulation'`、`teaching_model=True` 等明确来源标记。接口速率是实测计数差推导，游戏预测误差是模拟位置计算，课程示例没有本机观测身份。关键模型返回限制说明，其余范围在功能文档中说明。


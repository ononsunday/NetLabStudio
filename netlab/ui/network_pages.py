import json
import time
from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QFormLayout,QTabWidget,QComboBox,QSpinBox,QDoubleSpinBox,QPlainTextEdit,QSplitter,QFileDialog,QCheckBox,QTextBrowser,QInputDialog)
from .common import Page,DataView,Table,button,label,row,line,dumps
from .visuals import Timeline,LineChart,GameArena

def spin(value,lo=1,hi=1000000):
    w=QSpinBox(); w.setRange(lo,hi); w.setValue(value); return w

def decimal(value,lo=0,hi=1000,step=1):
    w=QDoubleSpinBox(); w.setRange(lo,hi); w.setDecimals(3); w.setSingleStep(step); w.setValue(value); return w

def combo(values):
    w=QComboBox(); w.addItems(values); return w

def tabs(*pairs):
    w=QTabWidget()
    for name,child in pairs: w.addTab(child,name)
    return w

def form(fields):
    w=QWidget(); l=QFormLayout(w)
    for name,control in fields: l.addRow(name,control)
    return w

class ObservePage(Page):
    def __init__(self,window):
        super().__init__(window,'本机网络观察','网卡、连接、Wi-Fi 和路由来自 Windows 当前状态。读取不到的字段显示不可用。','本机实测')
        self.adapters=Table(['适配器','状态','IPv4','IPv6','MAC','Mbps','发送字节','接收字节','网关','DNS'])
        self.connections=Table(['协议','本地地址','远端地址','状态','PID','进程'])
        self.output=DataView(); self.chart=LineChart('接口实时速率 / KiB/s'); self.rate=label('速率监控尚未开始','muted')
        self.layout.addWidget(row(button('读取本机状态',self.refresh,True),button('读取防火墙规则',self.firewall),button('开始 / 停止速率监控',self.toggle_rates)))
        self.layout.addWidget(tabs(('适配器',self.adapters),('连接与进程',self.connections),('完整信息 / Wi-Fi / 路由',self.output)),1)
        self.layout.addWidget(self.chart); self.layout.addWidget(self.rate); self.finish()
        self.timer=QTimer(self); self.timer.setInterval(1000); self.timer.timeout.connect(self.sample)
        self.samples=[]; self.sampler=None
    def refresh(self):
        from netlab.services.observe import system_snapshot
        self.config={'operation':'system_snapshot'}
        self.perform(system_snapshot,self.show_snapshot,True)
    def show_snapshot(self,data):
        self.output.set_data(data)
        self.adapters.set_rows([[a.get(k,'不可用') for k in ['name','status','ipv4','ipv6','mac','speed_mbps','sent_bytes','recv_bytes','gateway','dns']] for a in data.get('adapters',[])])
        self.connections.set_rows([[c.get(k,'不可用') for k in ['protocol','local','remote','status','pid','process']] for c in data.get('connections',[])])
    def firewall(self):
        from netlab.services.observe import firewall
        self.config={'operation':'windows_firewall'}
        self.perform(firewall,background=True)
    def toggle_rates(self):
        if self.timer.isActive(): self.timer.stop(); self.status('已停止速率监控'); return
        import psutil
        self.sampler=(time.monotonic(),psutil.net_io_counters()); self.timer.start(); self.status('正在读取本机接口累计计数')
    def sample(self):
        import psutil
        now=time.monotonic(); c=psutil.net_io_counters(); previous,old=self.sampler; elapsed=now-previous
        tx=max(0,c.bytes_sent-old.bytes_sent)/elapsed/1024; rx=max(0,c.bytes_recv-old.bytes_recv)/elapsed/1024
        self.samples=(self.samples+[tx+rx])[-300:]; self.chart.set_series(self.samples); self.rate.setText(f'上行 {tx:.2f} KiB/s    下行 {rx:.2f} KiB/s    根据接口字节计数差计算')
        self.sampler=(now,c)

class SubnetPage(Page):
    def __init__(self,window):
        super().__init__(window,'网络基础与子网','IPv4 / IPv6 地址解析、逐位 AND、VLSM 和地址冲突检查。','本地精确计算')
        self.cidr=line('192.168.10.37/24'); self.hosts=line('60, 30, 12'); self.addresses=line('192.168.1.10/24, 192.168.1.10/24'); self.output=DataView(); self.bits=Table(['步骤','二进制 / 计算过程'])
        self.layout.addWidget(row(self.cidr,button('解析地址',self.calculate,True),button('课程：IP 地址',lambda:window.learn('IPv4'))))
        self.layout.addWidget(row(label('VLSM 主机数'),self.hosts,button('规划子网',self.vlsm)))
        self.layout.addWidget(row(label('冲突检查'),self.addresses,button('检查地址',self.conflicts)))
        self.packet_size=spin(4000,20,65535);self.mtu=spin(1500,68,65535);self.ip_version=combo(['4','6']);self.df=QCheckBox('禁止 IPv4 分片');self.path_mtus=line('1500,1400,1280')
        self.layout.addWidget(row(label('IP 数据报字节'),self.packet_size,label('MTU'),self.mtu,self.ip_version,self.df,button('计算分片',self.fragment)))
        self.layout.addWidget(row(label('路径 MTU 序列'),self.path_mtus,button('路径 MTU 发现',self.path_mtu)))
        self.layout.addWidget(tabs(('结果',self.output),('逐步计算',self.bits)),1); self.finish()
    def calculate(self):
        from netlab.core.subnet import analyze_network
        self.config={'cidr':self.cidr.text()}
        self.perform(lambda:analyze_network(self.cidr.text()),self.show)
    def show(self,data):
        self.output.set_data(data); self.bits.set_rows([[x['label'],x['value']] for x in data['binary_steps']])
    def vlsm(self):
        from netlab.core.subnet import vlsm_plan
        def work():self.config={'base':self.cidr.text(),'hosts':[int(x.strip()) for x in self.hosts.text().split(',')]};return vlsm_plan(**self.config)
        self.perform(work)
    def conflicts(self):
        from netlab.core.subnet import conflicts
        def work():self.config={'addresses':[x.strip() for x in self.addresses.text().split(',')]};return conflicts(**self.config)
        self.perform(work)
    def fragment(self):
        from netlab.core.routing import fragment_datagram
        def work():self.config={'size':self.packet_size.value(),'mtu':self.mtu.value(),'version':int(self.ip_version.currentText()),'df':self.df.isChecked()};return fragment_datagram(**self.config)
        self.perform(work)
    def path_mtu(self):
        from netlab.core.routing import path_mtu_experiment
        def work():self.config={'packet_size':self.packet_size.value(),'mtus':[int(v.strip()) for v in self.path_mtus.text().split(',')],'version':int(self.ip_version.currentText()),'df':self.df.isChecked()};return path_mtu_experiment(**self.config)
        self.perform(work)

class TransportPage(Page):
    def __init__(self,window):
        super().__init__(window,'TCP · UDP · QUIC','修改链路条件，计算握手、发送、丢包恢复与连接关闭事件。所有时间均为模拟时间。')
        self.protocol=combo(['TCP','UDP','QUIC']); self.size=spin(8192,1,2000000); self.loss=decimal(.05,0,1,.01); self.delay=decimal(30,0,10000); self.jitter=decimal(5,0,5000); self.bandwidth=decimal(10,.001,10000); self.window_size=spin(4096,64,1000000); self.seed=spin(1,0,999999)
        f=form([('传输协议',self.protocol),('应用数据 / 字节',self.size),('丢包概率 (0~1)',self.loss),('单向延迟 / ms',self.delay),('抖动 / ms',self.jitter),('链路带宽 / Mbps',self.bandwidth),('接收窗口 / 字节',self.window_size),('随机种子',self.seed)])
        self.output=DataView(); self.timeline=Timeline(); self.chart=LineChart('TCP 拥塞窗口 / 字节')
        left=QWidget(); l=QVBoxLayout(left); l.addWidget(f); l.addWidget(button('运行协议实验',self.simulate,True)); l.addWidget(button('同条件对比三个协议',self.compare)); l.addWidget(label('QUIC 使用教学恢复与流模型；实测 HTTP/3 位于 Web 实验。','muted')); l.addStretch()
        self.control_action=combo(['keepalive','reset']);self.peer_alive=QCheckBox('对端可用 / RST 序列有效');self.peer_alive.setChecked(True);l.addWidget(self.control_action);l.addWidget(self.peer_alive);l.addWidget(button('连接保活 / 复位实验',self.connection_control))
        split=QSplitter(); split.addWidget(left); split.addWidget(tabs(('时序图',self.timeline),('状态与指标',self.output),('窗口曲线',self.chart))); split.setSizes([250,850]); self.layout.addWidget(split,1); self.finish()
    def params(self):
        return dict(bytes_total=self.size.value(),loss=self.loss.value(),delay_ms=self.delay.value(),jitter_ms=self.jitter.value(),bandwidth_mbps=self.bandwidth.value(),receive_window=self.window_size.value(),seed=self.seed.value())
    def simulate(self):
        from netlab.core.transport import simulate_tcp,simulate_udp,simulate_quic
        params=self.params();self.config={**params,'protocol':self.protocol.currentText()}; fn={'TCP':simulate_tcp,'UDP':simulate_udp,'QUIC':simulate_quic}[self.protocol.currentText()]
        self.perform(lambda:fn(**params),self.show,True)
    def show(self,data):
        self.output.set_data(data); self.timeline.set_events(data.get('events',[])); self.timeline.step()
        values=[e['cwnd'] for e in data.get('window_history',[])]
        self.chart.set_series(values)
    def compare(self):
        from netlab.core.transport import simulate_tcp,simulate_udp,simulate_quic
        params=self.params();self.config=params
        self.perform(lambda:{'model':'同条件教学模拟；吞吐量受应用与实现影响','TCP':simulate_tcp(**params),'UDP':simulate_udp(**params),'QUIC':simulate_quic(**params)},background=True)
    def connection_control(self):
        from netlab.core.transport import simulate_connection_control
        args=dict(action=self.control_action.currentText(),loss=self.loss.value(),delay_ms=self.delay.value(),seed=self.seed.value(),peer_alive=self.peer_alive.isChecked(),valid_sequence=self.peer_alive.isChecked());self.config=args
        self.perform(lambda:simulate_connection_control(**args),self.show,True)

class RoutingPage(Page):
    def __init__(self,window):
        super().__init__(window,'路由与互联网','编辑带权图，逐步检查最短路径；在拓扑页配置实际虚拟接口、静态路由和链路故障。')
        self.algorithm=combo(['Dijkstra','Bellman-Ford','OSPF','RIP','BGP']); self.source=line('R1')
        self.graph=QPlainTextEdit(dumps({'R1':{'R2':2,'R3':8},'R2':{'R1':2,'R3':1,'R4':5},'R3':{'R1':8,'R2':1,'R4':2},'R4':{'R2':5,'R3':2}})); self.graph.setMaximumHeight(210)
        self.output=DataView(); self.steps=Table(['轮次 / 选定节点','变化','当前距离']);self.timeline=Timeline()
        self.destination=line('10.2.3.9'); self.routes=QPlainTextEdit(dumps([{'network':'0.0.0.0/0','next_hop':'192.168.1.1'},{'network':'10.0.0.0/8','next_hop':'R2'},{'network':'10.2.3.0/24','next_hop':'R3'}])); self.routes.setMaximumHeight(120)
        self.layout.addWidget(row(self.algorithm,label('源节点'),self.source,button('计算 / 传播',self.calculate,True),button('打开拓扑',lambda:window.navigate('topology'))))
        self.layout.addWidget(self.graph); self.layout.addWidget(row(label('最长前缀匹配'),self.destination,button('查询路由',self.lookup)))
        self.layout.addWidget(self.routes); self.layout.addWidget(tabs(('路由结果',self.output),('算法步骤',self.steps),('协议传播',self.timeline)),1); self.finish()
    def calculate(self):
        from netlab.core.routing import dijkstra,bellman_ford,route_protocol
        def work():
            a=self.algorithm.currentText()
            if a in ('OSPF','RIP','BGP'):
                self.config={'topology':self.window.pages['topology'].config_dict(),'protocol':a};return route_protocol(**self.config)
            self.config={'graph':json.loads(self.graph.toPlainText()),'source':self.source.text(),'algorithm':a};return (dijkstra if a=='Dijkstra' else bellman_ford)(self.config['graph'],self.config['source'])
        self.perform(work,self.show)
    def show(self,data):
        self.output.set_data(data);self.timeline.set_events(data.get('events',[]));self.timeline.step(); self.steps.set_rows([[x.get('selected',x.get('iteration',i)),dumps(x.get('updates',x)),dumps(x.get('distances',{}))] for i,x in enumerate(data.get('steps',[]))])
    def lookup(self):
        from netlab.core.routing import longest_prefix_match
        def work():self.config={'destination':self.destination.text(),'routes':json.loads(self.routes.toPlainText())};return {'route':longest_prefix_match(**self.config)}
        self.perform(work)

class WebPage(Page):
    def __init__(self,window):
        super().__init__(window,'DNS 与现代 Web','对指定目标执行实际请求；教学模式用虚拟域名演示解析、连接与封装。','实测 / 教学模式分开')
        self.target=line('https://example.com'); self.operation=combo(['website','http','dns','doh','dot','tls','quic']); self.record=combo(['A','AAAA','CNAME','MX','TXT','NS']); self.method=combo(['GET','HEAD','POST','OPTIONS']); self.timeout=spin(5,1,30)
        self.dns_server=line('https://cloudflare-dns.com/dns-query'); self.body=QPlainTextEdit(); self.body.setPlaceholderText('POST 正文（只在选择 POST 后发送）'); self.body.setMaximumHeight(80)
        self.headers=line('{}'); self.output=DataView(); self.timeline=Timeline(); self.local_info=label('本地服务器未运行','muted')
        self.layout.addWidget(row(self.target,self.operation,button('执行指定目标请求',self.probe,True)))
        self.layout.addWidget(row(label('DNS 记录'),self.record,label('方法'),self.method,label('超时 / 秒'),self.timeout))
        self.layout.addWidget(row(label('DoH / DoT 服务'),self.dns_server)); self.layout.addWidget(row(label('HTTP Headers / JSON'),self.headers)); self.layout.addWidget(self.body)
        self.layout.addWidget(row(button('访问网站：教学模拟',self.simulated),button('启动本地 HTTP',lambda:self.start_local('http')),button('启动本地 HTTPS',lambda:self.start_local('https')))); self.layout.addWidget(self.local_info)
        self.layout.addWidget(tabs(('证据与响应',self.output),('教学事件时序',self.timeline)),1); self.finish()
        self.operation.currentTextChanged.connect(self.update_dns_mode)
    def update_dns_mode(self,kind):
        if kind=='dot':self.dns_server.setText('cloudflare-dns.com');self.dns_server.setPlaceholderText('DoT 主机名或 tls://主机:853')
        elif kind=='doh':self.dns_server.setText('https://cloudflare-dns.com/dns-query');self.dns_server.setPlaceholderText('明确指定的 HTTPS DNS 查询端点')
    def probe(self):
        from netlab.services.diagnostics import run_probe
        target=self.target.text();original=target; kind=self.operation.currentText(); kw={'cancel_event':self.window.cancel_event};target_port=443
        if kind in ('dns','doh','dot','tls') and '://' in target:
            from urllib.parse import urlsplit
            parsed=urlsplit(target)
            try:target_port=parsed.port or 443
            except ValueError as exc:return self.status(str(exc),True)
            target=parsed.hostname or target
        if kind in ('doh','dot'): kw['server']=self.dns_server.text()
        if kind=='http':
            try:kw.update(body=self.body.toPlainText(),headers=json.loads(self.headers.text()))
            except ValueError as exc:return self.status('Headers 必须为有效 JSON：'+str(exc),True)
        if getattr(self,'local_ca',None) and original.startswith(self.local_url): kw['cafile']=self.local_ca
        timeout=self.timeout.value();record=self.record.currentText();method=self.method.currentText()
        self.config={'operation':kind,'target':original,'actual_target':target,'port':target_port,'timeout':timeout,'record_type':record,'method':method,'server':kw.get('server'),'headers':kw.get('headers',{}),'body':kw.get('body','')}
        self.perform(lambda:run_probe(kind,target,port=target_port,timeout=timeout,record_type=record,method=method,**kw),background=True)
    def simulated(self):
        from netlab.core.experiments import website_experiment
        target=self.target.text();self.config={'operation':'website_simulation','target':target,'transport':'TCP','seed':1}
        self.perform(lambda:website_experiment(target),lambda d:(self.output.set_data(d),self.timeline.set_events(d.get('events',[])),self.timeline.step()))
    def start_local(self,kind):
        self.config={'operation':'start_local','server_kind':kind,'host':'127.0.0.1','port':0}
        def show(d):
            self.output.set_data(d); self.local_info.setText(dumps(d)); self.local_url=d.get('url',f"{kind}://127.0.0.1:{d['port']}"); self.target.setText(self.local_url); self.local_ca=d.get('cafile',d.get('certificate')); self.operation.setCurrentText('http')
        self.perform(lambda:self.window.servers.start(kind),show,True)

class DiagnosticsPage(Page):
    def __init__(self,window):
        super().__init__(window,'网络诊断中心','仅检查你指定的主机。诊断向导按接口、地址、网关、连接和 DNS 收集证据。','实际通信')
        self.target=line('127.0.0.1'); self.operation=combo(['tcp','ping','traceroute','tls','http','dns','latency','diagnose']); self.port=spin(443,1,65535); self.timeout=spin(3,1,10); self.count=spin(4,1,30)
        self.output=DataView(); self.chart=LineChart(); self.layout.addWidget(row(self.target,self.operation,button('开始诊断',self.probe,True)))
        self.layout.addWidget(row(label('端口'),self.port,label('超时 / 秒'),self.timeout,label('次数'),self.count)); self.layout.addWidget(self.chart); self.layout.addWidget(self.output,1); self.finish()
    def probe(self):
        from netlab.services.diagnostics import run_probe
        params={'kind':self.operation.currentText(),'target':self.target.text(),'port':self.port.value(),'timeout':self.timeout.value(),'count':self.count.value()};self.config=params
        self.perform(lambda:run_probe(**params,cancel_event=self.window.cancel_event),self.show,True)
    def show(self,d):
        self.output.set_data(d); detail=d.get('details',{}); samples=d.get('samples',detail.get('samples_ms',detail.get('samples',detail.get('rtt_ms',[])))) if isinstance(detail,dict) else d.get('samples',[])
        self.chart.set_series([x if isinstance(x,(int,float)) else x.get('elapsed_ms',x.get('rtt_ms')) if isinstance(x,dict) else None for x in samples])
        self.window.db.save_experiment('diagnostic',self.config.get('target','诊断'),self.config,d)

class SecurityPage(Page):
    def __init__(self,window):
        super().__init__(window,'网络安全与 VPN','证书检查使用系统信任库；防火墙与隧道在虚拟网络中计算，不修改 Windows 设置。','实测 / 教学模式分开')
        self.target=line('example.com'); self.port=spin(443,1,65535); self.output=DataView(); self.timeline=Timeline()
        self.packet=QPlainTextEdit(dumps({'source':'10.0.0.2','destination':'10.0.0.8','protocol':'TCP','sport':50200,'dport':443})); self.packet.setMaximumHeight(100)
        self.rules=QPlainTextEdit(dumps([{'action':'allow','protocol':'TCP','dport':443},{'action':'deny','protocol':'TCP','dport':23}])); self.rules.setMaximumHeight(125)
        self.layout.addWidget(row(self.target,self.port,button('验证 TLS 证书',self.cert,True),button('查看 Windows 防火墙',self.firewall)))
        self.layout.addWidget(row(button('TLS / VPN 课程',lambda:window.learn('VPN')),button('SSH 握手检查',self.ssh),button('TLS 握手教学',self.tls_sim)))
        self.message=line('Hello secure channel');self.tamper=QCheckBox('篡改密文 / 签名');self.vpn_target=line('10.1.2.3');self.split_prefixes=line('10.0.0.0/8,192.168.0.0/16');self.full_tunnel=QCheckBox('全隧道');self.encrypt=QCheckBox('加密隧道');self.encrypt.setChecked(True)
        self.layout.addWidget(row(self.message,self.tamper,button('哈希 / 密钥交换 / 签名实验',self.crypto)))
        self.layout.addWidget(row(label('目的 IP'),self.vpn_target,label('分流前缀'),self.split_prefixes,self.full_tunnel,self.encrypt,button('计算 VPN 封装与路由',self.vpn)))
        self.layout.addWidget(label('虚拟防火墙：数据包与规则（JSON）','sectionTitle')); self.layout.addWidget(self.packet); self.layout.addWidget(self.rules); self.layout.addWidget(button('按规则匹配',self.match))
        self.layout.addWidget(tabs(('安全证据',self.output),('握手事件',self.timeline)),1); self.finish()
    def cert(self):
        from netlab.services.diagnostics import run_probe
        target=self.target.text();port=self.port.value();self.config={'operation':'tls','target':target,'port':port};self.perform(lambda:run_probe('tls',target,port=port,cancel_event=self.window.cancel_event),background=True)
    def ssh(self):
        from netlab.services.diagnostics import run_probe
        target=self.target.text();port=self.port.value();self.config={'operation':'ssh','target':target,'port':port};self.perform(lambda:run_probe('ssh',target,port=port,cancel_event=self.window.cancel_event),background=True)
    def firewall(self):
        from netlab.services.observe import firewall
        self.config={'operation':'windows_firewall'}
        self.perform(firewall,background=True)
    def match(self):
        from netlab.core.services import evaluate_firewall
        def work():
            self.config={'operation':'firewall_simulation','packet':json.loads(self.packet.toPlainText()),'rules':json.loads(self.rules.toPlainText())};return evaluate_firewall(self.config['packet'],self.config['rules'])
        self.perform(work)
    def tls_sim(self):
        from netlab.services.security import tls_handshake_model
        self.config={'operation':'tls_handshake_model','resumed':False}
        self.perform(tls_handshake_model,lambda d:(self.output.set_data(d),self.timeline.set_events(d.get('events',[])),self.timeline.step()))
    def crypto(self):
        from netlab.services.security import crypto_demo
        message=self.message.text();tamper=self.tamper.isChecked();self.config={'operation':'crypto_demo','message':message,'tamper':tamper};self.perform(lambda:crypto_demo(message,tamper),background=True)
    def vpn(self):
        from netlab.services.security import vpn_demo
        params=dict(destination=self.vpn_target.text(),split_prefixes=[s.strip() for s in self.split_prefixes.text().split(',') if s.strip()],full_tunnel=self.full_tunnel.isChecked(),encrypted=self.encrypt.isChecked(),message=self.message.text());self.config=params
        self.perform(lambda:vpn_demo(**params),lambda d:(self.output.set_data(d),self.timeline.set_events(d.get('events',[])),self.timeline.step()),True)

class GamePage(Page):
    def __init__(self,window):
        super().__init__(window,'游戏网络与 P2P','比较真实位置、预测位置与服务器确认；改变延迟和丢包，观察同步误差。NAT 穿透结果来自教学映射规则。')
        self.delay=decimal(60,0,2000); self.loss=decimal(.05,0,1,.01); self.seed=spin(1,0,99999); self.nat=combo(['cone','restricted','symmetric','cgnat']); self.output=DataView(); self.timeline=Timeline(); self.chart=LineChart('玩家同步误差 / 单位');self.arena=GameArena()
        self.layout.addWidget(row(label('单向延迟 ms'),self.delay,label('丢包概率'),self.loss,label('NAT'),self.nat,label('随机种子'),self.seed,button('运行联机实验',self.simulate,True)))
        self.layout.addWidget(self.chart); self.layout.addWidget(tabs(('玩家同步',self.arena),('联机事件',self.timeline),('位置与穿透结果',self.output)),1); self.finish()
    def simulate(self):
        from netlab.core.experiments import game_experiment
        params={'delay_ms':self.delay.value(),'loss':self.loss.value(),'seed':self.seed.value(),'nat_type':self.nat.currentText()};self.config=params
        self.perform(lambda:game_experiment(**params),self.show,True)
    def show(self,d):
        self.output.set_data(d); self.timeline.set_events(d.get('events',[])); self.timeline.step()
        self.chart.set_series([v.get('prediction_error',0) for v in d.get('frames',[])]);self.arena.set_frames(d.get('frames',[]))

class CapturePage(Page):
    def __init__(self,window):
        super().__init__(window,'抓包与协议分析','导入 PCAP / PCAPNG 查看字段与原始字节。实时抓包只在你选定接口并点击后启动。','文件解析 / 实时抓包 / 虚拟包')
        self.file=line('', '选择抓包文件'); self.filter=combo(['全部','Ethernet','IPv4','IPv6','TCP','UDP','ICMP','DNS','ARP']); self.interface=line('', '接口名称或 Npcap 标识'); self.duration=spin(3,1,30); self.limit=spin(100,1,2000)
        self.table=Table(['序号','时间','源地址','目的地址','源端口','目的端口','协议','长度','摘要']); self.output=DataView();self.timeline=Timeline(); self.packets=[]
        self.layout.addWidget(row(self.file,button('打开文件',self.open_file),self.filter,button('解析',self.load,True)))
        self.layout.addWidget(row(self.interface,label('秒'),self.duration,label('包上限'),self.limit,button('检查抓包支持',self.capability),button('在此接口抓包',self.capture)))
        self.layout.addWidget(self.table,1); self.layout.addWidget(tabs(('完整字段 / Hex',self.output),('TCP 会话时序',self.timeline)),1); self.finish(); self.table.cellClicked.connect(self.select); self.filter.currentTextChanged.connect(self.apply_filter)
    def open_file(self):
        path,_=QFileDialog.getOpenFileName(self,'打开授权抓包文件','','PCAP (*.pcap *.pcapng *.cap)')
        if path: self.file.setText(path); self.load()
    def load(self):
        from netlab.services.packets import read_capture
        path=self.file.text(); self.config={'path':path}; self.perform(lambda:read_capture(path),self.show,True)
    def show(self,d):
        self.packets=d.get('packets',[]); self.output.set_data({k:v for k,v in d.items() if k!='packets'});events=d.get('events',[e for f in d.get('flows',[]) for e in f.get('events',[])]);events.sort(key=lambda e:e.get('time',0));self.timeline.set_events(events);self.timeline.step(); self.apply_filter()
    def apply_filter(self):
        f=self.filter.currentText();aliases={'IPv4':'IP','Ethernet':'Ether'};layer=aliases.get(f,f)
        self.filtered=[p for p in self.packets if f=='全部' or layer in p.get('protocols',[]) or f.lower() in dumps(p.get('fields',{})).lower() or f.lower() in str(p.get('protocol','')).lower()]
        self.table.set_rows([[p.get(k,'') for k in ['index','time','source','destination','sport','dport','protocol','length','summary']] for p in self.filtered])
    def select(self,r,c):
        index=self.table.item(r,0).text(); p=next((p for p in self.packets if str(p.get('index'))==index),None)
        if p: self.output.set_data(p)
    def capability(self):
        from netlab.services.packets import capability
        self.perform(capability,background=True)
    def capture(self):
        if not self.interface.text().strip(): return self.status('请先明确指定已授权的本机接口',True)
        from netlab.services.packets import capture
        args=(self.interface.text(),self.duration.value(),self.limit.value()); self.config={'interface':args[0],'duration':args[1],'limit':args[2]}
        self.perform(lambda:capture(*args),self.show,True)
    def virtual(self,packets):
        self.timeline.set_events([]);self.config={'operation':'virtual_frame_analysis'};self.result={'kind':'teaching','data_source':'virtual_frame','packets':packets}; self.packets=packets; self.apply_filter(); self.output.set_data({'来源':'虚拟拓扑中的教学数据包；未发送到真实网卡'})

class ProgrammingPage(Page):
    def __init__(self,window):
        super().__init__(window,'Socket 与网络编程','示例默认使用回环地址。运行编辑器中的代码会启动本机子进程，请只运行你信任的代码。','真实本地通信')
        self.template=QComboBox(); self.language=combo(['Python','C']); self.code=QPlainTextEdit(); self.code.setTabStopDistance(32); self.output=DataView(); self.server_kind=combo(['tcp','udp','http','https','http2','chat','file','websocket','http3','ssh']); self.server_port=spin(0,0,65535); self.host=line('127.0.0.1'); self.client_port=spin(0,0,65535); self.message=line('Hello NetLab'); self.timeout=spin(10,1,30)
        self.layout.addWidget(row(self.language,self.template,button('加载示例',self.load_template),button('运行代码',self.run_code,True),label('执行上限 / 秒'),self.timeout))
        self.layout.addWidget(row(label('本地服务器'),self.server_kind,self.server_port,button('启动',self.start),button('停止全部',self.stop)))
        self.layout.addWidget(row(self.host,self.client_port,self.message,button('实际通信测试',self.echo)))
        split=QSplitter(); split.addWidget(self.code); split.addWidget(self.output); split.setSizes([600,500]); self.layout.addWidget(split,1); self.finish(); self.templates={}
        self.language.currentTextChanged.connect(self.init_templates); self.init_templates()
    def init_templates(self):
        from netlab.services.programming import templates
        self.templates=templates(); self.template.clear()
        if isinstance(self.templates,list):self.templates=[v for v in self.templates if v['language']==self.language.currentText().lower()]
        if isinstance(self.templates,dict): self.template.addItems(list(self.templates))
        elif isinstance(self.templates,list): self.template.addItems([str(x.get('name',i)) for i,x in enumerate(self.templates)])
        self.load_template()
    def load_template(self):
        key=self.template.currentText()
        item=self.templates.get(key,'') if isinstance(self.templates,dict) else next((v for v in self.templates if v.get('name')==key),{})
        text=item if isinstance(item,str) else item.get('code',item.get('source',''))
        self.code.setPlainText(text)
    def run_code(self):
        from netlab.services.programming import run_python
        code=self.code.toPlainText(); timeout=self.timeout.value(); self.config={'language':self.language.currentText(),'timeout':timeout,'code':code}
        if self.language.currentText()=='C':
            from netlab.services.programming import run_c
            self.perform(lambda:run_c(code,timeout=timeout),background=True)
        else: self.perform(lambda:run_python(code,timeout=timeout),background=True)
    def start(self):
        kind=self.server_kind.currentText(); port=self.server_port.value()
        self.config={'operation':'start_local','server_kind':kind,'host':'127.0.0.1','server_port':port}
        def show(d): self.output.set_data(d); self.client_port.setValue(d.get('port',0)); self.host.setText('127.0.0.1')
        self.perform(lambda:self.window.servers.start(kind,port=port),show,True)
    def stop(self):
        self.config={'operation':'stop_local','servers_before':self.window.servers.list()}
        self.perform(lambda:(self.window.servers.stop_all(),{'servers':self.window.servers.list(),'status':'本地服务器已停止'})[1],background=True)
    def echo(self):
        from netlab.services.servers import echo_client
        kind=self.server_kind.currentText(); host=self.host.text(); port=self.client_port.value(); message=self.message.text()
        self.config={'operation':'client_communication','server_kind':kind,'host':host,'client_port':port,'message':message}
        def work():
            if kind in ('tcp','udp'):return echo_client(kind,host,port,message)
            if kind=='chat':
                from netlab.services.servers import chat_client
                return chat_client(host,port,message)
            if kind=='file':
                from netlab.services.servers import file_client
                return file_client(host,port,message.encode())
            from netlab.services.diagnostics import run_probe
            local=next((s for s in self.window.servers.list() if s['port']==port),{})
            scheme='ws' if kind=='websocket' else 'https' if kind in ('https','http2','http3') else 'http'
            host_for_url=f'[{host}]' if ':' in host else host
            target=host if kind=='ssh' else f'{scheme}://{host_for_url}:{port}/'
            if kind=='ssh' and local.get('trusted_public_key'):
                from netlab.services.modern import ssh_local_client
                return ssh_local_client(host,port,local['trusted_public_key'])
            return run_probe(kind,target,port=port,cafile=local.get('cafile'),message=message)
        self.perform(work,background=True)


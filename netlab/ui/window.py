import logging
import threading
from pathlib import Path
from PySide6.QtCore import Qt,QThreadPool,QTimer,QAbstractAnimation
from PySide6.QtGui import QAction,QKeySequence,QFont
from PySide6.QtWidgets import (QMainWindow,QApplication,QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QStackedWidget,QSplitter,QTextBrowser,QStatusBar,QMessageBox,QDialog,QDialogButtonBox,QCheckBox)
from .common import Job,Page,button,label,row,line
from .theme import apply_theme
from .network_pages import ObservePage,SubnetPage,RoutingPage,TransportPage,WebPage,SecurityPage,GamePage,CapturePage,DiagnosticsPage,ProgrammingPage
from .topology import TopologyPage
from .system_pages import BinaryPage,CPUPage,MemoryPage,OSPage
from .learning import LearningPage,IntegratedPage,HistoryPage

NAV=[('home','工作台'),('subnet','网络基础与子网'),('observe','本机网络观察'),('topology','局域网与拓扑'),('routing','路由与互联网'),('transport','TCP / UDP / QUIC'),('web','DNS 与现代 Web'),('security','安全与 VPN'),('game','游戏网络与 P2P'),('capture','抓包与协议分析'),('diagnostics','网络诊断'),('programming','Socket 编程'),('learning','课程与练习'),('integrated','综合实验 A–F'),('binary','二进制与逻辑'),('cpu','CPU 与网络应用'),('memory','Cache 与内存'),('os','操作系统与 I/O'),('history','记录与数据管理')]

class HomePage(Page):
    def __init__(self,window):
        super().__init__(window,'探索每一次通信','NetLab Studio 将你的 Windows 网络、虚拟协议和计算机系统放到一个可检查的实验空间。','本地实验室')
        self.layout.addWidget(label('从问题开始','sectionTitle'))
        for title,text,key in [('看见真实网络','读取适配器、Wi-Fi、活动连接与进程，检查指定目标的连接。','observe'),('搭建一张网络','用设备、接口和链路创建局域网，单步观察 ARP、交换与转发。','topology'),('改变协议条件','调整延迟、抖动、丢包与窗口，检查 TCP / UDP / QUIC 的计算结果。','transport'),('看见系统协作','执行汇编 SEND，检查应用、内核缓冲区、DMA 与协议栈的事件。','cpu')]:
            self.layout.addWidget(row(button(title,lambda checked=False,k=key:window.navigate(k),True),label(text,'subtitle')))
        self.layout.addWidget(label('建议学习路线','sectionTitle'));self.layout.addWidget(label('地址与封装 → ARP 和交换 → 路由 → 可靠传输 → DNS / TLS / HTTP → Socket → CPU 与操作系统','muted'))
        self.layout.addWidget(row(button('访问网站综合实验',lambda:window.navigate('integrated')),button('学习中心',lambda:window.navigate('learning')),button('实验历史',lambda:window.navigate('history'))))
        self.summary=label('','muted');self.layout.addWidget(self.summary);self.layout.addStretch();self.layout.addWidget(label('实测数据来自本机接口或你指定的目标；示例和协议模型明确标为教学模拟。个人数据默认存储在本机。','muted'));self.update_summary()
    def update_summary(self):self.summary.setText(f'本地已保存 {len(self.window.db.list_experiments())} 次实验 · {len(self.window.db.get_progress())} 个知识点有学习记录')

class MainWindow(QMainWindow):
    def __init__(self,db,data_dir):
        super().__init__();self.db=db;self.data_dir=Path(data_dir);self.jobs=[];self.pool=QThreadPool(self);self.pool.setMaxThreadCount(3);self.closing=False;self.cancel_event=threading.Event();self.light=bool(db.get_setting('light_theme',False));self.nav_collapsed=False;self.inspector_preferred=True
        from netlab.services.servers import LocalServerManager
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True)
        self.servers=LocalServerManager();self.setWindowTitle('NetLab Studio · 计算机网络与系统实验室');self.resize(1480,920);self.setMinimumSize(1000,680)
        container=QWidget();outer=QVBoxLayout(container);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0);self.setCentralWidget(container)
        top=QFrame();top.setObjectName('topbar');tl=QHBoxLayout(top);tl.setContentsMargins(15,10,15,10);self.toggle_nav=button('☰',self.collapse_nav);tl.addWidget(self.toggle_nav);tl.addWidget(label('NetLab Studio','brand'));self.global_search=line('', '全局知识搜索  Ctrl+K');self.global_search.setMaximumWidth(420);tl.addWidget(self.global_search,1);tl.addStretch();self.task_label=label('就绪 · 本地','badge');tl.addWidget(self.task_label);tl.addWidget(button('深色 / 浅色',self.theme));tl.addWidget(button('知识面板',self.toggle_inspector));tl.addWidget(button('设置',self.settings));outer.addWidget(top)
        self.split=QSplitter();self.sidebar=QFrame();self.sidebar.setObjectName('sidebar');sl=QVBoxLayout(self.sidebar);sl.setContentsMargins(0,16,0,10);sl.addWidget(label('   LABORATORIES','muted'));self.nav=QListWidget();self.nav.setObjectName('navigation');self.nav.addItems([f'{i+1:02d}  {name}' for i,(_,name) in enumerate(NAV)]);sl.addWidget(self.nav);sl.addWidget(label('   v1.0.0 · Native Qt','muted'));self.sidebar.setMaximumWidth(245);self.sidebar.setMinimumWidth(215);self.split.addWidget(self.sidebar)
        self.stack=QStackedWidget();self.split.addWidget(self.stack);self.pages={}
        classes={'home':HomePage,'subnet':SubnetPage,'observe':ObservePage,'topology':TopologyPage,'routing':RoutingPage,'transport':TransportPage,'web':WebPage,'security':SecurityPage,'game':GamePage,'capture':CapturePage,'diagnostics':DiagnosticsPage,'programming':ProgrammingPage,'learning':LearningPage,'integrated':IntegratedPage,'binary':BinaryPage,'cpu':CPUPage,'memory':MemoryPage,'os':OSPage,'history':HistoryPage}
        for key,name in NAV:
            self.pages[key]=classes[key](self);self.stack.addWidget(self.pages[key])
        self.inspector=QFrame();self.inspector.setObjectName('inspector');il=QVBoxLayout(self.inspector);il.setContentsMargins(15,20,15,15);il.addWidget(label('知识与实验指导','sectionTitle'));self.knowledge=QTextBrowser();self.knowledge.setOpenExternalLinks(True);il.addWidget(self.knowledge);il.addWidget(button('到课程中心',lambda:self.navigate('learning')));self.inspector.setMinimumWidth(230);self.inspector.setMaximumWidth(330);self.split.addWidget(self.inspector);self.split.setSizes([220,1010,250]);outer.addWidget(self.split,1)
        self.setStatusBar(QStatusBar());self.statusBar().showMessage('就绪 · 无需管理员权限启动 · 抓包驱动单独检测');self.nav.currentRowChanged.connect(self.select_page);self.nav.setCurrentRow(0);self.global_search.returnPressed.connect(lambda:self.learn(self.global_search.text()));apply_theme(QApplication.instance(),self.light)
        a=QAction(self);a.setShortcut(QKeySequence('Ctrl+K'));a.triggered.connect(self.global_search.setFocus);self.addAction(a)
        save=QAction(self);save.setShortcut(QKeySequence('Ctrl+S'));save.triggered.connect(lambda:self.stack.currentWidget().save());self.addAction(save)
        reset=QAction(self);reset.setShortcut(QKeySequence('F5'));reset.triggered.connect(lambda:self.pages['observe'].refresh() if self.stack.currentWidget()==self.pages['observe'] else self.pages['history'].refresh());self.addAction(reset)
    def navigate(self,key):
        if key in self.pages:self.nav.setCurrentRow([k for k,_ in NAV].index(key))
    def select_page(self,index):
        if index<0:return
        self.stack.setCurrentIndex(index);key= NAV[index][0]
        if key=='history':self.pages[key].refresh()
        if key=='home':self.pages[key].update_summary()
        from netlab.content import search_topics
        queries={'home':'OSI','subnet':'CIDR','observe':'Wi-Fi','topology':'ARP','routing':'路由','transport':'TCP','web':'DNS','security':'TLS','game':'NAT','capture':'抓包','diagnostics':'故障','programming':'Socket','binary':'补码','cpu':'CPU','memory':'Cache','os':'DMA'}
        results=search_topics(queries.get(key,'网络'))
        if results:
            import html
            t=results[0];self.knowledge.setHtml(f'<h2>{html.escape(t["title"])}</h2><p>{html.escape(str(t["concept"]))}</p><h3>操作提示</h3><p>{html.escape(str(t["mechanism"]))}</p><p>{html.escape(str(t["example"]))}</p><h3>实验步骤</h3><p>1. 检查参数与目标。<br>2. 执行本页实验。<br>3. 查看证据、事件和字段。<br>4. 保存实验并记录你的结论。</p>')
    def learn(self,query):
        self.navigate('learning');p=self.pages['learning'];p.category.setCurrentIndex(0);p.search.setText(query)
    def open_experiment(self,experiment,title=''):
        text=str(experiment).lower();mapping=[(('integrated','challenge'),'integrated'),(('observe','adapter'),'observe'),(('diagnostic','ping'),'diagnostics'),(('performance',),'os'),(('subnet','cidr','vlsm'),'subnet'),(('transport','tcp','udp','quic'),'transport'),(('routing','ospf','rip','bgp'),'routing'),(('web','dns','http'),'web'),(('security','tls','vpn','firewall'),'security'),(('game','gaming','p2p','stun'),'game'),(('packet','capture','pcap'),'capture'),(('program','socket'),'programming'),(('binary','logic','alu'),'binary'),(('cache','memory'),'memory'),(('cpu','assembly'),'cpu'),(('os','schedule','page','dma'),'os'),(('topology','arp','dhcp','vlan','lan'),'topology')]
        key=next((k for terms,k in mapping if any(v in text for v in terms)),'integrated');self.navigate(key)
    def collapse_nav(self):
        self.nav_collapsed=not self.nav_collapsed;self.sidebar.setVisible(not self.nav_collapsed)
    def toggle_inspector(self):
        self.inspector_preferred=not self.inspector.isVisible();self.inspector.setVisible(self.inspector_preferred)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'inspector'):self.inspector.setVisible(self.inspector_preferred and self.width()>=1250)
    def theme(self):self.light=not self.light;apply_theme(QApplication.instance(),self.light);self.db.set_setting('light_theme',self.light)
    def settings(self):
        d=QDialog(self);d.setWindowTitle('本地设置');l=QVBoxLayout(d);l.addWidget(label('数据目录：'+str(self.data_dir)));l.addWidget(label('实验数据库、设置和日志只保存在本机。网络请求仅在点击执行后访问指定目标。'));l.addWidget(button('打开数据管理',lambda:(d.accept(),self.navigate('history'))));l.addWidget(button('查看技术限制',lambda:(d.accept(),self.show_limits())));buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(d.reject);l.addWidget(buttons);d.exec()
    def show_limits(self):
        QMessageBox.information(self,'技术范围','协议、CPU 与操作系统模拟是教学模型。\n实时抓包需要 Npcap 和允许抓包的权限。\nWi-Fi 数据取决于驱动和 Windows 提供的信息。\nHTTP/3、SSH 和 TLS 使用成熟库；是否可连接取决于目标服务、UDP 路径及证书。\n完整逐项实现和验证情况见项目 docs/FEATURES.md。')
    def run_job(self,function,on_result,on_error):
        if self.closing:return on_error('应用正在关闭，未启动新任务')
        if len(self.jobs)>=3:return on_error('当前已有 3 个后台任务；等待其中一个完成后再开始')
        job=Job(function);self.jobs.append(job);self.task_label.setText(f'{len(self.jobs)} 个后台任务')
        def error(msg):logging.getLogger('netlab').error(msg);on_error(msg)
        def finished():
            if job in self.jobs:self.jobs.remove(job)
            self.task_label.setText(f'{len(self.jobs)} 个后台任务' if self.jobs else '就绪 · 本地')
            if self.closing and not self.jobs:QTimer.singleShot(0,self.close)
        job.signals.result.connect(on_result);job.signals.error.connect(error);job.signals.finished.connect(finished);self.pool.start(job)
    def closeEvent(self,event):
        self.closing=True
        self.cancel_event.set()
        for p in self.pages.values():
            for timer in p.findChildren(QTimer):timer.stop()
            for animation in p.findChildren(QAbstractAnimation):animation.stop()
        if self.jobs:
            event.ignore();self.statusBar().showMessage('正在等待有界网络任务退出，随后关闭应用…');return
        self.servers.close();self.db.close();event.accept()


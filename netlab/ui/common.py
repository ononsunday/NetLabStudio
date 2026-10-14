import json
import copy
from dataclasses import asdict, is_dataclass
from PySide6.QtCore import QObject, QRunnable, Signal, Qt, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QLineEdit, QFileDialog, QMessageBox, QTabWidget, QPlainTextEdit,QInputDialog,QMenu,QScrollArea,QLayout)

def serial(value):
    if is_dataclass(value): return asdict(value)
    if isinstance(value, bytes): return value.hex()
    if hasattr(value, 'to_dict'): return value.to_dict()
    return str(value)

def dumps(value): return json.dumps(value, ensure_ascii=False, indent=2, default=serial)

class JobSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

class Job(QRunnable):
    def __init__(self, function):
        super().__init__(); self.function = function; self.signals = JobSignals()
    def run(self):
        try: self.signals.result.emit(self.function())
        except Exception as exc: self.signals.error.emit(f"{type(exc).__name__}: {exc}")
        finally: self.signals.finished.emit()

def button(text, fn=None, primary=False):
    b=QPushButton(text)
    if primary: b.setObjectName('primary')
    if fn: b.clicked.connect(fn)
    return b

def row(*widgets):
    w=QWidget(); l=QHBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(8)
    for x in widgets: l.addWidget(x)
    return w

def label(text, name=None):
    w=QLabel(text); w.setWordWrap(len(text)>30)
    if name: w.setObjectName(name)
    if name=='badge':w.setMaximumWidth(220)
    return w

def line(text='', placeholder=''):
    w=QLineEdit(text); w.setPlaceholderText(placeholder); return w

class DataView(QTabWidget):
    def __init__(self):
        super().__init__(); self.tree=QTreeWidget(); self.tree.setHeaderLabels(['字段 / Evidence','值']); self.tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.raw=QPlainTextEdit(); self.raw.setReadOnly(True)
        self.addTab(self.tree,'结构与证据'); self.addTab(self.raw,'JSON')
    def set_data(self,data):
        self.raw.setPlainText(dumps(data)); self.tree.clear()
        def add(parent,key,val,depth=0):
            if depth>18: val='结构过深，请查看 JSON'
            complex_=isinstance(val,(dict,list,tuple))
            item=QTreeWidgetItem([str(key), f'{len(val)} 项' if complex_ else str(val)])
            parent.addChild(item) if isinstance(parent,QTreeWidgetItem) else parent.addTopLevelItem(item)
            if isinstance(val,dict):
                for k,v in val.items(): add(item,k,v,depth+1)
            elif isinstance(val,(list,tuple)):
                for k,v in enumerate(val[:1000]): add(item,k,v,depth+1)
                if len(val)>1000: add(item,'提示','树视图最多显示前 1000 项；JSON 保留完整结果',depth+1)
        if isinstance(data,dict):
            for k,v in data.items(): add(self.tree,k,v)
        else: add(self.tree,'result',data)
        self.tree.expandToDepth(0)

class Table(QTableWidget):
    def __init__(self,headers):
        super().__init__(0,len(headers)); self.setHorizontalHeaderLabels(headers); self.setAlternatingRowColors(True); self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.horizontalHeader().setStretchLastSection(True); self.verticalHeader().hide()
        self.query='';self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.customContextMenuRequested.connect(self.filter_menu)
    def set_rows(self,rows):
        self.setSortingEnabled(False); self.setRowCount(len(rows))
        for r,values in enumerate(rows):
            for c,v in enumerate(values):
                item=QTableWidgetItem()
                if isinstance(v,(int,float)): item.setData(Qt.ItemDataRole.DisplayRole,v)
                else: item.setText(str(v))
                self.setItem(r,c,item)
        self.setSortingEnabled(True); self.resizeColumnsToContents()
        self.filter_rows()
    def filter_menu(self,pos):
        menu=QMenu(self);action=menu.addAction('筛选当前表格');clear=menu.addAction('清除筛选');selected=menu.exec(self.viewport().mapToGlobal(pos))
        if selected==clear:self.query='';self.filter_rows()
        elif selected==action:
            text,ok=QInputDialog.getText(self,'表格筛选','匹配任意列文本',text=self.query)
            if ok:self.query=text.casefold();self.filter_rows()
    def filter_rows(self):
        for r in range(self.rowCount()):self.setRowHidden(r,bool(self.query) and not any(self.query in self.item(r,c).text().casefold() for c in range(self.columnCount()) if self.item(r,c)))

class Page(QWidget):
    def __init__(self,window,title,subtitle,kind='教学模拟'):
        super().__init__(); self.window=window; self.name=title; self.setObjectName('page'); self.result=None; self.config={};self.busy=False
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(self.scroll.Shape.NoFrame);outer.addWidget(self.scroll)
        self.body=QWidget();self.body.setObjectName('page');self.scroll.setWidget(self.body)
        self.layout=QVBoxLayout(self.body); self.layout.setContentsMargins(22,20,22,15); self.layout.setSpacing(12);self.layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.layout.addWidget(row(label(title,'pageTitle'),label(kind,'badge')))
        self.layout.addWidget(label(subtitle,'subtitle'))
        self.feedback=label('准备就绪','muted')
    def finish(self):
        self.layout.addWidget(self.feedback)
        self.layout.addWidget(row(button('保存实验',self.save),button('保存为模板',self.save_template),button('导出 JSON',self.export),button('生成报告',self.report)))
    def status(self,text,error=False):
        self.feedback.setText(text); self.feedback.setStyleSheet('color: #ff8798' if error else '')
        self.window.statusBar().showMessage(text,12000)
    def perform(self,fn,callback=None,background=False):
        if self.busy:return self.status('本页任务正在执行，请等待结果',True)
        clicked_config=copy.deepcopy(self.config)
        self.result=None
        disabled=[]
        if background:
            self.busy=True
            disabled=[w for w in self.findChildren(QPushButton) if w.isEnabled()]
            for w in disabled:w.setEnabled(False)
        self.status('正在执行…')
        def enable():
            self.busy=False
            for w in disabled:w.setEnabled(True)
        def ok(data):
            self.result=data
            if background:self.config=clicked_config
            try:
                if callback: callback(data)
                elif hasattr(self,'output'): self.output.set_data(data)
            except Exception as exc:
                self.status(f'结果展示失败，原始结果仍可导出：{type(exc).__name__}: {exc}',True);enable();return
            measured=isinstance(data,dict) and (data.get('kind')=='measured' or data.get('data_kind')=='measured')
            source=('导入抓包文件解析；采集环境由文件提供者说明' if isinstance(data,dict) and data.get('data_source')=='pcap_import' else '本机实测 / 实际通信' if measured else '教学模拟或本地计算')
            failed=isinstance(data,dict) and data.get('ok') is False
            self.status(('执行结束，检测失败：'+str(data.get('error') or '查看失败项与证据') if failed else '完成。结果来源：'+source),failed)
            enable()
        def fail(msg):self.status(msg,True);enable()
        if background: self.window.run_job(fn,ok,fail)
        else:
            try: ok(fn())
            except Exception as exc: fail(f'{type(exc).__name__}: {exc}')
    def save(self):
        if self.busy:return self.status('等待当前任务完成后再保存',True)
        if self.result is None: return self.status('请先完成一次实验',True)
        try:
            self.window.db.save_experiment(self.name,self.name,self.config,self.result); self.status('已保存到本地 SQLite')
        except Exception as exc: self.status(str(exc),True)
    def export(self):
        if self.result is None: return self.status('请先运行实验',True)
        path,_=QFileDialog.getSaveFileName(self,'导出实验','','JSON (*.json)')
        if path:
            try:
                with open(path,'w',encoding='utf-8') as f: f.write(dumps({'module':self.name,'config':self.config,'result':self.result}))
                self.status('已导出 '+path)
            except OSError as exc: self.status(str(exc),True)
    def report(self):
        if self.result is None: return self.status('请先运行实验',True)
        from .reports import report_dialog
        report_dialog(self)
    def save_template(self):
        if not self.config:return self.status('先设置并运行一次实验，模板将保存本次参数',True)
        name,ok=QInputDialog.getText(self,'保存实验模板','模板名称',text=self.name)
        if ok and name:
            try:self.window.db.save_template(name,self.name,self.config);self.status('实验模板已保存')
            except Exception as exc:self.status(str(exc),True)
    def apply_config(self,config):
        if 'nodes' in config and hasattr(self,'set_config'):return self.set_config(config)
        mapping={'base':'cidr','action':'control_action','bytes_total':'size','size':'packet_size','version':'ip_version','receive_window':'window_size','delay_ms':'delay','jitter_ms':'jitter','bandwidth_mbps':'bandwidth','nat_type':'nat','target':'target','operation':'operation','kind':'operation','block_size':'block','buffer_bytes':'buffer_size','processing':'processing','assembly':'code','code':'code','record_type':'record','server':'dns_server','references':'refs','mtus':'path_mtus','encrypted':'encrypt','split_prefixes':'split_prefixes'}
        for k,v in config.items():
            control=getattr(self,mapping.get(k,k),None)
            if control is None:continue
            if hasattr(control,'setChecked') and isinstance(v,bool):control.setChecked(v)
            elif hasattr(control,'setValue') and isinstance(v,(int,float)):control.setValue(v)
            elif hasattr(control,'setCurrentText'):control.setCurrentText(str(v))
            elif hasattr(control,'setPlainText'):control.setPlainText(dumps(v) if isinstance(v,(list,dict)) else str(v))
            elif hasattr(control,'setText'):control.setText(','.join(str(x) for x in v) if isinstance(v,list) else dumps(v) if isinstance(v,dict) else str(v))
        self.config=copy.deepcopy(config);self.result=None;self.status('模板参数已载入；执行后生成新的实验结果')


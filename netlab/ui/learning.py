import html
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QSplitter,QListWidget,QListWidgetItem,QTextBrowser,QPlainTextEdit,QFileDialog,QInputDialog,QMessageBox,QCheckBox,QTabWidget,QDialog,QDialogButtonBox
from .common import Page,DataView,Table,button,label,row,line,dumps
from .network_pages import combo,tabs,spin
from .visuals import Timeline

class LearningPage(Page):
    def __init__(self,window):
        super().__init__(window,'课程与互动学习','搜索知识点，运行关联实验，回答针对性问题。学习进度、错题和笔记保存在本机。','知识与学习记录')
        from netlab.content import TOPICS
        self.topics=TOPICS; self.current=None; self.search=line('', '搜索 TCP、Cache、Wi-Fi 7…'); self.category=combo(['全部']+sorted({t['category'] for t in TOPICS})); self.mode=combo(['自由实验','教学引导','挑战模式']); self.list=QListWidget();self.browser=QTextBrowser(); self.browser.setOpenExternalLinks(True);self.answer=QListWidget();self.answer.setMaximumHeight(150);self.note=QPlainTextEdit();self.note.setPlaceholderText('写下你的理解或实验观察');self.note.setMaximumHeight(95);self.progress=label('','muted')
        self.layout.addWidget(row(self.search,self.category,self.mode,button('错题',self.show_mistakes),button('刷新进度',self.update_progress)))
        right=QWidget();l=QVBoxLayout(right);l.setContentsMargins(0,0,0,0);l.addWidget(self.browser,1);l.addWidget(self.answer);l.addWidget(row(button('提交答案',self.submit,True),button('打开关联实验',self.experiment),button('标记已学习',self.complete)));l.addWidget(self.note);l.addWidget(button('保存笔记',self.save_note))
        split=QSplitter();split.addWidget(self.list);split.addWidget(right);split.setSizes([240,780]);self.layout.addWidget(split,1);self.layout.addWidget(self.progress);self.layout.addWidget(self.feedback)
        self.search.textChanged.connect(self.filter);self.category.currentTextChanged.connect(self.filter);self.list.currentItemChanged.connect(self.select);self.mode.currentTextChanged.connect(self.mode_changed);self.filter();self.update_progress()
        self.browser.setOpenLinks(False);self.browser.setOpenExternalLinks(False);self.browser.anchorClicked.connect(self.follow_link)
    def filter(self):
        from netlab.content import search_topics
        self.list.clear();category=None if self.category.currentText()=='全部' else self.category.currentText()
        for t in search_topics(self.search.text(),category):
            item=QListWidgetItem(t['title']);item.setData(Qt.ItemDataRole.UserRole,t['id']);self.list.addItem(item)
        if self.list.count():self.list.setCurrentRow(0)
    def select(self,item,old=None):
        if item is None:return
        from netlab.content import get_topic
        self.current=get_topic(item.data(Qt.ItemDataRole.UserRole));t=self.current;escape=lambda v:html.escape(str(v)).replace('\n','<br>')
        sections=[]
        for k,title in [('concept','概念'),('mechanism','工作过程'),('example','现实例子'),('fields','字段与工具')]:sections.append(f'<h3>{title}</h3><p>{escape(t.get(k,""))}</p>')
        sources=' '.join(f'<a href="{html.escape(str(s if isinstance(s,str) else s.get("url","")),quote=True)}">参考资料 {i+1}</a>' for i,s in enumerate(t.get('sources',[])))
        from netlab.content import get_topic
        related=' · '.join(f'<a href="netlab-topic:{escape(uid)}">{escape(get_topic(uid)["title"])}</a>' for uid in t.get('related',[]))
        if self.mode.currentText()=='挑战模式':sections=[]
        self.browser.setHtml(f'<h1>{escape(t["title"])}</h1>'+''.join(sections)+f'<h3>练习</h3><p>{escape(t.get("question",""))}</p><p>关联：{related}</p><p>{sources}</p>')
        self.answer.clear();self.answer.addItems([str(v) for v in t.get('options',[])]);self.note.clear()
    def submit(self):
        if self.current is None or self.answer.currentRow()<0:return self.status('请选择一个答案',True)
        t=self.current;choice=self.answer.currentRow();correct=choice==t['answer'] if isinstance(t['answer'],int) else self.answer.currentItem().text()==str(t['answer'])
        self.window.db.record_answer(t['id'],choice,correct)
        if correct:self.window.db.set_progress(t['id'],'completed',100)
        self.status(('回答正确。' if correct else '这道题需要复习。')+t.get('explanation',''),not correct);self.update_progress()
    def complete(self):
        if self.current:self.window.db.set_progress(self.current['id'],'completed');self.update_progress();self.status('已记录已学习；练习答题另行评分')
    def update_progress(self):
        p=self.window.db.get_progress();self.progress.setText(f'{len(p)} / {len(self.topics)} 个知识点有学习记录    {len(self.window.db.mistakes())} 条错题记录')
    def save_note(self):
        if self.current and self.note.toPlainText().strip():self.window.db.add_note(self.current['title'],self.note.toPlainText(),self.current['id']);self.status('笔记已保存')
    def show_mistakes(self):
        mistakes=self.window.db.mistakes();ids={m['topic_id'] for m in mistakes};self.list.clear()
        for t in self.topics:
            if t['id'] in ids:item=QListWidgetItem(t['title']);item.setData(Qt.ItemDataRole.UserRole,t['id']);self.list.addItem(item)
        if self.list.count():self.list.setCurrentRow(0)
        self.status(f'当前显示 {len(ids)} 个知识点的错题')
    def experiment(self):
        if self.current:self.window.open_experiment(self.current.get('experiment'),self.current['title'])
    def mode_changed(self):
        self.status({'自由实验':'可以直接编辑参数，自行保存实验结果。','教学引导':'阅读工作过程，打开关联实验，运行后记录笔记。','挑战模式':'先回答问题，再用实验验证；错误答案会保留在错题记录。'}[self.mode.currentText()])
        if self.list.currentItem():self.select(self.list.currentItem())
    def follow_link(self,url):
        text=url.toString()
        if text.startswith('netlab-topic:'):
            from netlab.content import get_topic
            t=get_topic(text.split(':',1)[1]);self.category.setCurrentIndex(0);self.search.setText(t['title'])
        else:
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)

class IntegratedPage(Page):
    def __init__(self,window):
        super().__init__(window,'跨模块综合实验','实验 A–F 连接协议、拓扑、CPU 和操作系统。状态事件来自相应核心引擎，可逐步检查。')
        self.experiment=combo(['A 访问一个网站','B 建立家庭局域网','C 游戏联机','D 网络故障排查','E CPU 发送网络消息','F 网络性能与操作系统']);self.mode=combo(['教学引导','自由实验','挑战模式']);self.seed=spin(1,0,99999);self.output=DataView();self.timeline=Timeline();self.guide=QTextBrowser();self.guide.setMaximumHeight(170);self.layout.addWidget(row(self.experiment,self.mode,label('种子'),self.seed,button('开始综合实验',self.start,True)));self.layout.addWidget(self.guide)
        self.fault_guess=combo(['gateway','link','vlan','dns','route']);self.packet_size=spin(512,64,65535);self.buffer_size=spin(4096,64,1000000);self.io_mode=combo(['interrupt','polling','batch']);self.layout.addWidget(row(label('故障判断'),self.fault_guess,button('提交故障判断',self.answer_fault),button('打开实验工作区',self.workspace)));self.layout.addWidget(row(label('性能：包字节'),self.packet_size,label('缓冲字节'),self.buffer_size,self.io_mode,button('对比包大小与 I/O 策略',self.compare_performance)))
        self.layout.addWidget(tabs(('统一事件',self.timeline),('实验配置与结果',self.output)),1);self.finish();self.experiment.currentIndexChanged.connect(self.describe);self.describe();self.fault=None
    def describe(self):
        from netlab.content import GUIDES
        key='ABCDEF'[self.experiment.currentIndex()];guide=GUIDES.get(key,{}) if isinstance(GUIDES,dict) else next((g for g in GUIDES if g.get('id')==key),{})
        self.guide.setHtml(f'<h2>{html.escape(guide.get("title",key))}</h2><p>{html.escape(guide.get("goal",""))}</p><ol>'+''.join('<li>'+html.escape(s)+'</li>' for s in guide.get('steps',[]))+'</ol>')
    def start(self):
        idx=self.experiment.currentIndex();seed=self.seed.value();self.config={'experiment':'ABCDEF'[idx],'seed':seed,'mode':self.mode.currentText()};self.fault=None
        if idx==0:
            from netlab.core.experiments import website_experiment
            self.perform(lambda:website_experiment('https://example.test',seed=seed),self.show,True)
        elif idx==1:
            from netlab.core.experiments import home_experiment
            self.perform(lambda:home_experiment(seed),self.show_topology,True)
        elif idx==3:
            from netlab.core.experiments import fault_experiment
            self.perform(lambda:fault_experiment('random',seed),self.show_fault,True)
        elif idx==2:
            from netlab.core.experiments import game_experiment
            self.perform(lambda:game_experiment(seed=seed),self.show,True)
        elif idx==4:
            from netlab.systems import cpu_network_experiment
            self.perform(lambda:cpu_network_experiment(seed=seed),self.show,True)
        else:
            from netlab.core.experiments import performance_experiment
            params={'packet_size':self.packet_size.value(),'buffer_size':self.buffer_size.value(),'io_mode':self.io_mode.currentText()};self.config.update(params);self.perform(lambda:performance_experiment(**params),self.show,True)
    def show(self,d):self.output.set_data(d);self.timeline.set_events(d.get('events',[]));self.timeline.step()
    def show_topology(self,d):self.show(d);self.window.pages['topology'].set_config(d['topology'])
    def show_fault(self,d):
        self.fault=d['fault'];self.window.pages['topology'].set_config(d['topology'])
        if self.mode.currentText()=='挑战模式':d={k:v for k,v in d.items() if k not in ('fault','answer')};self.result=d
        self.show(d)
    def answer_fault(self):
        if self.fault is None:return self.status('先开始实验 D，再根据配置与证据判断',True)
        correct=self.fault_guess.currentText()==self.fault;self.window.db.record_answer('diagnostic_order',self.fault_guess.currentText(),correct);self.status('判断正确。可在拓扑工作区修复并重测。' if correct else '判断尚未匹配故障；继续查看局域网 Ping、ARP、链路和路由证据。',not correct)
    def workspace(self):self.window.navigate(['web','topology','game','topology','cpu','os'][self.experiment.currentIndex()])
    def compare_performance(self):
        from netlab.systems import network_pipeline
        size=self.packet_size.value();buffer=self.buffer_size.value();self.config={'bytes_total':min(262144,max(size,4096)*8),'buffer':buffer}
        total=self.config['bytes_total'];sizes=sorted({64,512,size,4096})
        def work():
            comparisons=[]
            for s in sizes:
                if s>buffer:continue
                for mode in ('interrupt','polling'):
                    d=network_pipeline(b'x'*total,packet_size=s,buffer_bytes=buffer,processing=mode);comparisons.append({k:v for k,v in d.items() if k not in ('events','packets')})
            return {'mode':'teaching_simulation','comparisons':comparisons,'total_payload_bytes':total,'note':'相同总载荷，最后一个数据块可以小于包大小；处理成本为教学假设。'}
        self.perform(work,background=True)

class HistoryPage(Page):
    def __init__(self,window):
        super().__init__(window,'实验记录与数据管理','SQLite 自动迁移。备份、分享导出和清除操作都在本机完成。','本地持久化')
        self.table=Table(['ID','模块','名称','保存时间']);self.output=DataView();self.records=[];self.redact=QCheckBox('导出时脱敏地址、MAC、SSID、Cookie 等');self.redact.setChecked(True);self.kind=line('', '按模块筛选');self.layout.addWidget(row(self.kind,button('刷新',self.refresh,True),button('导出备份 JSON',self.backup),button('导入备份',self.restore),button('导出 CSV',self.csv)));self.layout.addWidget(self.redact)
        self.topologies=combo([]);self.layout.addWidget(row(label('已保存拓扑'),self.topologies,button('载入拓扑',self.load_topology),button('全部笔记',self.notes),button('自定义模板',self.templates)))
        self.layout.addWidget(self.table,1);self.layout.addWidget(self.output,1);self.layout.addWidget(row(button('导出选中实验报告',self.selected_report),button('删除选中记录',self.delete_selected),button('清除个人实验数据',self.clear)));self.layout.addWidget(self.feedback);self.table.cellClicked.connect(self.select);self.refresh()
    def refresh(self):
        self.records=self.window.db.list_experiments(self.kind.text() or None);self.table.set_rows([[v['id'],v['kind'],v['name'],v['created']] for v in self.records]);self.saved_topologies=self.window.db.list_topologies();self.topologies.clear()
        for t in self.saved_topologies:self.topologies.addItem(t['name'],t['id'])
    def selected(self):
        rows=self.table.selectionModel().selectedRows()
        if not rows:return None
        uid=self.table.item(rows[0].row(),0).text();return self.window.db.get_experiment(uid)
    def select(self,r,c):
        record=self.selected()
        if record:self.output.set_data(record);self.result=record['result'];self.config=record['config']
    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,'导出 SQLite 数据备份','','JSON (*.json)')
        if path:
            try:self.window.db.export_json(path,redact=self.redact.isChecked());self.status('备份已导出。脱敏备份中的地址不适合恢复可运行拓扑' if self.redact.isChecked() else '原始备份已导出')
            except Exception as exc:self.status(str(exc),True)
    def restore(self):
        path,_=QFileDialog.getOpenFileName(self,'导入数据备份','','JSON (*.json)')
        if path:self.perform(lambda:self.window.db.import_json(path),lambda d:(self.output.set_data(d),self.refresh()))
    def csv(self):
        path,_=QFileDialog.getSaveFileName(self,'导出记录 CSV','','CSV (*.csv)')
        if path:
            try:self.window.db.export_csv(path,redact=self.redact.isChecked());self.status('CSV 已导出')
            except Exception as exc:self.status(str(exc),True)
    def load_topology(self):
        uid=self.topologies.currentData()
        if uid:
            d=self.window.db.load_topology(uid);self.window.pages['topology'].set_config(d['config'] if 'config' in d else d);self.window.navigate('topology')
    def notes(self):self.output.set_data(self.window.db.list_notes())
    def templates(self):
        values=self.window.db.list_templates();self.output.set_data(values)
        if not values:return self.status('在实验页点击“保存为模板”创建自己的模板')
        choices=[str(i+1)+'  '+v['name'] for i,v in enumerate(values)];choice,ok=QInputDialog.getItem(self,'载入模板','选择参数模板',choices,0,False)
        if ok:
            d=values[choices.index(choice)];page=next((p for p in self.window.pages.values() if p.name==d['kind']),None)
            if page:page.apply_config(d['config']);self.window.navigate(next(k for k,p in self.window.pages.items() if p==page))
    def selected_report(self):
        d=self.selected()
        if d:
            from .reports import report_dialog
            report_dialog(self,experiment_id=d['id'])
    def delete_selected(self):
        d=self.selected()
        if d and QMessageBox.question(self,'删除记录','删除这个已保存的实验记录？')==QMessageBox.StandardButton.Yes:self.window.db.delete_experiment(d['id']);self.refresh()
    def clear(self):
        if QMessageBox.question(self,'清除本机记录','将清除本应用的实验、笔记、错题、进度与拓扑。此操作无法撤销。是否继续？')==QMessageBox.StandardButton.Yes:self.output.set_data(self.window.db.clear_personal_data());self.refresh()


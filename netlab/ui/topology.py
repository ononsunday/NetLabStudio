import json
import uuid
from dataclasses import asdict
from PySide6.QtCore import Qt,QTimer,QRectF,QVariantAnimation,QPointF
from PySide6.QtGui import QColor,QPen,QPainter,QFont,QBrush
from PySide6.QtWidgets import QGraphicsObject,QGraphicsScene,QGraphicsLineItem,QGraphicsEllipseItem,QDialog,QVBoxLayout,QDialogButtonBox,QPlainTextEdit,QInputDialog,QFileDialog,QSplitter,QMenu
from .common import Page,DataView,button,label,row,line,dumps
from .network_pages import combo,spin,tabs
from .visuals import ZoomView,Timeline

class DeviceItem(QGraphicsObject):
    def __init__(self,node,page):
        super().__init__(); self.node=node; self.page=page; self.setFlags(self.GraphicsItemFlag.ItemIsMovable|self.GraphicsItemFlag.ItemIsSelectable|self.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(node.get('x',50),node.get('y',50)); self.setToolTip(f"{node['id']} · {node.get('type','pc')}\n双击配置接口与路由")
    def boundingRect(self): return QRectF(0,0,140,86)
    def paint(self,p,option,widget):
        p.setRenderHint(QPainter.RenderHint.Antialiasing); up=self.node.get('up',True)
        col=QColor('#49d8bd' if up else '#ff8798'); p.setPen(QPen(col,3 if self.isSelected() else 1)); p.setBrush(QColor('#1a2a43')); p.drawRoundedRect(self.boundingRect(),9,9)
        p.setPen(col); p.setFont(QFont('Segoe UI',9,QFont.Weight.Bold)); p.drawText(QRectF(10,8,122,18),str(self.node.get('type','pc')).upper())
        p.setPen(QColor('#e7eef8')); p.setFont(QFont('Microsoft YaHei UI',10)); p.drawText(QRectF(10,28,124,20),str(self.node.get('name',self.node['id']))[:15])
        ips=[i.get('ip','') for i in self.node.get('interfaces',[]) if i.get('ip')]
        p.setPen(QColor('#8ca0bc')); p.setFont(QFont('Segoe UI',8)); p.drawText(QRectF(10,55,125,18),(ips[0] if ips else 'L2 / 未配置')[:24])
    def itemChange(self,change,value):
        if change==self.GraphicsItemChange.ItemPositionHasChanged:
            self.node['x']=value.x(); self.node['y']=value.y(); self.page.update_links()
            if self.page.sim and self.node['id'] in self.page.sim.topology.nodes:
                d=self.page.sim.topology.nodes[self.node['id']];d.x=value.x();d.y=value.y()
        return super().itemChange(change,value)
    def mouseDoubleClickEvent(self,event): self.page.edit_node(self.node['id']); event.accept()
    def contextMenuEvent(self,event):
        menu=QMenu(); configure=menu.addAction('设备与接口配置'); failure=menu.addAction('关闭 / 恢复设备'); remove=menu.addAction('删除设备'); act=menu.exec(event.screenPos())
        if act==configure:self.page.edit_node(self.node['id'])
        elif act==failure:
            self.node['up']=not self.node.get('up',True);self.update()
            if self.page.sim:self.page.sim.set_device(self.node['id'],self.node['up']);self.page.status('设备状态已更新，保留模拟队列')
        elif act==remove:self.page.remove_node(self.node['id'])

class PacketItem(QGraphicsEllipseItem):
    def __init__(self,event,page):
        super().__init__(-7,-7,14,14);self.event=event;self.page=page;self.setPen(QPen(QColor('#49d8bd')));self.setBrush(QBrush(QColor('#49d8bd')));self.setZValue(10);self.setToolTip('双击查看当前数据包与封装')
    def mouseDoubleClickEvent(self,event):
        pid=self.event.get('packet_id');packet=self.page.sim.packets.get(pid,self.event) if self.page.sim else self.event;self.page.output.set_data(packet);event.accept()

class TopologyPage(Page):
    def __init__(self,window):
        super().__init__(window,'虚拟网络拓扑','拖动设备，Ctrl 选择两台设备后连接端口。双击设备配置 IP、VLAN、DHCP、NAT 和静态路由。')
        from netlab.core.topology import example_topology
        self.data=example_topology('home'); self.sim=None; self.nodes={}; self.edges=[]; self.events=[]; self.dot=None;self.packet_animation=QVariantAnimation(self);self.packet_animation.setDuration(140);self.animation_slot=None;self.wifi_ap=None
        self.scene=QGraphicsScene(); self.view=ZoomView(self.scene); self.view.setDragMode(self.view.DragMode.RubberBandDrag)
        self.device_type=combo(['pc','laptop','server','switch','router','ap','internet']); self.example=combo(['home','ipv6','vlan','vlan_routed','trunk','routed','fault']); self.source=combo([]); self.target=combo([]); self.protocol=combo(['ICMP','TCP','UDP']); self.payload=line('Hello NetLab'); self.seed=spin(1,0,999999);self.dynamic=combo(['OSPF','RIP','BGP'])
        self.output=DataView(); self.timeline=Timeline(); self.timeline.view.setMinimumHeight(120)
        self.timer=QTimer(self); self.timer.setInterval(180); self.timer.timeout.connect(self.step)
        self.layout.addWidget(row(self.device_type,button('添加设备',self.add_node),button('连接端口',self.connect_ports),button('配置选中项',self.edit_selected),button('平移 / 框选',self.toggle_drag),button('适应画布',self.fit),button('Wi-Fi 关联 / 漫游',self.wifi)))
        self.layout.addWidget(row(self.example,button('载入示例',self.load_example),button('导入配置',self.import_config),button('导出配置',self.export_config),button('编辑完整 JSON',self.edit_all),button('保存拓扑',self.save_topology)))
        self.layout.addWidget(row(self.dynamic,button('计算并安装动态路由',self.configure_routing),label('教学协议计算会写入虚拟路由表；链路改变后可重新计算收敛。','muted')))
        self.layout.addWidget(row(label('来源'),self.source,label('目标'),self.target,self.protocol,self.payload,button('发送虚拟包',self.send,True)))
        self.layout.addWidget(row(button('单步',self.step),button('连续运行',self.timer.start),button('暂停',self.timer.stop),button('重置',self.reset_sim),button('申请 DHCP',self.dhcp),button('快照',self.snapshot),button('恢复快照',self.restore),button('交给协议分析',self.analyze_packets),self.seed))
        split=QSplitter(); split.addWidget(self.view); split.addWidget(tabs(('设备 / 包状态',self.output),('事件时序',self.timeline))); split.setSizes([700,450]); self.layout.addWidget(split,1); self.finish(); self.render(); self.reset_sim()
        self.scene.selectionChanged.connect(self.selection_info)
    def config_dict(self):return json.loads(dumps(self.data))
    def render(self):
        self.packet_animation.stop();self.dot=None
        self.nodes={}; self.edges=[]; self.scene.clear()
        for n in self.data['nodes']:
            item=DeviceItem(n,self); self.nodes[n['id']]=item; self.scene.addItem(item)
        for link in self.data['links']:
            item=QGraphicsLineItem(); item.setZValue(-1); item.setPen(QPen(QColor('#648bbf' if link.get('up',True) else '#ff8798'),2)); item.setData(0,link.get('id')); item.setFlag(item.GraphicsItemFlag.ItemIsSelectable); item.setToolTip(dumps(link)); self.scene.addItem(item); self.edges.append((item,link))
        self.update_links(); self.source.clear(); self.target.clear(); self.source.addItems(list(self.nodes)); self.target.addItems(list(self.nodes))
        if self.target.count()>1:self.target.setCurrentIndex(self.target.count()-1)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-160,-120,160,120)); self.fit()
    def update_links(self):
        for item,link in self.edges:
            a=self.nodes.get(link['a'].split(':')[0]); b=self.nodes.get(link['b'].split(':')[0])
            if a and b:
                x=a.pos();y=b.pos();item.setLine(x.x()+70,x.y()+43,y.x()+70,y.y()+43)
    def fit(self):self.view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
    def toggle_drag(self):
        drag=self.view.DragMode
        self.view.setDragMode(drag.ScrollHandDrag if self.view.dragMode()==drag.RubberBandDrag else drag.RubberBandDrag)
    def load_example(self):
        from netlab.core.topology import example_topology
        self.data=example_topology(self.example.currentText()); self.render(); self.reset_sim()
    def add_node(self):
        kind=self.device_type.currentText(); uid=kind+str(len(self.data['nodes'])+1); n={'id':uid,'name':uid,'type':kind,'x':90+len(self.nodes)*30,'y':100+len(self.nodes)*20,'interfaces':[{'name':'eth0','mac':'02:00:00:'+':'.join(f'{b:02x}' for b in uuid.uuid4().bytes[:3]),'ip':'','vlan':1,'mode':'access','up':True}]}
        self.data['nodes'].append(n);self.render();self.reset_sim()
    def connect_ports(self):
        selected=[i.node for i in self.scene.selectedItems() if isinstance(i,DeviceItem)]
        if len(selected)!=2:return self.status('请 Ctrl 点击选择两台设备',True)
        endpoints=[]
        for n in selected:
            existing=[v['name'] for v in n['interfaces']]; port,ok=QInputDialog.getItem(self,'连接端口',n['name']+' 的端口',existing+['添加新端口'],0,False)
            if not ok:return
            if port=='添加新端口':
                port='eth'+str(len(existing)); n['interfaces'].append({'name':port,'mac':'02:00:00:'+':'.join(f'{b:02x}' for b in uuid.uuid4().bytes[:3]),'ip':'','vlan':1,'mode':'access','up':True})
            endpoints.append(n['id']+':'+port)
        if any(l[k] in endpoints for l in self.data['links'] for k in ('a','b')):return self.status('端口已经连接，请添加新端口',True)
        self.data['links'].append({'id':'link'+str(len(self.data['links'])+1),'a':endpoints[0],'b':endpoints[1],'delay_ms':2,'bandwidth_mbps':100,'loss':0,'up':True,'cost':1});self.render();self.reset_sim()
    def json_editor(self,title,data):
        d=QDialog(self);d.setWindowTitle(title);d.resize(720,570);l=QVBoxLayout(d);l.addWidget(label('字段采用教学拓扑模型。接口 IP 写为 CIDR，如 192.168.1.2/24；路由为 routes 数组。','muted'));edit=QPlainTextEdit(dumps(data));l.addWidget(edit);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject);l.addWidget(buttons)
        if d.exec()==QDialog.DialogCode.Accepted:
            try:return json.loads(edit.toPlainText())
            except Exception as exc:self.status(str(exc),True)
        return None
    def edit_node(self,uid):
        from netlab.core.topology import NetworkSimulator
        n=next(n for n in self.data['nodes'] if n['id']==uid);result=self.json_editor('设备配置 · '+uid,n)
        if result is None:return
        old=self.config_dict();candidate=self.config_dict();candidate['nodes']=[result if v['id']==uid else v for v in candidate['nodes']]
        try:NetworkSimulator.from_dict(candidate,self.seed.value());self.data=candidate;self.render();self.reset_sim()
        except Exception as exc:self.data=old;self.status(str(exc),True)
    def edit_selected(self):
        selected=self.scene.selectedItems()
        if not selected:return self.status('先选择设备或链路',True)
        i=selected[0]
        if isinstance(i,DeviceItem):return self.edit_node(i.node['id'])
        for item,link in self.edges:
            if item==i:
                result=self.json_editor('链路参数与故障',link)
                if result:
                    candidate=self.config_dict();candidate['links']=[result if v.get('id')==link.get('id') else v for v in candidate['links']]
                    try:
                        from netlab.core.topology import NetworkSimulator
                        NetworkSimulator.from_dict(candidate,self.seed.value())
                        same_parameters={k:v for k,v in link.items() if k!='up'}=={k:v for k,v in result.items() if k!='up'}
                        if same_parameters and self.sim:
                            self.sim.set_link(link['id'],result.get('up',True));self.data=candidate;self.render();self.status('链路状态已更新，保留包、表项和事件队列')
                        else:self.data=candidate;self.render();self.reset_sim()
                    except Exception as exc:self.status(str(exc),True)
    def edit_all(self):
        d=self.json_editor('编辑完整拓扑',self.data)
        if d is not None:self.set_config(d)
    def set_config(self,d):
        from netlab.core.topology import NetworkSimulator
        try:NetworkSimulator.from_dict(d,self.seed.value());self.data=d;self.render();self.reset_sim()
        except Exception as exc:self.status(str(exc),True)
    def remove_node(self,uid):
        self.data['nodes']=[n for n in self.data['nodes'] if n['id']!=uid];self.data['links']=[l for l in self.data['links'] if l['a'].split(':')[0]!=uid and l['b'].split(':')[0]!=uid];self.render();self.reset_sim()
    def reset_sim(self):
        from netlab.core.topology import NetworkSimulator
        self.timer.stop();self.events=[];self.timeline.set_events([])
        try:self.sim=NetworkSimulator.from_dict(self.data,self.seed.value());self.output.set_data(self.sim.snapshot());self.status('模拟状态已重置')
        except Exception as exc:self.sim=None;self.status(str(exc),True)
    def send(self):
        if self.sim is None:return self.status('先修正拓扑配置',True)
        try:
            pid=self.sim.send(self.source.currentText(),self.target.currentText(),self.protocol.currentText(),self.payload.text());self.config=self.config_dict();self.output.set_data({'packet_id':pid,'来源':'教学模拟；单步或播放查看转发'});self.status('虚拟包已排入事件队列')
        except Exception as exc:self.status(str(exc),True)
    def step(self):
        if self.sim is None:return
        try:
            e=self.sim.step()
            if e is None:self.timer.stop();self.status('当前队列执行结束');return
            if hasattr(e,'to_dict'):e=e.to_dict()
            self.events.append(e);self.timeline.set_events(self.events);self.timeline.all();self.result=self.sim.snapshot();self.output.set_data(self.result)
            self.animate(e)
        except Exception as exc:self.timer.stop();self.status(str(exc),True)
    def animate(self,e):
        self.packet_animation.stop()
        a=self.nodes.get(str(e.get('source','')).split(':')[0]);b=self.nodes.get(str(e.get('target','')).split(':')[0])
        if self.dot is not None:
            try:self.scene.removeItem(self.dot)
            except RuntimeError:pass
            self.dot=None
        if a:
            self.dot=PacketItem(e,self);self.scene.addItem(self.dot);start=a.pos()+QPointF(70,-9);end=(b.pos() if b else a.pos())+QPointF(70,-9);self.dot.setPos(start);self.packet_animation.setStartValue(start);self.packet_animation.setEndValue(end)
            if self.animation_slot:
                try:self.packet_animation.valueChanged.disconnect(self.animation_slot)
                except RuntimeError:pass
            self.animation_slot=self.dot.setPos;self.packet_animation.valueChanged.connect(self.animation_slot);self.packet_animation.start()
    def wifi(self):
        from netlab.core.services import wifi_associate
        aps=[{'id':n['id'],'x':n.get('x',0),'y':n.get('y',0),'channel':1,'power_dbm':-35} for n in self.data['nodes'] if n['type']=='ap'];n=next((n for n in self.data['nodes'] if n['id']==self.source.currentText()),None)
        if not aps or not n:return self.status('添加至少一个 ap，并在来源选中客户端；拖动位置可比较漫游',True)
        def show(d):self.output.set_data(d);self.wifi_ap=d.get('associated')
        self.perform(lambda:wifi_associate(aps,(n.get('x',0),n.get('y',0)),self.wifi_ap),show)
    def dhcp(self):
        if self.sim is None:return
        source=self.source.currentText();target=self.target.currentText()
        def show(d):
            self.data=self.sim.topology.to_dict();self.render();self.source.setCurrentText(source);self.target.setCurrentText(target);self.output.set_data(d)
        self.perform(lambda:self.sim.request_dhcp(source,target),show)
    def snapshot(self):
        if self.sim is None:return
        self.result=self.sim.snapshot();self.export()
    def restore(self):
        self.timer.stop()
        path,_=QFileDialog.getOpenFileName(self,'恢复实验快照','','JSON (*.json)')
        if not path:return
        try:
            from netlab.core.topology import NetworkSimulator
            with open(path,encoding='utf-8') as f:d=json.load(f)
            snapshot=d.get('result',d);self.timer.stop();self.sim=NetworkSimulator.restore(snapshot);self.data=self.sim.topology.to_dict();self.events=list(self.sim.engine.history);self.render();self.result=snapshot;self.output.set_data(snapshot);self.timeline.set_events(self.events);self.timeline.all();self.status('快照已恢复，处于暂停状态')
        except Exception as exc:self.status(str(exc),True)
    def export_config(self):
        path,_=QFileDialog.getSaveFileName(self,'导出拓扑','','JSON (*.json)')
        if path:
            try:
                with open(path,'w',encoding='utf-8') as f:f.write(dumps(self.config_dict()))
                self.status('拓扑已导出')
            except OSError as exc:self.status(str(exc),True)
    def import_config(self):
        path,_=QFileDialog.getOpenFileName(self,'导入拓扑','','JSON (*.json)')
        if path:
            try:
                with open(path,encoding='utf-8') as f:self.set_config(json.load(f))
            except Exception as exc:self.status(str(exc),True)
    def save_topology(self):
        name,ok=QInputDialog.getText(self,'保存本地拓扑','实验名称',text='我的局域网')
        if ok and name:
            try:self.window.db.save_topology(name,self.config_dict());self.status('已保存本地拓扑')
            except Exception as exc:self.status(str(exc),True)
    def selection_info(self):
        selected=self.scene.selectedItems()
        if selected and isinstance(selected[0],DeviceItem):
            uid=selected[0].node['id'];self.output.set_data(asdict(self.sim.topology.nodes[uid]) if self.sim and uid in self.sim.topology.nodes else selected[0].node)
    def analyze_packets(self):
        if self.sim is None:return
        snapshot=self.sim.snapshot();packets=snapshot.get('packets',{})
        if isinstance(packets,dict):packets=list(packets.values())
        rows=[]
        for i,p in enumerate(packets):
            try:
                from netlab.services.packets import parse_virtual_frame
                frame=parse_virtual_frame(self.sim.packet_bytes(p['id']),i+1);frame['time']=max((e['time'] for e in self.sim.engine.history if e.get('packet_id')==p['id'] and e['kind'] in ('FRAME_SEND','FRAME_RECEIVE','DELIVER')),default=self.sim.engine.time);frame['time_unit']='模拟秒';frame['simulation_state']=p;frame['summary']='虚拟帧 '+frame['summary'];frame['origin_note']='根据虚拟字段重建的教学帧；不是本机实测抓包';rows.append(frame)
            except Exception as exc:rows.append({'index':i+1,'source':p.get('source_ip'),'destination':p.get('destination_ip'),'protocol':p.get('protocol'),'summary':'教学字段模型','fields':p,'error':str(exc)})
        rows.sort(key=lambda r:r.get('time',0))
        for i,r in enumerate(rows):r['index']=i+1
        self.window.pages['capture'].virtual(rows);self.window.navigate('capture')
    def configure_routing(self):
        if self.sim is None:return
        def work():self.config={'topology':self.config_dict(),'protocol':self.dynamic.currentText()};return self.sim.configure_routing(self.dynamic.currentText())
        def show(d):self.data=self.sim.topology.to_dict();self.render();self.output.set_data(d)
        self.perform(work,show)


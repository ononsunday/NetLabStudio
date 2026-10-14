import json
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPen,QBrush,QFont
from PySide6.QtWidgets import QWidget,QVBoxLayout,QSplitter,QPlainTextEdit,QTabWidget,QGraphicsScene,QGraphicsRectItem,QGraphicsTextItem,QInputDialog,QDialog,QDialogButtonBox
from .common import Page,DataView,Table,button,label,row,line,dumps
from .network_pages import spin,decimal,combo,form,tabs
from .visuals import Timeline,ZoomView,LineChart

class GateItem(QGraphicsRectItem):
    def __init__(self,gid,page):
        super().__init__(0,0,110,64);self.gid=gid;self.page=page;self.setData(0,gid)
        self.setFlags(self.GraphicsItemFlag.ItemIsMovable|self.GraphicsItemFlag.ItemIsSelectable|self.GraphicsItemFlag.ItemSendsGeometryChanges)
    def itemChange(self,change,value):
        if change==self.GraphicsItemChange.ItemPositionHasChanged:
            self.page.circuit_data.setdefault('positions',{})[self.gid]={'x':value.x(),'y':value.y()};self.page.update_gate_links()
        return super().itemChange(change,value)
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event);self.page.circuit.setPlainText(dumps(self.page.circuit_data))

class BinaryPage(Page):
    def __init__(self,window):
        super().__init__(window,'二进制与数字逻辑','计算整数编码、补码、溢出、IEEE 754 和逻辑门。电路的输出由门与连接关系计算。','本地计算 / 教学电路')
        self.integer=line('-13'); self.bits=combo(['8','16','32','64']); self.float_value=line('0.1'); self.float_bits=combo(['32','64']); self.op=combo(['ADD','SUB','AND','OR','XOR','NOT','SHL','SHR']); self.a=line('7'); self.b=line('3'); self.output=DataView()
        self.layout.addWidget(row(self.integer,self.bits,button('原码 / 反码 / 补码',self.encode,True),self.float_value,self.float_bits,button('IEEE 754',self.floating)))
        self.layout.addWidget(row(self.op,self.a,self.b,button('ALU 计算',self.calculate)))
        self.circuit=QPlainTextEdit(); self.circuit.setMaximumHeight(150); self.inputs=line('{"a": 1, "b": 0, "cin": 1}')
        self.scene=QGraphicsScene(); self.view=ZoomView(self.scene); self.view.setMinimumHeight(210);self.view.setDragMode(self.view.DragMode.RubberBandDrag);self.gate_items={};self.gate_edges=[];self.circuit_data={}
        self.layout.addWidget(row(label('电路输入 JSON'),self.inputs,button('全加器示例',self.example),button('计算电路',self.evaluate),button('添加逻辑门',self.add_gate),button('连接两个门',self.connect_gates)))
        self.layout.addWidget(tabs(('门与连线画布',self.view),('电路配置 JSON',self.circuit),('计算结果',self.output)),1); self.finish()
        self.example()
    def encode(self):
        from netlab.systems import describe_integer
        def work():
            args={'value':int(self.integer.text(),0),'bits':int(self.bits.currentText())};self.config={'operation':'integer',**args};return describe_integer(**args)
        self.perform(work)
    def floating(self):
        from netlab.systems import describe_float
        def work():
            args={'value':float(self.float_value.text()),'bits':int(self.float_bits.currentText())};self.config={'operation':'float',**args};return describe_float(**args)
        self.perform(work)
    def calculate(self):
        from netlab.systems import alu
        def work():self.config={'op':self.op.currentText(),'a':int(self.a.text(),0),'b':int(self.b.text(),0),'bits':int(self.bits.currentText())};return alu(**self.config)
        self.perform(work)
    def example(self):
        gates={k:{'kind':'INPUT','inputs':[],'value':0} for k in ('a','b','cin')}
        for k,kind,inputs in [('xor1','XOR',['a','b']),('sum','XOR',['xor1','cin']),('and1','AND',['a','b']),('and2','AND',['xor1','cin']),('carry','OR',['and1','and2']),('sum_out','OUTPUT',['sum']),('carry_out','OUTPUT',['carry'])]:gates[k]={'kind':kind,'inputs':inputs,'value':0}
        self.circuit.setPlainText(dumps({'gates':gates,'positions':{}})); self.evaluate()
    def evaluate(self):
        from netlab.systems import LogicCircuit
        def work():
            self.circuit_data=json.loads(self.circuit.toPlainText());self.circuit_data['input_values']=json.loads(self.inputs.text());self.config=self.circuit_data.copy(); c=LogicCircuit.from_dict(self.circuit_data); return c.evaluate(self.circuit_data['input_values'])
        self.perform(work,self.show_circuit)
    def apply_config(self,config):
        if 'gates' in config:
            self.circuit.setPlainText(dumps(config));self.inputs.setText(dumps(config.get('input_values',{k:g.get('value',0) for k,g in config['gates'].items() if g['kind']=='INPUT'})));self.evaluate()
        else:
            super().apply_config(config)
            if 'value' in config:
                is_float=config.get('operation')=='float'
                (self.float_value if is_float else self.integer).setText(str(config['value']))
                (self.float_bits if is_float else self.bits).setCurrentText(str(config.get('bits',32 if is_float else 8)))
    def show_circuit(self,data):
        self.output.set_data(data);self.gate_items={};self.gate_edges=[]; self.scene.clear(); gates=self.circuit_data.get('gates',{});positions=self.gate_items
        for i,(gid,g) in enumerate(gates.items()):
            item=GateItem(gid,self);item.setBrush(QColor('#192c45'));item.setPen(QPen(QColor('#49d8bd'),2));pos=self.circuit_data.get('positions',{}).get(gid,{'x':50+(i%3)*220,'y':55+(i//3)*150});item.setPos(pos['x'],pos['y']);self.scene.addItem(item)
            t=QGraphicsTextItem(f"{gid} · {data.get('values',{}).get(gid,'?')}\n{g.get('kind','')}",item); t.setDefaultTextColor(QColor('#e7eef8')); t.setPos(6,5);item.label=t; positions[gid]=item
        for gid,g in gates.items():
            for source in g.get('inputs',[]):
                if source in positions:
                    a=positions[source].scenePos(); b=positions[gid].scenePos(); link=self.scene.addLine(a.x()+110,a.y()+32,b.x(),b.y()+32,QPen(QColor('#7ca7ff'),2)); link.setZValue(-1);self.gate_edges.append((link,source,gid))
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-25,-25,25,25)); self.view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
    def update_gate_links(self):
        for link,source,target in self.gate_edges:
            a=self.gate_items[source].scenePos();b=self.gate_items[target].scenePos();link.setLine(a.x()+110,a.y()+32,b.x(),b.y()+32)
    def add_gate(self):
        kind,ok=QInputDialog.getItem(self,'添加门','门类型',['AND','OR','NOT','XOR','NAND','NOR'],0,False)
        if not ok:return
        inputs,ok=QInputDialog.getText(self,'门输入','输入节点 ID，以逗号分隔（如 a,b 或 xor1,cin）')
        if not ok:return
        try:
            c=json.loads(self.circuit.toPlainText()); gid='g'+str(len(c['gates'])+1); c['gates'][gid]={'kind':kind,'inputs':[s.strip() for s in inputs.split(',') if s.strip()],'value':0}; self.circuit.setPlainText(dumps(c)); self.evaluate()
        except Exception as exc:self.status(str(exc),True)
    def connect_gates(self):
        selected=[x.data(0) for x in self.scene.selectedItems() if x.data(0)]
        if len(selected)!=2: return self.status('Ctrl 点击选择两个门，再设置连接方向',True)
        source,ok=QInputDialog.getItem(self,'连接方向','选择来源门',selected,0,False)
        if not ok:return
        target=next(x for x in selected if x!=source)
        try:
            c=json.loads(self.circuit.toPlainText()); c['gates'][target]['inputs'][0]=source; self.circuit.setPlainText(dumps(c)); self.evaluate()
        except Exception as exc:self.status(str(exc),True)

class CPUPage(Page):
    def __init__(self,window):
        super().__init__(window,'CPU 与网络应用','16 位教学 CPU。逐条观察 PC、寄存器、标志、内存，以及 SEND 引出的系统调用与 DMA 事件。')
        self.code=QPlainTextEdit('MOV R0, 72\nSTORE 10, R0\nMOV R0, 105\nSTORE 11, R0\nSEND 10, 2\nHALT'); self.code.setTabStopDistance(32)
        self.registers=Table(['寄存器 / 标志','值']); self.memory=Table(['地址','值']); self.output=DataView(); self.timeline=Timeline(); self.cpu=None
        self.layout.addWidget(row(button('汇编 / 重置',self.assemble,True),button('单步',self.step),button('运行',self.run),button('CPU 消息交给虚拟网络',self.network),button('指令集与示例',self.help)))
        split=QSplitter(); split.addWidget(self.code); split.addWidget(tabs(('寄存器',self.registers),('内存',self.memory),('完整状态',self.output),('系统与网络事件',self.timeline))); split.setSizes([350,650]); self.layout.addWidget(split,1); self.finish(); self.assemble()
    def assemble(self):
        from netlab.systems import CPU
        def work():
            self.cpu=CPU(); self.cpu.load(self.code.toPlainText()); self.config={'assembly':self.code.toPlainText()}; return self.cpu.snapshot()
        self.perform(work,self.show)
    def step(self):
        if not self.ensure_current():return
        self.perform(lambda:(self.cpu.step(),self.cpu.snapshot())[1],self.show)
    def run(self):
        if not self.ensure_current():return
        self.perform(lambda:(self.cpu.run(max_steps=1000),self.cpu.snapshot())[1],self.show)
    def ensure_current(self):
        if self.cpu is None or self.cpu.source!=self.code.toPlainText():self.assemble()
        return self.cpu is not None and self.cpu.source==self.code.toPlainText()
    def apply_config(self,config):super().apply_config(config);self.assemble()
    def show(self,d):
        self.output.set_data(d); regs=d.get('registers',{})
        if isinstance(regs,list): regs={f'R{i}':v for i,v in enumerate(regs)}
        self.registers.set_rows([['PC',d.get('pc')]]+[[k,v] for k,v in regs.items()]+[['标志',d.get('flags',{})],['HALT',d.get('halted')]])
        mem=d.get('memory',[]); self.memory.set_rows([[k,v] for k,v in (mem.items() if isinstance(mem,dict) else enumerate(mem))][:256]); self.timeline.set_events(d.get('events',[])); self.timeline.all()
    def network(self):
        from netlab.systems import cpu_network_experiment
        assembly=self.code.toPlainText();topology=self.window.pages['topology'].config_dict();source=self.window.pages['topology'].source.currentText();target=self.window.pages['topology'].target.currentText();self.config={'assembly':assembly,'topology':topology,'source':source,'target':target}
        def show(d):self.show(d['cpu']);self.timeline.set_events(d['events']);self.timeline.step();self.output.set_data(d)
        self.perform(lambda:cpu_network_experiment(assembly,topology,source,target),show,True)
    def help(self): self.output.set_data({'指令':['MOV Rn, 立即数或寄存器','LOAD Rn, 地址','STORE 地址, Rn或立即数','ADD Rn, 值','SUB Rn, 值','JMP 标签','JZ 标签','CMP Rn, 值','SEND 内存地址, 长度','HALT'],'边界':'教学指令集；SEND 只生成模拟消息，不访问本机网卡。'})

class MemoryPage(Page):
    def __init__(self,window):
        super().__init__(window,'Cache 与内存','按组映射计算命中、替换和访问成本。地址以字节为单位，组相联度可调。')
        self.addresses=line('0, 4, 8, 0, 16, 4, 20, 0'); self.lines=spin(4,1,256); self.block=spin(4,1,4096); self.ways=spin(2,1,256); self.policy=combo(['LRU','FIFO']); self.output=DataView(); self.table=Table(['访问','地址','命中','组','块','替换'])
        from netlab.systems.memory import MemoryArena
        self.arena=MemoryArena();self.alloc_size=spin(8,1,128);self.heap_address=line('0');self.stack_value=line('42')
        self.layout.addWidget(row(label('地址序列'),self.addresses,button('运行访问序列',self.simulate,True))); self.layout.addWidget(row(label('Cache 行数'),self.lines,label('块大小'),self.block,label('相联度'),self.ways,self.policy));self.layout.addWidget(row(label('堆分配字节'),self.alloc_size,button('分配',self.malloc),self.heap_address,button('释放地址',self.free),self.stack_value,button('压栈',self.push),button('弹栈',self.pop))); self.layout.addWidget(tabs(('访问记录',self.table),('缓存状态 / 栈与堆',self.output)),1); self.finish()
    def malloc(self):
        self.config={'operation':'malloc','alloc_size':self.alloc_size.value(),'arena_before':self.arena.snapshot()}
        self.perform(lambda:(self.arena.malloc(self.alloc_size.value()),self.arena.snapshot())[1])
    def free(self):
        self.config={'operation':'free','heap_address':self.heap_address.text(),'arena_before':self.arena.snapshot()};self.perform(lambda:(self.arena.free(int(self.heap_address.text(),0)),self.arena.snapshot())[1])
    def push(self):
        self.config={'operation':'push','stack_value':self.stack_value.text(),'arena_before':self.arena.snapshot()};self.perform(lambda:(self.arena.push(int(self.stack_value.text(),0)),self.arena.snapshot())[1])
    def pop(self):
        self.config={'operation':'pop','arena_before':self.arena.snapshot()};self.perform(lambda:{'popped':self.arena.pop(),'memory':self.arena.snapshot()})
    def simulate(self):
        from netlab.systems import Cache
        def work():
            self.config={'addresses':[int(x.strip(),0) for x in self.addresses.text().split(',')],'lines':self.lines.value(),'block_size':self.block.value(),'ways':self.ways.value(),'policy':self.policy.currentText()}; c=Cache(**{k:v for k,v in self.config.items() if k!='addresses'}); return c.run(self.config['addresses'])
        self.perform(work,self.show)
    def show(self,d):
        self.output.set_data(d); accesses=d.get('accesses',d.get('trace',[])); self.table.set_rows([[i,v.get('address'),v.get('hit'),v.get('set',v.get('set_index')),v.get('block'),v.get('evicted')] for i,v in enumerate(accesses)])

class OSPage(Page):
    def __init__(self,window):
        super().__init__(window,'操作系统与网络 I/O','调度、分页与网络收发共用可检查的模拟事件；处理时延和 CPU 成本由参数计算。')
        self.algorithm=combo(['FCFS','SJF','RR','PRIORITY']); self.quantum=spin(2,1,100); self.processes=QPlainTextEdit(dumps([{'pid':'client','arrival':0,'cpu_bursts':[2,3],'io_bursts':[2]},{'pid':'server','arrival':1,'burst':3},{'pid':'logger','arrival':2,'burst':2}])); self.processes.setMaximumHeight(150)
        self.refs=line('1,2,3,1,4,2,5,1'); self.frames=spin(3,1,100); self.replacement=combo(['LRU','FIFO','OPT']); self.payload=line('Hello from application'); self.packet_size=spin(512,1,65535); self.buffer_size=spin(4096,1,1000000); self.processing=combo(['interrupt','polling']); self.bandwidth=decimal(100,.01,10000)
        self.output=DataView(); self.timeline=Timeline(); self.layout.addWidget(row(self.algorithm,label('时间片'),self.quantum,button('进程调度',self.schedule,True))); self.layout.addWidget(self.processes)
        self.layout.addWidget(row(label('页面访问'),self.refs,self.frames,self.replacement,button('页面置换',self.pages)))
        self.layout.addWidget(row(self.payload,label('包字节'),self.packet_size,label('缓冲字节'),self.buffer_size,self.processing)); self.layout.addWidget(row(label('带宽 / Mbps'),self.bandwidth,button('CPU → Socket → DMA → 网络',self.pipeline)))
        self.layout.addWidget(tabs(('状态与指标',self.output),('进程与 I/O 事件',self.timeline)),1); self.finish()
    def schedule(self):
        from netlab.systems import schedule_processes
        def work():self.config={'processes':json.loads(self.processes.toPlainText()),'algorithm':self.algorithm.currentText(),'quantum':self.quantum.value()};return schedule_processes(**self.config)
        self.perform(work,self.show)
    def pages(self):
        from netlab.systems import page_replacement
        def work():self.config={'references':[int(s.strip()) for s in self.refs.text().split(',')],'frames':self.frames.value(),'policy':self.replacement.currentText()};return page_replacement(**self.config)
        self.perform(work,self.show)
    def pipeline(self):
        from netlab.systems import network_pipeline
        self.config={'payload':self.payload.text(),'packet_size':self.packet_size.value(),'buffer_bytes':self.buffer_size.value(),'processing':self.processing.currentText(),'bandwidth_mbps':self.bandwidth.value()}
        self.perform(lambda:network_pipeline(**self.config),self.show)
    def show(self,d): self.output.set_data(d); self.timeline.set_events(d.get('events',[])); self.timeline.step()



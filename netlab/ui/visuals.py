import math
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPen,QBrush,QColor,QPainter,QFont
from PySide6.QtWidgets import QWidget,QGraphicsView,QGraphicsScene,QVBoxLayout,QHBoxLayout,QSlider,QLabel
from .common import button,label,row,Table,DataView

class ZoomView(QGraphicsView):
    def __init__(self,scene=None):
        super().__init__(scene); self.setRenderHint(QPainter.RenderHint.Antialiasing); self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag); self.setBackgroundBrush(QColor('#101a2b'))
    def wheelEvent(self,event):
        factor=1.15 if event.angleDelta().y()>0 else 1/1.15
        scale=self.transform().m11()
        if .15<scale*factor<5: self.scale(factor,factor)
        event.accept()

class Timeline(QWidget):
    def __init__(self):
        super().__init__(); self.events=[]; self.cursor=0; self.actors=[]
        self.scene=QGraphicsScene(); self.view=ZoomView(self.scene); self.view.setMinimumHeight(220)
        self.table=Table(['时间','事件','来源','目标','解释']); self.table.setMaximumHeight(190)
        self.detail=DataView(); self.detail.setMaximumHeight(200); self.detail.hide()
        self.timer=QTimer(self); self.timer.setInterval(250); self.timer.timeout.connect(self.step)
        self.pos=label('0 / 0','muted'); self.speed=QSlider(Qt.Orientation.Horizontal); self.speed.setRange(25,1000); self.speed.setValue(250); self.speed.valueChanged.connect(self.timer.setInterval); self.speed.setMaximumWidth(150)
        self.layout=QVBoxLayout(self); self.layout.setContentsMargins(0,0,0,0)
        self.layout.addWidget(row(button('播放',self.play,True),button('暂停',self.timer.stop),button('单步',self.step),button('重置',self.reset),button('全部',self.all),self.pos,label('每步 ms'),self.speed))
        self.layout.addWidget(self.view,1); self.layout.addWidget(self.table); self.layout.addWidget(self.detail)
        self.table.cellClicked.connect(self.select_event)
    def set_events(self,events):
        self.timer.stop(); self.events=[dict(x) for x in events]; self.cursor=0
        self.actors=list(dict.fromkeys(str(e.get(k,'')) for e in self.events for k in ['source','target'] if e.get(k)))[:14]
        if not self.actors: self.actors=['应用','协议栈','网络']
        self.draw()
    def play(self):
        if self.cursor>=len(self.events): self.cursor=0
        self.timer.start()
    def step(self):
        if self.cursor<len(self.events): self.cursor+=1; self.draw()
        else: self.timer.stop()
    def reset(self): self.timer.stop(); self.cursor=0; self.draw()
    def all(self): self.timer.stop(); self.cursor=len(self.events); self.draw()
    def draw(self):
        self.scene.clear(); actors=self.actors or ['应用','网络']; width=max(620,len(actors)*155); count=min(self.cursor,220); height=max(240,count*49+85)
        self.scene.setSceneRect(0,0,width,height)
        xs={a:80+i*(width-160)/max(1,len(actors)-1) for i,a in enumerate(actors)}
        for a,x in xs.items():
            t=self.scene.addText(a[:20],QFont('Microsoft YaHei UI',10)); t.setDefaultTextColor(QColor('#e7eef8')); t.setPos(x-35,10)
            self.scene.addLine(x,45,x,height,QPen(QColor('#344967'),1,Qt.PenStyle.DashLine))
        offset=max(0,self.cursor-220)
        for i,e in enumerate(self.events[offset:self.cursor]):
            y=75+i*49; s=xs.get(str(e.get('source')),80); local=not e.get('target') or e.get('target')==e.get('source'); d=s if local else xs.get(str(e.get('target')),width-80)
            col=QColor('#ff8798' if any(v in str(e.get('kind','')).lower() for v in ['drop','loss','error','timeout']) else '#49d8bd')
            if local:self.scene.addEllipse(s-4,y-4,8,8,QPen(col,2),QBrush(col))
            else:
                self.scene.addLine(s,y,d,y,QPen(col,2));direction=1 if d>=s else -1
                self.scene.addLine(d,y,d-direction*8,y-5,QPen(col,2)); self.scene.addLine(d,y,d-direction*8,y+5,QPen(col,2))
            stamp=e.get('time',e.get('time_ms',0));stamp=f'{stamp:.6f}' if isinstance(stamp,(int,float)) else str(stamp)
            fields=e.get('data') or {};caption=str(e.get('kind',e.get('type','event')))
            if isinstance(fields,dict):
                if fields.get('flag'):caption+=' '+str(fields['flag'])
                elif fields.get('to'):caption+=' '+str(fields['to'])
            t=self.scene.addText(f"{stamp}  {caption}"[:65],QFont('Segoe UI',9)); t.setDefaultTextColor(col); t.setPos(min(min(s,d)+6,width-t.boundingRect().width()-12),y-25)
        visible=self.events[:self.cursor]
        self.table.set_rows([[e.get('time',e.get('time_ms',0)),e.get('kind',e.get('type','')),e.get('source',''),e.get('target',''),e.get('explanation',e.get('description',''))] for e in visible[-200:]])
        self.pos.setText(f'{self.cursor} / {len(self.events)}')
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
    def select_event(self,r,c):
        values=self.events[max(0,self.cursor-200):self.cursor]
        # Table sorting can change row order, so identify by the complete displayed tuple.
        vals=[self.table.item(r,i).text() for i in range(4)]
        match=next((e for e in values if [str(e.get('time',e.get('time_ms',0))),str(e.get('kind',e.get('type',''))),str(e.get('source','')),str(e.get('target',''))]==vals),None)
        if match: self.detail.show(); self.detail.set_data(match)

class LineChart(QWidget):
    def __init__(self,title='延迟 / ms'):
        super().__init__(); self.series=[]; self.title=title; self.setMinimumHeight(170)
    def set_series(self,values,title=None):
        self.series=values[-300:]
        if title: self.title=title
        self.update()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.fillRect(self.rect(),QColor('#101a2b'))
        w,h=self.width(),self.height(); p.setPen(QColor('#8ca0bc')); p.drawText(14,24,self.title)
        values=[float(v) for v in self.series if v is not None]
        if not values: p.drawText(14,55,'运行实验后显示计算结果'); return
        lo,hi=min(0,min(values)),max(values)
        if hi==lo: hi=lo+1
        for i in range(4):
            y=45+(h-70)*i/3; p.setPen(QPen(QColor('#2a3c55'),1)); p.drawLine(48,int(y),w-18,int(y)); p.setPen(QColor('#8ca0bc')); p.drawText(4,int(y)+4,f'{hi-(hi-lo)*i/3:.1f}')
        p.setPen(QPen(QColor('#49d8bd'),2)); previous=None
        for i,v in enumerate(self.series):
            if v is None: previous=None; continue
            xy=(48+(w-66)*i/max(1,len(self.series)-1),45+(h-70)*(hi-float(v))/(hi-lo))
            if previous: p.drawLine(int(previous[0]),int(previous[1]),int(xy[0]),int(xy[1]))
            p.drawEllipse(int(xy[0])-2,int(xy[1])-2,4,4); previous=xy
        p.end()

class GameArena(QWidget):
    def __init__(self):
        super().__init__();self.frames=[];self.index=0;self.setMinimumHeight(220);self.timer=QTimer(self);self.timer.setInterval(50);self.timer.timeout.connect(self.advance)
    def set_frames(self,frames):
        self.frames=frames;self.index=0;self.timer.start();self.update()
    def advance(self):
        if self.index<len(self.frames)-1:self.index+=1;self.update()
        else:self.timer.stop()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor('#101a2b'))
        if not self.frames:p.setPen(QColor('#8ca0bc'));p.drawText(20,35,'运行联机实验后，使用计算出的玩家位置播放同步过程');return
        f=self.frames[self.index];values=[float(v.get('true',0)) for v in self.frames];lo=min(0,min(values));hi=max(1,max(values));w=self.width()
        for i,(key,name,color) in enumerate([('true','真实位置','#e7eef8'),('predicted','客户端预测','#49d8bd'),('server','服务器确认','#7ca7ff'),('interpolated','客户端插值','#ffba74')]):
            y=45+i*47;p.setPen(QColor('#2a3c55'));p.drawLine(135,y,w-25,y);p.setPen(QColor(color));p.drawText(12,y+5,name);x=135+(w-170)*(float(f.get(key,0))-lo)/(hi-lo);p.setBrush(QColor(color));p.drawEllipse(int(x)-7,y-7,14,14)
        p.setPen(QColor('#8ca0bc'));p.drawText(12,self.height()-8,f"模拟 t={f.get('time',0):.3f}    预测误差={f.get('prediction_error',0):.3f}");p.end()


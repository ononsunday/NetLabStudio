"""Real Qt widget interactions against local engines and loopback services."""
import time
import pytest
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from netlab.storage import Database
from netlab.ui.window import MainWindow,NAV

@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def window(qapp,tmp_path):
    w=MainWindow(Database(tmp_path/'ui.sqlite3'),tmp_path);w.show();qapp.processEvents()
    yield w
    deadline=time.monotonic()+30
    while w.jobs and time.monotonic()<deadline:qapp.processEvents();QTest.qWait(20)
    w.close();qapp.processEvents()

def wait_jobs(w,timeout=30):
    deadline=time.monotonic()+timeout
    while w.jobs and time.monotonic()<deadline:QApplication.processEvents();QTest.qWait(20)
    assert not w.jobs,'background task did not finish'

def click(page,text):
    b=next(b for b in page.findChildren(QPushButton) if b.text()==text)
    QTest.mouseClick(b,Qt.MouseButton.LeftButton);QApplication.processEvents()

def test_all_native_pages_and_theme(window):
    for i,(key,_) in enumerate(NAV):
        window.navigate(key);QApplication.processEvents();assert window.stack.currentIndex()==i;assert window.pages[key].isVisible()
    window.theme();assert window.db.get_setting('light_theme') is True
    window.theme();assert window.db.get_setting('light_theme') is False
    window.learn('TCP');assert window.pages['learning'].list.count()>0

def test_subnet_error_and_ipv6(window):
    p=window.pages['subnet'];window.navigate('subnet');p.cidr.setText('192.168.10.37/24');click(p,'解析地址');assert p.result['network']=='192.168.10.0'
    p.cidr.setText('2001:db8::12/64');click(p,'解析地址');assert p.result['broadcast'] is None;assert p.bits.rowCount()==4
    p.cidr.setText('broken');click(p,'解析地址');assert 'Error' in p.feedback.text()

def test_system_interactions_and_save(window):
    p=window.pages['cpu'];window.navigate('cpu');click(p,'运行');assert p.result['halted'];assert p.result['sent_messages'][0]['payload_hex']=='4869';click(p,'保存实验');assert len(window.db.list_experiments())==1
    binary=window.pages['binary'];window.navigate('binary');click(binary,'计算电路');assert binary.result['outputs']['sum_out']==0;assert binary.result['outputs']['carry_out']==1
    m=window.pages['memory'];window.navigate('memory');click(m,'运行访问序列');assert m.result['hits']+m.result['misses']==8
    o=window.pages['os'];window.navigate('os');click(o,'进程调度');assert o.result.get('events');click(o,'页面置换');assert o.result.get('faults',o.result.get('page_faults',0))>0;click(o,'CPU → Socket → DMA → 网络');assert o.result['cpu_cycles']>0

def test_topology_execution_and_virtual_analysis(window):
    p=window.pages['topology'];window.navigate('topology');p.source.setCurrentText('PC1');p.target.setCurrentText('WEB');click(p,'发送虚拟包')
    for _ in range(200):
        if not p.sim.engine.queue:break
        p.step()
    assert p.sim.stats['delivered']>0;assert p.events
    click(p,'交给协议分析');c=window.pages['capture'];assert c.packets;assert any(x.get('hex') for x in c.packets);assert window.stack.currentWidget()==c

def test_transport_background_and_parameters(window):
    p=window.pages['transport'];window.navigate('transport');p.loss.setValue(0);click(p,'运行协议实验');wait_jobs(window);assert p.result['events'];assert p.chart.series
    p.loss.setValue(1);click(p,'运行协议实验');wait_jobs(window);assert p.result['metrics']['success'] is False

def test_actual_local_https_ui(window):
    p=window.pages['web'];window.navigate('web');click(p,'启动本地 HTTPS');wait_jobs(window);assert p.local_ca;assert p.target.text().startswith('https://127.0.0.1:')
    click(p,'执行指定目标请求');wait_jobs(window);assert p.result['ok'];assert p.result['details']['status']==200

def test_editor_executes_and_c_templates_distinct(window):
    p=window.pages['programming'];window.navigate('programming');p.load_template();assert 'socket' in p.code.toPlainText();click(p,'运行代码');wait_jobs(window);assert p.result['returncode']==0
    p.language.setCurrentText('C');assert p.template.count()==2;assert '#include' in p.code.toPlainText()

def test_learning_answer_records_progress(window):
    p=window.pages['learning'];window.navigate('learning');p.search.setText('TCP');assert p.current
    answer=p.current['answer'];i=answer if isinstance(answer,int) else next(i for i in range(p.answer.count()) if p.answer.item(i).text()==str(answer));p.answer.setCurrentRow(i);click(p,'提交答案');assert window.db.get_progress(p.current['id'])


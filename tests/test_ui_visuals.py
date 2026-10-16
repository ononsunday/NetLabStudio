"""A local state change must not be drawn as a transmitted packet."""
from PySide6.QtWidgets import QApplication,QGraphicsEllipseItem,QGraphicsLineItem,QGraphicsTextItem
from netlab.ui.visuals import Timeline

def test_local_protocol_state_has_marker_and_formatted_label():
    app=QApplication.instance() or QApplication([])
    timeline=Timeline()
    timeline.set_events([{'time':0.026375642,'kind':'TCP_STATE','source':'server','target':'','data':{'to':'SYN_RECEIVED'}}])
    timeline.all()
    items=timeline.scene.items()
    assert sum(isinstance(item,QGraphicsEllipseItem) for item in items)==1
    assert sum(isinstance(item,QGraphicsLineItem) for item in items)==1  # Actor lifeline only.
    assert any('0.026376' in item.toPlainText() and 'SYN_RECEIVED' in item.toPlainText() for item in items if isinstance(item,QGraphicsTextItem))
    timeline.close();timeline.deleteLater();app.processEvents()

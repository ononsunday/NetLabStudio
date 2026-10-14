from PySide6.QtGui import QColor, QPalette

DARK = {"bg": "#0c1220", "panel": "#131d2f", "card": "#19263b", "line": "#2a3c55", "text": "#e7eef8", "muted": "#8ca0bc", "accent": "#49d8bd", "blue": "#7ca7ff", "error": "#ff8798"}
LIGHT = {"bg": "#eef3f8", "panel": "#ffffff", "card": "#e5edf6", "line": "#c3d1e1", "text": "#17283e", "muted": "#50637c", "accent": "#007e6c", "blue": "#345dc4", "error": "#ad2342"}

def apply_theme(app, light=False):
    c = LIGHT if light else DARK
    p = QPalette()
    for role, key in [(QPalette.ColorRole.Window,"bg"),(QPalette.ColorRole.WindowText,"text"),(QPalette.ColorRole.Base,"panel"),(QPalette.ColorRole.AlternateBase,"card"),(QPalette.ColorRole.Text,"text"),(QPalette.ColorRole.Button,"card"),(QPalette.ColorRole.ButtonText,"text"),(QPalette.ColorRole.Highlight,"blue"),(QPalette.ColorRole.HighlightedText,"bg")]:
        p.setColor(role, QColor(c[key]))
    app.setPalette(p)
    app.setStyleSheet(f"""
    QWidget {{ font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; color: {c['text']}; }}
    QMainWindow, QStackedWidget, QWidget#page {{ background: {c['bg']}; }}
    QFrame#sidebar, QFrame#inspector, QFrame#topbar {{ background: {c['panel']}; }}
    QLabel#brand {{ font-size: 22px; font-weight: 700; color: {c['accent']}; }}
    QLabel#pageTitle {{ font-size: 27px; font-weight: 700; }}
    QLabel#subtitle, QLabel#muted {{ color: {c['muted']}; }}
    QLabel#sectionTitle {{ font-size: 17px; font-weight: 600; }}
    QLabel#badge {{ color: {c['accent']}; background: {c['card']}; padding: 5px 9px; border-radius: 6px; }}
    QPushButton {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 6px; padding: 7px 12px; min-height: 20px; }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton:pressed {{ background: {c['line']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton#primary {{ background: {c['accent']}; color: {c['bg']}; font-weight: 600; border: none; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {c['panel']}; border: 1px solid {c['line']}; border-radius: 5px; padding: 7px; min-height: 20px; }}
    QPlainTextEdit, QTextBrowser, QTreeWidget, QTableWidget, QListWidget {{ background: {c['panel']}; border: 1px solid {c['line']}; border-radius: 6px; selection-background-color: {c['line']}; }}
    QListWidget#navigation {{ background: transparent; border: none; outline: none; }}
    QListWidget#navigation::item {{ padding: 11px 10px; margin: 2px 5px; border-radius: 6px; }}
    QListWidget#navigation::item:selected {{ color: {c['accent']}; background: {c['card']}; border-left: 3px solid {c['accent']}; }}
    QHeaderView::section {{ background: {c['card']}; border: none; padding: 8px; color: {c['muted']}; }}
    QTabWidget::pane {{ border: 1px solid {c['line']}; border-radius: 6px; }}
    QTabBar::tab {{ padding: 10px 16px; background: {c['panel']}; color: {c['muted']}; }}
    QTabBar::tab:selected {{ color: {c['accent']}; border-bottom: 2px solid {c['accent']}; }}
    QSplitter::handle {{ background: {c['line']}; width: 1px; }}
    QScrollBar:vertical {{ background: {c['bg']}; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {c['line']}; border-radius: 4px; min-height: 25px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QStatusBar {{ background: {c['panel']}; color: {c['muted']}; }}
    QToolTip {{ background: {c['card']}; border: 1px solid {c['line']}; padding: 5px; }}
    QGroupBox {{ border: 1px solid {c['line']}; border-radius: 6px; margin-top: 15px; padding-top: 15px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; color: {c['muted']}; }}
    """)
    return c

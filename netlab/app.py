import argparse
import json
import logging
import os
import sys
from pathlib import Path

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir');parser.add_argument('--quit-after',type=float,default=0);parser.add_argument('--screenshot');parser.add_argument('--page',default='home');parser.add_argument('--verify',metavar='RESULT_JSON',help='Run bounded loopback and model verification, write evidence, then close');args=parser.parse_args(argv)
    data_dir=Path(args.data_dir) if args.data_dir else Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))/'NetLabStudio';data_dir.mkdir(parents=True,exist_ok=True)
    from logging.handlers import RotatingFileHandler
    handler=RotatingFileHandler(data_dir/'netlab.log',maxBytes=2_000_000,backupCount=3,encoding='utf-8');handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));logger=logging.getLogger('netlab');logger.setLevel(logging.INFO);logger.addHandler(handler)
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont
    app=QApplication.instance() or QApplication(sys.argv[:1]);app.setApplicationName('NetLab Studio');app.setOrganizationName('NetLabStudio');app.setStyle('Fusion');app.setFont(QFont('Microsoft YaHei UI',10))
    def exception(kind,value,tb):
        logger.error('UI exception',exc_info=(kind,value,tb));QMessageBox.critical(None,'NetLab Studio',f'{kind.__name__}: {value}\n实验记录仍保存在本机。详情见日志。')
    sys.excepthook=exception
    from netlab.storage import Database
    from netlab.ui.window import MainWindow
    db=Database(data_dir/'netlab.sqlite3');window=MainWindow(db,data_dir);window.show();window.navigate(args.page)
    verification_status=[0]
    if args.verify:
        from netlab.verification import run_verification
        result_path=Path(args.verify).resolve();result_path.parent.mkdir(parents=True,exist_ok=True)
        def verified(data):
            result_path.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            verification_status[0]=0 if data.get('ok') else 1
            window.navigate('history');window.pages['history'].output.set_data(data)
            if args.screenshot:
                QTimer.singleShot(100,lambda:window.grab().save(str(Path(args.screenshot))))
            QTimer.singleShot(300,window.close)
        def verification_error(message):verified({'ok':False,'error':message,'checks':[]})
        QTimer.singleShot(0,lambda:window.run_job(lambda:run_verification(result_path.parent/'verify-work'),verified,verification_error))
    if args.screenshot:
        path=Path(args.screenshot);path.parent.mkdir(parents=True,exist_ok=True);QTimer.singleShot(800,lambda:window.grab().save(str(path)))
    if args.quit_after:QTimer.singleShot(int(args.quit_after*1000),window.close)
    code=app.exec();return code or verification_status[0]


from PySide6.QtWidgets import QDialog,QVBoxLayout,QLineEdit,QPlainTextEdit,QCheckBox,QDialogButtonBox,QFileDialog
from .common import label

def report_dialog(page,experiment_id=None):
    dialog=QDialog(page);dialog.setWindowTitle('实验报告');dialog.resize(640,380);l=QVBoxLayout(dialog);l.addWidget(label('报告包含实验目标、配置、运行证据与个人总结。默认隐藏地址与敏感字段。'))
    summary=QPlainTextEdit();summary.setPlaceholderText('个人总结：本次观察到了什么？哪些结论仍需验证？');l.addWidget(summary);redact=QCheckBox('分享报告脱敏');redact.setChecked(True);l.addWidget(redact);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);l.addWidget(buttons)
    if dialog.exec()!=QDialog.DialogCode.Accepted:return
    path,_=QFileDialog.getSaveFileName(page,'保存可编辑 Markdown 报告','','Markdown (*.md)')
    if not path:return
    try:
        uid=experiment_id or page.window.db.save_experiment(page.name,page.name,page.config,page.result)
        text=page.window.db.report_markdown(uid,summary.toPlainText(),redact.isChecked())
        with open(path,'w',encoding='utf-8') as f:f.write(text)
        page.status('报告已生成：'+path)
    except Exception as exc:page.status(str(exc),True)


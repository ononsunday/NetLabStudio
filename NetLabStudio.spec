# Native Qt portable Windows build. No console window or administrator manifest.
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules
from pathlib import Path
import os

root = Path(SPECPATH)
datas = [(str(root / 'examples'), 'examples'), (str(root / 'docs'), 'docs'), (str(root / 'README.md'), '.')]
for name in ['scapy','dnspython','httpx','httpcore','h2','hpack','hyperframe','idna','certifi','anyio','aioquic','asyncssh','websockets','cryptography','psutil']:
    datas += copy_metadata(name)
datas += collect_data_files('certifi')
a = Analysis(['main.py'], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=collect_submodules('dns.rdtypes') + collect_submodules('scapy.layers') + ['scapy.arch.windows'],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['PySide6.QtWebEngineWidgets','PySide6.QtWebEngineCore','PySide6.QtQml','PySide6.QtQuick','PySide6.Qt3DCore','tkinter','matplotlib','numpy','pandas'],
             noarchive=False)
# Qt uses Windows' unversioned ICU API. A Poppler directory on PATH can cause
# bindepend to collect an incompatible ICU whose exports end in _78.
# Leave Windows system libraries in the OS rather than shipping that DLL.
if os.name == 'nt':
    a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.casefold() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='NetLabStudio', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          disable_windowed_traceback=False, uac_admin=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='NetLabStudio')

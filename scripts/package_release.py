"""Assemble the complete portable directory and source archive, without user data."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PORTABLE_README='''# NetLab Studio · Windows 便携版

双击 `NetLabStudio.exe` 启动。请保留整个文件夹，特别是 `_internal`，不能只复制 EXE。

软件普通账户即可启动。个人记录存储在 `%LOCALAPPDATA%\\NetLabStudio`；无需 Npcap 即可使用教学实验和导入抓包。实时抓包需要另行安装 Npcap 并取得对应权限。

- [中文操作指南](_internal/docs/USER_GUIDE.md)
- [功能及限制](_internal/docs/FEATURES.md)
- [实际验证记录](_internal/docs/VALIDATION.md)
- [完整项目说明](_internal/README.md)
- [依赖许可证](_internal/docs/licenses/README.md)

示例位于 `_internal/examples`。它们都是明确标注的教学数据。内置 Python 示例使用随软件运行的独立子进程，无需另装解释器；C 示例需要可用的编译器。额外 Python 包需要源码环境。
'''

def make_zip(target,files):
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for absolute,relative in sorted(files,key=lambda pair:pair[1]):archive.write(absolute,relative)
    with zipfile.ZipFile(target) as archive:
        bad=archive.testzip()
        if bad:raise RuntimeError('ZIP integrity failure: '+bad)
        forbidden=[p for p in archive.namelist() if p.endswith(('.sqlite3','.sqlite3-wal','.sqlite3-shm','.key','.log')) or p.endswith('.pem') and not p.endswith('/certifi/cacert.pem')]
        if forbidden:raise RuntimeError('Personal/runtime files were found: '+str(forbidden))
    return {'file':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}

def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    portable=ROOT/'dist'/'NetLabStudio'
    if not (portable/'NetLabStudio.exe').is_file():raise FileNotFoundError('Build NetLabStudio.spec first')
    internal=portable/'_internal'
    for folder in ('docs','examples'):shutil.copytree(ROOT/folder,internal/folder,dirs_exist_ok=True)
    shutil.copy2(ROOT/'README.md',internal/'README.md')
    shutil.copy2(ROOT/'requirements-lock.txt',portable/'requirements-lock.txt')
    (portable/'README.md').write_text(PORTABLE_README,encoding='utf-8')
    output=ROOT/'releases';output.mkdir(exist_ok=True)
    packaged=[(p,'NetLabStudio/'+p.relative_to(portable).as_posix()) for p in portable.rglob('*') if p.is_file()]
    runtime_files=[p for p,_ in packaged if p.suffix.casefold() in ('.sqlite3','.key','.log') or p.suffix.casefold()=='.pem' and p!=internal/'certifi'/'cacert.pem']
    if runtime_files:raise RuntimeError('Remove runtime files from the portable directory first')
    result=[make_zip(output/'NetLabStudio-1.0.0-Windows-x64.zip',packaged)]
    folders={'netlab','tests','examples','docs','scripts'}
    roots={'main.py','README.md','pyproject.toml','requirements.txt','requirements-lock.txt','NetLabStudio.spec','Launch_NetLab.cmd','Setup_NetLab.cmd','Build_Windows.cmd','Run_Tests.cmd','.gitignore'}
    source=[]
    for p in ROOT.rglob('*'):
        relative=p.relative_to(ROOT)
        if relative.parts[0] not in folders and str(relative) not in roots:continue
        if '__pycache__' in relative.parts or p.suffix=='.pyc' or not p.is_file():continue
        source.append((p,'NetLabStudio/'+relative.as_posix()))
    result.append(make_zip(output/'NetLabStudio-1.0.0-Source.zip',source))
    (output/'SHA256.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

import json
from pathlib import Path
import sys

import pytest

from netlab.exercise_runner import run_exercise


def paths(tmp_path, code):
    source=tmp_path/"exercise.py"
    source.write_text(code,encoding="utf-8")
    return source,tmp_path/"out.log",tmp_path/"err.log"


def test_runner_utf8_output_main_and_argument_restore(tmp_path):
    source,out,err=paths(tmp_path,"import sys\nassert __name__=='__main__'\nassert len(sys.argv)==1\nprint('实际输出：你好')\nprint('错误通道：证据',file=sys.stderr)")
    previous=(sys.stdout,sys.stderr,sys.argv)
    assert run_exercise(source,out,err)==0
    assert out.read_text(encoding="utf-8")=="实际输出：你好\n"
    assert err.read_text(encoding="utf-8")=="错误通道：证据\n"
    assert (sys.stdout,sys.stderr,sys.argv)==previous


def test_runner_real_traceback(tmp_path):
    source,out,err=paths(tmp_path,"print('before failure')\nraise ValueError('真正失败')")
    assert run_exercise(source,out,err)==1
    assert out.read_text(encoding="utf-8")=="before failure\n"
    evidence=err.read_text(encoding="utf-8")
    assert "Traceback" in evidence and "ValueError: 真正失败" in evidence
    assert str(source) in evidence


@pytest.mark.parametrize("code,expected,error",[("None",0,""),("0",0,""),("1",1,""),("7",7,""),("'停止原因'",1,"停止原因\n")])
def test_runner_system_exit_semantics(tmp_path,code,expected,error):
    source,out,err=paths(tmp_path,"import sys\nsys.exit("+code+")")
    assert run_exercise(source,out,err)==expected
    assert err.read_text(encoding="utf-8")==error


def test_runner_source_size_bound(tmp_path):
    source,out,err=paths(tmp_path,"#"*(1024*1024+1))
    assert run_exercise(source,out,err)==1
    assert "1 MiB" in err.read_text(encoding="utf-8")


def test_bundled_dispatch_protocol_executes_headless_child(tmp_path,monkeypatch):
    # Use the source launcher to exercise the exact frozen command protocol;
    # the release acceptance separately runs the compiled EXE itself.
    from netlab.services import programming
    real_run=programming._run
    python=sys.executable
    launcher=Path(__file__).resolve().parents[1]/"main.py"
    commands=[]
    def launch(args,directory,seconds):
        assert args[0]==python and args[1]=="--run-exercise" and len(args)==5
        commands.append(args)
        return real_run([python,str(launcher)]+args[1:],directory,seconds)
    monkeypatch.setattr(sys,"frozen",True,raising=False)
    monkeypatch.setattr(programming,"_run",launch)
    response=programming.run_python("import sys\nassert 'netlab.app' not in sys.modules\n"+programming.TCP_CODE,timeout=5,workdir=tmp_path)
    assert response["ok"],response
    assert response["stdout"].strip()=="你好 TCP" and response["returncode"]==0
    assert not response["sandboxed"] and len(commands)==1
    assert not list(tmp_path.iterdir())
    failure=programming.run_python("raise RuntimeError('child failure')",timeout=5,workdir=tmp_path)
    assert not failure["ok"] and failure["returncode"]==1
    assert "RuntimeError: child failure" in failure["stderr"]
    assert not list(tmp_path.iterdir())

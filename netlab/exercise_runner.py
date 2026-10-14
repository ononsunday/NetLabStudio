"""Execute user-requested editor code in the application's child interpreter.

This is not a sandbox. The parent process enforces time/output limits and owns
the child process tree. Only the standard library and packaged dependencies are
available without an explicitly configured external interpreter.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import runpy
import sys
import traceback


def run_exercise(script, stdout_path, stderr_path) -> int:
    """Run a source file as __main__, write UTF-8 evidence, return its exit code."""
    source = Path(script).resolve()
    stdout_path, stderr_path = Path(stdout_path).resolve(), Path(stderr_path).resolve()
    if source in {stdout_path, stderr_path} or stdout_path == stderr_path:
        raise ValueError("练习源文件和两个输出文件必须使用不同路径")
    previous_argv = sys.argv
    with stdout_path.open("w", encoding="utf-8", errors="backslashreplace", buffering=1) as stdout, stderr_path.open("w", encoding="utf-8", errors="backslashreplace", buffering=1) as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                if not source.is_file() or source.stat().st_size > 1024 * 1024:
                    raise ValueError("练习须为存在且不超过 1 MiB 的 Python 文件")
                sys.argv = [str(source)]
                runpy.run_path(str(source), run_name="__main__")
                return 0
            except SystemExit as exc:
                if exc.code is None:
                    return 0
                if isinstance(exc.code, int):
                    return exc.code
                print(exc.code, file=stderr)
                return 1
            except BaseException as exc:
                traceback.print_exc(file=stderr)
                return 130 if isinstance(exc, KeyboardInterrupt) else 1
            finally:
                sys.argv = previous_argv

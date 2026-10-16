"""Run every Python exercise with the packaged EXE, using loopback only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from netlab.services.programming import templates

EXPECTED = {
    "tcp_echo": ("你好 TCP",),
    "udp_echo": ("hello UDP",),
    "asyncio": ("asyncio echo",),
    "select": ("select event",),
    "file_transfer": ("SHA256:", "verified: True"),
    "http": ("status: 200", "local HTTP response"),
    "multithread": ("client 0", "client 1", "client 2"),
    "buffers": ("received bytes: 262144", "loopback MiB/s:"),
    "timeout": ("timeout handled: server sent no data",),
    "chat": ("Alice received: Alice: hello Bob", "Bob received: Alice: hello Bob"),
    "websocket": ("WebSocket frame",),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=ROOT / "dist/NetLabStudio/NetLabStudio.exe")
    parser.add_argument("--output", type=Path, default=ROOT / "qa/bundled-examples.json")
    args = parser.parse_args()
    executable = args.exe.resolve(strict=True)
    results = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="netlab-bundled-exercises-") as directory:
        directory = Path(directory)
        for example in templates():
            if example["language"] != "python":
                continue
            source = directory / (example["id"] + ".py")
            out, err = directory / "stdout.txt", directory / "stderr.txt"
            source.write_text(example["code"], encoding="utf-8")
            out.write_text("", encoding="utf-8")
            err.write_text("", encoding="utf-8")
            start = time.perf_counter()
            try:
                process = subprocess.run(
                    [str(executable), "--run-exercise", str(source), str(out), str(err)],
                    cwd=directory, stdin=subprocess.DEVNULL, capture_output=True,
                    timeout=15, creationflags=0x08000000 if sys.platform == "win32" else 0,
                )
                stdout = out.read_text(encoding="utf-8")
                stderr = err.read_text(encoding="utf-8")
                ok = process.returncode == 0 and not stderr and all(
                    text in stdout for text in EXPECTED[example["id"]]
                )
                result = {"id": example["id"], "ok": ok, "returncode": process.returncode,
                          "stdout": stdout, "stderr": stderr}
            except Exception as exc:
                result = {"id": example["id"], "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
            results.append(result)
    evidence = {"scope": "loopback_only", "kind": "measured", "external_interpreter_used": False,
                "exe": str(executable), "passed": sum(result["ok"] for result in results),
                "total": len(results), "results": results, "temporary_files_removed": True,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

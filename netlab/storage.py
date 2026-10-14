"""Local SQLite storage with migrations, atomic imports, and redacted exports."""
from __future__ import annotations

import csv
import io
import ipaddress
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SCHEMA_VERSION = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def redact_data(value):
    """Produce an export copy. The stored original is never modified."""
    sensitive = {"password", "passwd", "secret", "private_key", "authorization", "cookie",
                 "set-cookie", "ssid", "username", "hostname", "computername", "user", "process_path"}

    def text(source):
        source = re.sub(r"(?<![\w:])(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}(?!\w)", "[MAC 已隐藏]", source)
        candidates = re.findall(r"(?<![\w])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?!\w)|[0-9a-fA-F]*:[0-9a-fA-F:.%_-]+", source)
        for candidate in sorted(set(candidates), key=len, reverse=True):
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            source = source.replace(candidate, "[IP 已隐藏]")
        return source

    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            result[str(key)] = "[已隐藏]" if lowered in sensitive or any(token in lowered for token in ("password", "private_key", "secret")) else redact_data(item)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_data(item) for item in value]
    if isinstance(value, str):
        return text(value)
    return value


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path) if str(path) != ":memory:" else ":memory:"
        if self.path != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._closed = False
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=10000")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self._migrate()

    def _migrate(self):
        with self._lock:
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                self.connection.close()
                self._closed = True
                raise ValueError("数据库由更新版本创建，请使用兼容的应用版本")
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                if version < 1:
                    statements = [
                        "CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)",
                        "CREATE TABLE experiments(id TEXT PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,config TEXT NOT NULL,result TEXT NOT NULL,created TEXT NOT NULL)",
                        "CREATE TABLE topologies(id TEXT PRIMARY KEY,name TEXT NOT NULL,config TEXT NOT NULL,updated TEXT NOT NULL)",
                        "CREATE TABLE progress(topic_id TEXT PRIMARY KEY,status TEXT NOT NULL,score REAL,updated TEXT NOT NULL)",
                        "CREATE TABLE notes(id TEXT PRIMARY KEY,topic_id TEXT,title TEXT NOT NULL,body TEXT NOT NULL,updated TEXT NOT NULL)",
                        "CREATE TABLE answers(id TEXT PRIMARY KEY,topic_id TEXT NOT NULL,answer TEXT NOT NULL,correct INTEGER NOT NULL,created TEXT NOT NULL)",
                        "CREATE TABLE templates(id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,config TEXT NOT NULL,updated TEXT NOT NULL)",
                        "CREATE INDEX experiment_kind_created ON experiments(kind,created)",
                        "CREATE INDEX answer_topic_created ON answers(topic_id,created)",
                    ]
                    for statement in statements:
                        self.connection.execute(statement)
                if version < 2:
                    self.connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
                    self.connection.execute("INSERT INTO metadata(key,value) VALUES(?,?)", ("format", "netlab-studio-local"))
                self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    @contextmanager
    def _transaction(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("数据库已关闭")
            try:
                yield self.connection
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    @staticmethod
    def _text(value, label, maximum=1_000_000):
        if not isinstance(value, str) or len(value) > maximum:
            raise ValueError(f"{label}必须为不超过 {maximum} 字符的文本")
        return value

    def set_setting(self, key: str, value):
        self._text(key, "设置键", 512)
        with self._transaction() as con:
            con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, _json(value)))

    def get_setting(self, key: str, default=None):
        with self._lock:
            row = self.connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def save_experiment(self, kind: str, name: str, config: dict, result, experiment_id: str | None = None) -> str:
        self._text(kind, "实验类别", 256)
        self._text(name, "实验名称", 2048)
        if not isinstance(config, dict):
            raise ValueError("实验配置必须为对象")
        experiment_id = experiment_id or str(uuid4())
        with self._transaction() as con:
            con.execute("INSERT INTO experiments(id,kind,name,config,result,created) VALUES(?,?,?,?,?,?)", (experiment_id, kind, name, _json(config), _json(result), _now()))
        return experiment_id

    @staticmethod
    def _experiment(row) -> dict:
        result = dict(row)
        for key in ("config", "result"):
            result[key] = json.loads(result[key])
        return result

    def list_experiments(self, kind: str | None = None, limit: int = 200) -> list[dict]:
        if not isinstance(limit, int) or not 1 <= limit <= 100_000:
            raise ValueError("记录数量应为 1 到 100000")
        with self._lock:
            if kind is None:
                rows = self.connection.execute("SELECT * FROM experiments ORDER BY created DESC,rowid DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = self.connection.execute("SELECT * FROM experiments WHERE kind=? ORDER BY created DESC,rowid DESC LIMIT ?", (kind, limit)).fetchall()
        return [self._experiment(row) for row in rows]

    def get_experiment(self, experiment_id: str) -> dict | None:
        with self._lock:
            row = self.connection.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        return self._experiment(row) if row else None

    def delete_experiment(self, experiment_id: str) -> bool:
        with self._transaction() as con:
            return bool(con.execute("DELETE FROM experiments WHERE id=?", (experiment_id,)).rowcount)

    def save_topology(self, name: str, config: dict, topology_id: str | None = None) -> str:
        self._text(name, "拓扑名称", 2048)
        if not isinstance(config, dict):
            raise ValueError("拓扑配置必须为对象")
        topology_id = topology_id or str(uuid4())
        with self._transaction() as con:
            con.execute("INSERT INTO topologies(id,name,config,updated) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,config=excluded.config,updated=excluded.updated", (topology_id, name, _json(config), _now()))
        return topology_id

    def load_topology(self, topology_id: str) -> dict | None:
        with self._lock:
            row = self.connection.execute("SELECT * FROM topologies WHERE id=?", (topology_id,)).fetchone()
        return {**dict(row), "config": json.loads(row["config"])} if row else None

    def list_topologies(self) -> list[dict]:
        with self._lock:
            rows = self.connection.execute("SELECT * FROM topologies ORDER BY updated DESC").fetchall()
        return [{**dict(row), "config": json.loads(row["config"])} for row in rows]

    def set_progress(self, topic_id: str, status: str = "completed", score: float | None = None):
        if status not in ("not_started", "learning", "completed") or score is not None and not 0 <= score <= 100:
            raise ValueError("学习状态无效；得分须为 0 到 100")
        self._text(topic_id, "知识点 ID", 512)
        with self._transaction() as con:
            con.execute("INSERT INTO progress(topic_id,status,score,updated) VALUES(?,?,?,?) ON CONFLICT(topic_id) DO UPDATE SET status=excluded.status,score=excluded.score,updated=excluded.updated", (topic_id, status, score, _now()))

    def get_progress(self, topic_id: str | None = None):
        with self._lock:
            if topic_id:
                row = self.connection.execute("SELECT * FROM progress WHERE topic_id=?", (topic_id,)).fetchone()
                return dict(row) if row else {"topic_id": topic_id, "status": "not_started", "score": None}
            return {row["topic_id"]: dict(row) for row in self.connection.execute("SELECT * FROM progress").fetchall()}

    def add_note(self, title: str, body: str, topic_id: str | None = None, note_id: str | None = None) -> str:
        self._text(title, "笔记标题", 2048)
        self._text(body, "笔记正文")
        note_id = note_id or str(uuid4())
        with self._transaction() as con:
            con.execute("INSERT INTO notes(id,topic_id,title,body,updated) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET topic_id=excluded.topic_id,title=excluded.title,body=excluded.body,updated=excluded.updated", (note_id, topic_id, title, body, _now()))
        return note_id

    def list_notes(self, topic_id: str | None = None, query: str = "") -> list[dict]:
        with self._lock:
            rows = self.connection.execute("SELECT * FROM notes ORDER BY updated DESC").fetchall()
        return [dict(row) for row in rows if (topic_id is None or row["topic_id"] == topic_id) and
                (not query or query.casefold() in (row["title"] + row["body"]).casefold())]

    def delete_note(self, note_id: str) -> bool:
        with self._transaction() as con:
            return bool(con.execute("DELETE FROM notes WHERE id=?", (note_id,)).rowcount)

    def record_answer(self, topic_id: str, answer, correct: bool) -> str:
        self._text(topic_id, "知识点 ID", 512)
        answer_id = str(uuid4())
        with self._transaction() as con:
            con.execute("INSERT INTO answers(id,topic_id,answer,correct,created) VALUES(?,?,?,?,?)", (answer_id, topic_id, _json(answer), int(bool(correct)), _now()))
        return answer_id

    def mistakes(self, topic_id: str | None = None) -> list[dict]:
        with self._lock:
            rows = self.connection.execute("SELECT * FROM answers WHERE correct=0 ORDER BY created DESC,rowid DESC").fetchall()
        return [{**dict(row), "answer": json.loads(row["answer"])} for row in rows if topic_id is None or row["topic_id"] == topic_id]

    def save_template(self, name: str, kind: str, config: dict, template_id: str | None = None) -> str:
        self._text(name, "模板名称", 2048)
        self._text(kind, "模板类别", 256)
        if not isinstance(config, dict):
            raise ValueError("模板配置必须为对象")
        template_id = template_id or str(uuid4())
        with self._transaction() as con:
            con.execute("INSERT INTO templates(id,name,kind,config,updated) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,kind=excluded.kind,config=excluded.config,updated=excluded.updated", (template_id, name, kind, _json(config), _now()))
        return template_id

    def list_templates(self, kind: str | None = None) -> list[dict]:
        with self._lock:
            rows = self.connection.execute("SELECT * FROM templates ORDER BY updated DESC").fetchall()
        return [{**dict(row), "config": json.loads(row["config"])} for row in rows if kind is None or row["kind"] == kind]

    def export_json(self, path: str | Path | None = None, redact: bool = True) -> dict:
        # Hold the lock for a consistent export while background tasks save records.
        with self._lock:
            payload = {"format": "netlab-studio-export", "version": SCHEMA_VERSION, "exported": _now(),
                       "redacted": bool(redact), "settings": {row["key"]: json.loads(row["value"]) for row in self.connection.execute("SELECT * FROM settings")},
                       "experiments": self.list_experiments(limit=100_000), "topologies": self.list_topologies(),
                       "progress": list(self.get_progress().values()), "notes": self.list_notes(),
                       "answers": [{**dict(row), "answer": json.loads(row["answer"])} for row in self.connection.execute("SELECT * FROM answers")],
                       "templates": self.list_templates()}
        if redact:
            payload = redact_data(payload)
        if path is not None:
            destination = Path(path)
            text = _json(payload)
            temporary = destination.with_name(destination.name + ".tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(destination)
        return payload

    def import_json(self, source: str | Path | dict) -> dict:
        if isinstance(source, dict):
            payload = source
        else:
            path = Path(source)
            if path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("导入文件不能超过 64 MiB")
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict) or payload.get("format") != "netlab-studio-export" or payload.get("version") not in (1, 2):
            raise ValueError("不支持的实验档案格式")
        tables = {
            "experiments": ("id", "kind", "name", "config", "result", "created"),
            "topologies": ("id", "name", "config", "updated"),
            "progress": ("topic_id", "status", "score", "updated"),
            "notes": ("id", "topic_id", "title", "body", "updated"),
            "answers": ("id", "topic_id", "answer", "correct", "created"),
            "templates": ("id", "name", "kind", "config", "updated"),
        }
        prepared = {}
        for table, columns in tables.items():
            rows = payload.get(table, [])
            if not isinstance(rows, list) or len(rows) > 100_000:
                raise ValueError(f"{table} 的记录格式或数量无效")
            prepared[table] = []
            for row in rows:
                if not isinstance(row, dict) or any(column not in row for column in columns):
                    raise ValueError(f"{table} 包含不完整记录")
                if table in ("experiments", "topologies", "templates") and not isinstance(row["config"], dict):
                    raise ValueError("实验配置必须为对象")
                if table == "progress" and (row["status"] not in ("not_started", "learning", "completed") or row["score"] is not None and not 0 <= row["score"] <= 100):
                    raise ValueError("学习进度格式无效")
                if table == "answers" and row["correct"] not in (0, 1, False, True):
                    raise ValueError("答题记录格式无效")
                key = "topic_id" if table == "progress" else "id"
                if not isinstance(row[key], str) or not row[key]:
                    raise ValueError("记录 ID 必须为非空文本")
                values = [_json(row[column]) if column in ("config", "result", "answer") else row[column] for column in columns]
                prepared[table].append(values)
        settings = payload.get("settings", {})
        if not isinstance(settings, dict):
            raise ValueError("设置必须为对象")
        counts = {}
        with self._transaction() as con:
            for table, columns in tables.items():
                count = 0
                query = f"INSERT OR IGNORE INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})"
                for values in prepared[table]:
                    count += con.execute(query, values).rowcount
                counts[table] = count
            for key, value in settings.items():
                con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, _json(value)))
        return {"imported": counts, "redacted": payload.get("redacted", False),
                "note": "相同 ID 的本地记录保留；脱敏档案中的地址不能直接用作可运行拓扑。"}

    def export_csv(self, path: str | Path | None = None, kind: str | None = None, redact: bool = True) -> str:
        records = self.list_experiments(kind, limit=100_000)
        if redact:
            records = redact_data(records)
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=["id", "kind", "name", "created", "config", "result"])
        writer.writeheader()
        for row in records:
            values = {**row, "config": _json(row["config"]), "result": _json(row["result"])}
            # Prevent spreadsheet formulas when a user-supplied experiment title
            # starts with one of the formula sigils. Preserve the stored original.
            values = {key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
                      for key, value in values.items()}
            writer.writerow(values)
        text = output.getvalue()
        if path is not None:
            Path(path).write_text(text, encoding="utf-8-sig", newline="")
        return text

    def report_markdown(self, experiment_id: str, summary: str = "", redact: bool = True) -> str:
        record = self.get_experiment(experiment_id)
        if record is None:
            raise ValueError("实验记录不存在")
        if redact:
            record, summary = redact_data(record), redact_data(summary)
        result = record["result"]
        measured = isinstance(result, dict) and (result.get("kind") == "measured" or result.get("data_kind") == "measured" or result.get("mode") in ("measured", "real", "live") or result.get("data_source") == "measured")
        source = ("导入抓包文件的字段解析；原始采集环境由文件提供者说明，不能据此认定为本机实测。" if isinstance(result, dict) and result.get("data_source") == "pcap_import" else "实测记录；结果只对应本次目标和测量条件。" if measured else "教学模拟或用户导入记录，不能视为本机实测结果。")
        return (f"# {record['name']}\n\n类别：{record['kind']}  \n时间（UTC）：{record['created']}\n\n"
                f"## 实验目标\n\n观察配置变化对实验结果的影响，并根据运行证据解释结果。\n\n"
                f"## 数据来源\n\n{source}\n\n"
                f"## 网络或系统配置\n\n```json\n{json.dumps(record['config'], ensure_ascii=False, indent=2)}\n```\n\n"
                f"## 关键步骤与运行结果\n\n```json\n{json.dumps(result, ensure_ascii=False, indent=2)}\n```\n\n"
                f"## 个人总结\n\n{summary or '尚未填写。'}\n\n"
                f"导出时脱敏：{'是' if redact else '否'}。\n")

    def clear_personal_data(self, keep_settings: bool = True) -> dict:
        counts = {}
        with self._transaction() as con:
            for table in ("experiments", "topologies", "progress", "notes", "answers", "templates"):
                counts[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                con.execute(f"DELETE FROM {table}")
            if not keep_settings:
                counts["settings"] = con.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
                con.execute("DELETE FROM settings")
        return counts

    def close(self):
        with self._lock:
            if not self._closed:
                self.connection.close()
                self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


Store = Database

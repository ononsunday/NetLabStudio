import csv
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from netlab.storage import Database, SCHEMA_VERSION, redact_data


def populate(db):
    db.set_setting("theme", "dark")
    db.set_progress("arp", "completed", 100)
    db.add_note("ARP 观察", "广播请求与单播响应", "arp")
    db.record_answer("arp", 1, False)
    db.record_answer("arp", 0, True)
    db.save_topology("示例拓扑", {"nodes": [{"ip": "192.168.1.10/24"}], "links": []})
    db.save_template("实验模板", "arp", {"seed": 7})
    return db.save_experiment("arp", "本地实验", {"target": "192.168.1.1", "seed": 7}, {"success": True, "teaching_model": True})


def test_database_initialization_roundtrip_and_reopen(tmp_path):
    path = tmp_path / "local.sqlite"
    with Database(path) as db:
        uid = populate(db)
        assert db.connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert db.get_experiment(uid)["config"]["seed"] == 7
    with Database(path) as db:
        assert db.get_setting("theme") == "dark"
        assert db.get_progress("arp")["score"] == 100
        assert len(db.mistakes()) == 1
        assert db.list_topologies()[0]["config"]["nodes"]
        assert len(db.list_notes("arp")) == 1
        assert len(db.list_templates("arp")) == 1


def test_backup_import_preserves_original_and_avoids_duplicate_ids(tmp_path):
    first, second = Database(tmp_path / "a.sqlite"), Database(tmp_path / "b.sqlite")
    populate(first)
    backup = tmp_path / "backup.json"
    first.export_json(backup, redact=False)
    imported = second.import_json(backup)
    assert imported["imported"]["experiments"] == 1
    assert second.get_progress() == first.get_progress()
    assert second.list_experiments() == first.list_experiments()
    assert second.import_json(backup)["imported"]["experiments"] == 0
    assert len(second.list_experiments()) == 1
    first.close()
    second.close()


def test_malformed_import_has_no_partial_writes(tmp_path):
    db = Database(tmp_path / "a.sqlite")
    populate(db)
    before = len(db.list_experiments())
    payload = db.export_json(redact=False)
    payload["experiments"][0]["id"] = "new-experiment"
    payload["notes"][0].pop("body")
    with pytest.raises(ValueError):
        db.import_json(payload)
    assert len(db.list_experiments()) == before
    db.close()


def test_redaction_and_report_source_are_accurate(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    uid = db.save_experiment("diagnostic", "TCP 实测", {"ip": "192.168.1.1", "ssid": "private wifi"},
                             {"kind": "measured", "details": {"address": "2001:db8::2", "mac": "AA:BB:CC:DD:EE:FF", "headers": {"Cookie": "token"}}})
    report = db.report_markdown(uid)
    assert "实测记录" in report and "192.168.1.1" not in report
    assert "2001:db8::2" not in report and "AA:BB:CC:DD:EE:FF" not in report
    assert "private wifi" not in report and '"token"' not in report
    assert db.get_experiment(uid)["config"]["ip"] == "192.168.1.1"
    uid2 = db.save_experiment("simulation", "教学", {}, {"mode": "teaching_simulation"})
    assert "教学模拟" in db.report_markdown(uid2)
    uid3 = db.save_experiment("server", "真实回环服务器", {}, {"data_kind": "measured"})
    assert "实测记录" in db.report_markdown(uid3)
    db.close()


def test_csv_export_and_formula_escaping(tmp_path):
    db = Database(":memory:")
    db.save_experiment("tcp", "=HYPERLINK(\"test\")", {"target": "192.0.2.1"}, {"ok": False})
    output = db.export_csv()
    rows = list(csv.DictReader(io.StringIO(output)))
    assert rows[0]["name"].startswith("'=")
    assert "192.0.2.1" not in output
    assert json.loads(rows[0]["result"]) == {"ok": False}
    db.close()


def test_note_updates_deletion_clear_and_setting_retention():
    db = Database(":memory:")
    populate(db)
    note = db.add_note("old", "old")
    db.add_note("new", "updated", note_id=note)
    assert db.list_notes(query="updated")[0]["title"] == "new"
    assert db.delete_note(note)
    counts = db.clear_personal_data()
    assert counts["experiments"] == 1
    assert not db.list_experiments() and not db.get_progress()
    assert db.get_setting("theme") == "dark"
    db.clear_personal_data(keep_settings=False)
    assert db.get_setting("theme") is None
    db.close()


def test_sql_parameterization_and_threaded_writes():
    db = Database(":memory:")
    db.add_note("' ; DROP TABLE notes; --", "literal text")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: db.save_experiment("test", str(i), {"i": i}, {"ok": True}), range(30)))
    assert len(db.list_experiments()) == 30 and len(db.list_notes()) == 1
    with pytest.raises(ValueError):
        db.set_progress("arp", "invalid")
    db.close()


def test_migration_from_version_one(tmp_path):
    path = tmp_path / "v1.sqlite"
    db = Database(path)
    db.set_setting("preserve", 123)
    db.close()
    con = sqlite3.connect(path)
    con.execute("DROP TABLE metadata")
    con.execute("PRAGMA user_version=1")
    con.commit()
    con.close()
    with Database(path) as migrated:
        assert migrated.get_setting("preserve") == 123
        assert migrated.connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_future_database_version_is_not_overwritten(tmp_path):
    path = tmp_path / "future.sqlite"
    con = sqlite3.connect(path)
    con.execute("PRAGMA user_version=99")
    con.close()
    with pytest.raises(ValueError):
        Database(path)
    con = sqlite3.connect(path)
    assert con.execute("PRAGMA user_version").fetchone()[0] == 99
    con.close()

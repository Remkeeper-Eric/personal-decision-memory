"""Freeze, then replay synthetic retrieval cases in disposable, retained vaults."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
import time
import traceback

from decision_memory.models import Record, render_record
from decision_memory.store import MemoryError as StoreError, Store, digest


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
RUNS = (WORKSPACE / "testing/runs").resolve()
PRODUCTION = (WORKSPACE / "vault").resolve()
CLIENT_TZ = timezone(timedelta(hours=8))


def timestamp():
    return datetime.now(CLIENT_TZ).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    """Read file contents only. Do not instantiate a Store on production."""
    if not root.exists():
        return {"exists": False, "files": {}}
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise RuntimeError(f"快照发现链接，停止而不读取库外路径：{relative}")
        if path.is_file():
            raw = path.read_bytes()
            files[relative] = {"bytes": len(raw), "sha256": digest(raw)}
    return {"exists": True, "files": files}


def changes(before, after):
    a, b = before["files"], after["files"]
    return {"root_existence_changed": before["exists"] != after["exists"],
            "added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()),
            "changed": sorted(k for k in a.keys() & b.keys() if a[k] != b[k])}


def changed(diff):
    return any(diff.values())


def confined_run(path):
    path = path.resolve()
    if path == RUNS or not path.is_relative_to(RUNS) or path.is_relative_to(PRODUCTION):
        raise RuntimeError("运行目录必须是 testing/runs/ 下的独立子目录")
    return path


def case_records(records, state):
    effective = {row["id"]: Record.model_validate(row) for row in records}
    if state == "revised":
        original = effective["SYN-M01"]
        effective[original.id] = original.model_copy(update={
            "base_version": 1,
            "exceptions": original.exceptions + ["v2 新增：只读查看、不提供设置修改时，不要求配置界面"],
            "action": "v2：先核对是否真的需要修改设置，再比较图形入口与脚本；保留开发者批量处理例外。",
            "body": original.body + "\n合成修订 v2，旧动作不再是当前版本。"})
    elif state == "long_record":
        original = effective["SYN-M01"]
        effective[original.id] = original.model_copy(update={
            "rationale": original.rationale + "\n" +
            "预算测试补充说明：调用方必须取得整条条件与例外，不得把省略解释为没有限制。" * 60})
    return [Record.model_validate(row.model_dump()).model_dump() for row in effective.values()]


def prepare(run_dir):
    run_dir = confined_run(run_dir)
    if run_dir.exists():
        raise RuntimeError("轮次目录已经存在，不覆盖")
    corpus = read_json(HERE / "corpus.json")
    cases = read_json(HERE / "cases.json")["cases"]
    if corpus.get("synthetic_only") is not True or len(cases) != 12:
        raise RuntimeError("仅运行固定的 12 项合成测试")
    records = [Record.model_validate(row).model_dump() for row in corpus["records"]]
    if len({r["id"] for r in records}) != 3 or len({c["id"] for c in cases}) != 12:
        raise RuntimeError("记录或案例 ID 不唯一")
    compiled = []
    for case in cases:
        if case["tier"] not in ("required", "exploratory"):
            raise RuntimeError("未知验收类别")
        compiled.append({**case, "initial_records": records,
                         "effective_records": case_records(records, case["state"])})
    frozen = run_dir / "inputs"
    frozen.mkdir(parents=True)
    for name in ("corpus.json", "cases.json", "README.md"):
        shutil.copyfile(HERE / name, frozen / name)
    write_json(frozen / "compiled-cases.json", {"synthetic_only": True, "cases": compiled})
    source_paths = [HERE / "run.py", WORKSPACE / "AGENTS.md", WORKSPACE / "pyproject.toml",
                    WORKSPACE / "testing/plans/v2/基于实现的测试方案.md"]
    source_paths += sorted((WORKSPACE / "src/decision_memory").rglob("*.py"))
    source_hashes = {}
    for source in source_paths:
        relative = source.relative_to(WORKSPACE).as_posix()
        destination = frozen / "source" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        source_hashes[relative] = sha(source)
    write_json(frozen / "source-hashes.json", source_hashes)
    frozen_hashes = {p.relative_to(frozen).as_posix(): sha(p)
                     for p in sorted(frozen.rglob("*")) if p.is_file()}
    write_json(run_dir / "freeze.json", {"frozen_at": timestamp(), "files": frozen_hashes})
    write_json(run_dir / "run.json", {"status": "prepared", "created_at": timestamp(),
        "run_dir": str(run_dir), "synthetic_only": True, "case_count": len(compiled),
        "human_review": "pending", "next_round_authorized": False,
        "runner": "direct Store calls; no model; no MCP client", "model": None, "tokens": None})
    print(json.dumps({"status": "prepared", "run_dir": str(run_dir),
                      "frozen_file_count": len(frozen_hashes)}, ensure_ascii=False))
    return 0


def checks_for(operation, result, error, records):
    expected = operation["expect"]
    checks = []

    def check(name, condition, actual=None):
        checks.append({"name": name, "passed": bool(condition), "actual": actual})

    if "error_contains" in expected:
        check("指定的库拒绝错误", error is not None and error["type"] == "MemoryError"
              and expected["error_contains"] in error["message"], error)
        return checks
    check("调用成功", error is None, error)
    if error is not None:
        return checks
    method = operation["method"]
    if method == "search":
        hits = result["results"]
    elif method == "context":
        hits = [{"record": row, "version": row["version"]} for row in result["memories"]]
    else:
        hits = [result]
    ids = [h["record"]["id"] for h in hits]
    by_id = {h["record"]["id"]: h for h in hits}
    check("无重复 ID", len(ids) == len(set(ids)), ids)
    for rid in expected.get("contains_ids", []):
        check(f"召回 {rid}", rid in ids, ids)
    for rid in expected.get("forbids_ids", []):
        check(f"排除 {rid}", rid not in ids, ids)
    for rid, version in expected.get("versions", {}).items():
        check(f"{rid} 当前 v{version}", rid in by_id and by_id[rid]["version"] == version,
              by_id.get(rid, {}).get("version"))
    for rid, rank in expected.get("max_rank", {}).items():
        actual = ids.index(rid) + 1 if rid in ids else None
        check(f"{rid} 排名前 {rank}", actual is not None and actual <= rank, actual)
    for rid, kind in expected.get("kinds", {}).items():
        actual = by_id.get(rid, {}).get("record", {}).get("kind")
        check(f"{rid} 来源类型保留", actual == kind, actual)
    for rid in expected.get("complete_conditions_for", []):
        fields = ("considerations", "rationale", "applies_when", "exceptions", "action", "sources")
        actual = by_id.get(rid, {}).get("record", {})
        check(f"{rid} 考量/条件/例外/动作/来源完整",
              all(actual.get(f) == records[rid][f] for f in fields))
    if expected.get("no_warnings"):
        check("没有校验警告", result.get("warnings", []) == [], result.get("warnings", []))
    for rid in expected.get("omitted_contains", []):
        omitted = [row["id"] for row in result.get("omitted", [])]
        check(f"省略列表明确含 {rid}", rid in omitted, omitted)
    if "content_chars_max" in expected:
        actual = result.get("content_chars")
        check("所选内容字符数在预算内", isinstance(actual, int) and actual <= expected["content_chars_max"], actual)
    for rid, hit in by_id.items():
        if rid not in records:
            check(f"无未知记录 {rid}", False)
            continue
        expected_record = records[rid]
        if method != "context":
            check(f"{rid} 全文与冻结有效记录相同", hit["record"] == expected_record)
            check(f"{rid} 正文指纹相符", hit.get("sha256") == digest(render_record(Record.model_validate(expected_record))))
        else:
            fields = ("kind", "title", "project_scope", "environments", "considerations", "rationale",
                      "applies_when", "exceptions", "action", "sources", "verification")
            check(f"{rid} 上下文保持冻结字段", all(hit["record"][f] == expected_record[f] for f in fields))
    return checks


def summary_hits(operation):
    result = operation.get("result")
    if result is None:
        return []
    method = operation["input"]["method"]
    if method == "search":
        return [f"{h['record']['id']} v{h['version']}（第 {i}）" for i, h in enumerate(result["results"], 1)]
    if method == "context":
        return [f"{h['id']} v{h['version']}" for h in result["memories"]]
    return [f"{result['record']['id']} v{result['version']}"]


def run_case(run_dir, case):
    case_dir = run_dir / "cases" / case["id"]
    case_dir.mkdir(parents=True)
    root = (case_dir / "vault").resolve()
    if not root.is_relative_to(run_dir) or root.is_relative_to(PRODUCTION):
        raise RuntimeError("测试库越界")
    store = Store(root)
    store.init()
    initial = {r["id"]: Record.model_validate(r) for r in case["initial_records"]}
    effective = {r["id"]: r for r in case["effective_records"]}
    setup = [{"operation": "init", "vault": str(root)}]

    def seed(record, activate=True):
        relative = store.stage(record)
        setup.append({"operation": "stage_synthetic", "id": record.id, "path": relative})
        if activate:
            output = store.publish(relative, digest(store.draft(relative)[1]))
            setup.append({"operation": "activate_test_fixture_only", "result": output})

    for rid, record in initial.items():
        if rid == "SYN-M01" and case["state"] == "long_record":
            record = Record.model_validate(effective[rid])
        seed(record, not (rid == "SYN-M01" and case["state"] == "draft_only"))
    if case["state"] == "revised":
        record = Record.model_validate(effective["SYN-M01"])
        relative = "drafts/SYN-M01.md"
        store.safe_path(relative, "drafts").write_bytes(render_record(record))
        setup.append({"operation": "revise_synthetic", "id": record.id,
                      "result": store.publish(relative, digest(store.draft(relative)[1]))})
    write_json(case_dir / "input.json", case)
    write_json(case_dir / "state-before.json", {"doctor": store.doctor(),
        "manifest": read_json(store.manifest_path), "snapshot": snapshot(root)})
    outputs = []
    revoked = False
    for number, operation in enumerate(case["operations"], 1):
        if case["state"] == "revoked" and operation.get("phase") != "before_revoke" and not revoked:
            active = store.get("SYN-M01", "SYN-team-tools", ["windows"])
            setup.append({"operation": "revoke_test_fixture", "before_operation": number,
                          "result": store.revoke("SYN-M01", active["sha256"])})
            revoked = True
        started = time.perf_counter()
        result, error = None, None
        try:
            result = getattr(store, operation["method"])(**operation["params"])
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            if not isinstance(exc, StoreError):
                error["traceback"] = traceback.format_exc()
        elapsed = (time.perf_counter() - started) * 1000
        checks = checks_for(operation, result, error, effective)
        outputs.append({"number": number, "input": operation, "result": result, "error": error,
            "elapsed_ms": round(elapsed, 3),
            "return_json_chars": len(json.dumps(result, ensure_ascii=False)) if result is not None else None,
            "checks": checks, "status": "pass" if all(c["passed"] for c in checks) else "fail"})
    write_json(case_dir / "setup.json", setup)
    write_json(case_dir / "state-after.json", {"doctor": store.doctor(),
        "manifest": read_json(store.manifest_path), "snapshot": snapshot(root)})
    outcome = {"id": case["id"], "title": case["title"], "tier": case["tier"],
        "status": "pass" if all(o["status"] == "pass" for o in outputs) else "fail", "operations": outputs}
    write_json(case_dir / "output.json", outcome)
    return outcome


def make_report(run_dir, results):
    lines = ["# R01 固定检索与状态测试结果", "", f"执行时间：{results['finished_at']}。状态：待用户复核。", "",
        "本轮直接调用 Store，使用三条合成记录和每题独立测试库；未测试模型自主检索或决策。", "",
        f"结果：{results['counts']['pass']} / {len(results['cases'])} 项符合预先固定的预期。",
        f"基本项：{results['required']}；探索项：{results['exploratory']}。", "",
        f"生产库文件快照变化：{json.dumps(results['production_diff'], ensure_ascii=False)}。", "",
        "全部题目与原始返回在 cases/ 下；inputs/ 是执行前冻结的语料、题目和代码快照。", "",
        "## 逐题证据", ""]
    for case in results["cases"]:
        label = {"pass": "符合预期", "fail": "未达到预期", "error": "设施错误"}[case["status"]]
        lines.extend([f"### {case['id']} {case['title']}：{label}", "",
                      f"类别：{'基本项' if case['tier'] == 'required' else '探索项'}。", ""])
        if case.get("error"):
            lines.extend([f"运行错误：{case['error']['message']}", ""])
        for op in case.get("operations", []):
            query = op["input"]["params"].get("query", op["input"]["params"].get("record_id"))
            lines.append(f"- {op['input']['method']}：{query}")
            lines.append(f"- 返回：{'；'.join(summary_hits(op)) or '无记录'}；耗时 {op['elapsed_ms']} ms。")
            if op["error"]:
                lines.append(f"- 异常：{op['error']['type']} / {op['error']['message']}。")
            if op["result"] and op["result"].get("omitted"):
                lines.append(f"- 明确省略：{json.dumps(op['result']['omitted'], ensure_ascii=False)}。")
            for check in op["checks"]:
                if not check["passed"]:
                    lines.append(f"- 未满足：{check['name']}；实际 {json.dumps(check['actual'], ensure_ascii=False)}。")
            lines.append("")
        evidence = case["id"]
        lines.extend([f"[本题完整输入]({(run_dir / 'cases' / evidence / 'input.json').as_posix()}) · "
                      f"[完整输出与检查]({(run_dir / 'cases' / evidence / 'output.json').as_posix()})", ""])
    lines.extend(["## 解释边界与后续", "",
        "探索题失败同样保留为失败；通过的题目只支持当前合成样例。第 4 项仅有两条同范围候选，不能证明大库前五条排名质量。", "",
        "第 5、6 项仅核对资料召回和内容完整，不证明 Codex 理解例外或服从当前用户要求。第 12 项的 get 是脚本安排，不证明 Codex 会主动补取。", "",
        "没有调用模型、没有实际 token 计量；耗时仅为本机单次 Store 调用，返回字符数不是 token。语料和题目由同一助手准备，存在设计偏差。", "",
        "本轮结束，等待用户复核。未自动修复检索、增加别名、启动新会话、进入下一轮或形成个人记忆。", ""])
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def execute(run_dir):
    run_dir = confined_run(run_dir)
    meta = read_json(run_dir / "run.json")
    if meta["status"] != "prepared":
        raise RuntimeError("只允许执行尚未运行的冻结轮次，不覆盖结果")
    frozen = run_dir / "inputs"
    for relative, expected in read_json(run_dir / "freeze.json")["files"].items():
        if sha(frozen / relative) != expected:
            raise RuntimeError(f"冻结输入已变化：{relative}")
    for relative, expected in read_json(frozen / "source-hashes.json").items():
        if sha(WORKSPACE / relative) != expected:
            raise RuntimeError(f"被测代码或计划已变化：{relative}")
    for name in ("tmp", "backups"):
        (run_dir / name).mkdir()
    os.environ["TEMP"] = os.environ["TMP"] = str(run_dir / "tmp")
    meta.update(status="running", started_at=timestamp(), python=sys.version, platform=platform.platform(),
        sqlite_version=sqlite3.sqlite_version,
        dependencies={name: importlib.metadata.version(name) for name in ("pydantic", "PyYAML")},
        test_backup_root=str(run_dir / "backups"), backup_used=False)
    write_json(run_dir / "run.json", meta)
    before = snapshot(PRODUCTION)
    write_json(run_dir / "production-before.json", before)
    outcomes = []
    for case in read_json(frozen / "compiled-cases.json")["cases"]:
        try:
            outcome = run_case(run_dir, case)
        except Exception as exc:
            outcome = {"id": case["id"], "title": case["title"], "tier": case["tier"],
                "status": "error", "operations": [], "error": {"type": type(exc).__name__,
                "message": str(exc), "traceback": traceback.format_exc()}}
            write_json(run_dir / "cases" / case["id"] / "output.json", outcome)
        outcomes.append(outcome)
        current = snapshot(PRODUCTION)
        if outcome["status"] == "error" or changed(changes(before, current)):
            break
    after = snapshot(PRODUCTION)
    write_json(run_dir / "production-after.json", after)
    diff = changes(before, after)
    counts = dict(Counter(c["status"] for c in outcomes))
    counts.setdefault("pass", 0)
    counts.setdefault("fail", 0)
    result = {"finished_at": timestamp(), "status": "awaiting_user_review", "counts": counts,
        "required": dict(Counter(c["status"] for c in outcomes if c["tier"] == "required")),
        "exploratory": dict(Counter(c["status"] for c in outcomes if c["tier"] == "exploratory")),
        "production_diff": diff, "cases": outcomes, "complete": len(outcomes) == 12}
    write_json(run_dir / "results.json", result)
    make_report(run_dir, result)
    blocked = changed(diff) or counts.get("error", 0) > 0 or not result["complete"]
    exit_code = 2 if blocked else (1 if counts["fail"] else 0)
    meta.update(status="blocked" if blocked else "awaiting_user_review", finished_at=result["finished_at"],
                counts=counts, exit_code=exit_code, production_changed=changed(diff))
    write_json(run_dir / "run.json", meta)
    print(json.dumps({"run_dir": str(run_dir), "status": meta["status"], "counts": counts,
                      "required": result["required"], "exploratory": result["exploratory"],
                      "production_diff": diff, "exit_code": exit_code}, ensure_ascii=False))
    return exit_code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "execute"))
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        directory = args.run_dir or RUNS / ("R01-fixed-retrieval-" + datetime.now(CLIENT_TZ).strftime("%Y%m%dT%H%M%S%f"))
        return prepare(directory)
    if args.run_dir is None:
        parser.error("execute 需要 --run-dir")
    return execute(args.run_dir)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"status": "infrastructure_error", "type": type(exc).__name__,
                          "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)

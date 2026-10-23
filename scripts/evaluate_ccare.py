"""Offline development diagnostics. Never sends data to any provider."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ccare.engine import local_state, strategy_for
from app.ccare.schemas import TurnRequest


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/ccare_smoke.json")
    parser.add_argument("--allow-dirty", action="store_true", help="Record an uncommitted development run explicitly")
    args = parser.parse_args()
    config_path = ROOT / args.config
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if config["mode"] != "local_rules_only":
        raise SystemExit("This runner supports offline diagnostics only")
    dirty = git("status", "--porcelain")
    if dirty and not args.allow_dirty:
        raise SystemExit("Commit the reviewed code before running, or explicitly use --allow-dirty for development")
    random.seed(config["seed"])
    source = ROOT / config["dataset"]
    records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len({r["id"] for r in records}) != len(records):
        raise SystemExit("Duplicate case IDs")
    run = ROOT / "experiments" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in records:
        req = TurnRequest(message=case["message"], history=case.get("history", []), goal=case["goal"], eligible=True)
        state = local_state(req)
        strategy = strategy_for(req, state)
        rows.append({"id": case["id"], "category": case["category"], "urgent_expected": case["urgent_expected"],
                     "urgent_observed": state.risk == "urgent", "strategy_expected": case["strategy_expected"],
                     "strategy_observed": strategy, "match": (state.risk == "urgent") == case["urgent_expected"] and strategy == case["strategy_expected"]})
    metadata = {"kind": "development_diagnostic_not_research_result", "commit": git("rev-parse", "HEAD"),
                "dirty": bool(dirty), "dirty_paths": dirty.splitlines(), "config": config,
                "config_sha256": sha(config_path), "data_sha256": sha(source), "python": platform.python_version(),
                "packages": {p: importlib.metadata.version(p) for p in ("fastapi", "pydantic", "httpx")},
                "code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in (ROOT / "backend/app/ccare").rglob("*.py")},
                "external_model_calls": 0, "cases": len(rows), "mismatches": [r["id"] for r in rows if not r["match"]]}
    (run / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "results.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (run / "notes.md").write_text("# 离线开发诊断\n\n" + f"处理 {len(rows)} 个合成案例；{len(metadata['mismatches'])} 个案例与暂定标签不符。外部调用 0 次。\n\n"
        "标签未经专业审核；数据参与过开发，不能据此宣称心理支持效果或独立测试集准确率。差异完整保存在 results.jsonl。\n", encoding="utf-8")
    print(json.dumps({"run": str(run), "cases": len(rows), "mismatches": metadata["mismatches"], "external_model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()

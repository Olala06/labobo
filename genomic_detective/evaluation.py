from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate_reports(report_dir: Path, expected_path: Path, output_path: Path) -> dict[str, Any]:
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    expected_map = expected.get("cases", expected)
    report_files = sorted(report_dir.glob("case_*.json"))
    checked, correct, missing = 0, 0, []
    rows = []
    for file in report_files:
        report = json.loads(file.read_text(encoding="utf-8"))
        case_name = report["case_name"]
        gold = expected_map.get(case_name)
        if gold is None:
            continue
        checked += 1
        wanted = gold.get("condition_id") or gold.get("condition")
        top = report["candidates"][0] if report["candidates"] else None
        got = None
        if top:
            got = top["condition_id"] if wanted == top["condition_id"] else top["name"]
        is_correct = got == wanted
        correct += int(is_correct)
        rows.append({"case": case_name, "expected": wanted, "top1": got, "correct": is_correct})
    result = {
        "checked": checked, "top1_correct": correct,
        "top1_accuracy": (correct / checked) if checked else None,
        "cases": rows,
        "warning": "Оценка отражает только предоставленный набор ответов и не доказывает клиническую точность или независимую валидацию.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

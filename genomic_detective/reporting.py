from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def _candidate_html(candidate: dict[str, Any]) -> str:
    evidence = "".join(f"<li>{html.escape(line)}</li>" for line in candidate["explanation"])
    sources = "".join(
        f'<li><a href="{html.escape(source["url"], quote=True)}" target="_blank" rel="noopener">{html.escape(source["label"])}</a></li>'
        for source in candidate["sources"]
    )
    return f"""
    <section class="candidate">
      <h2>{html.escape(candidate["name"])} <span>{candidate["score_0_to_100"]:.1f}/100</span></h2>
      <p>Гены: {html.escape(", ".join(candidate["genes"]))} · Наследование: {html.escape(candidate["inheritance"])}</p>
      <h3>Объяснение и экспертные доказательства</h3><ul>{evidence}</ul>
      <h3>Источники</h3><ul>{sources}</ul>
    </section>"""


def render_html(report: dict[str, Any]) -> str:
    candidates = "".join(_candidate_html(c) for c in report["candidates"]) or "<p>Убедительный кандидат по текущей базе не найден. Это не исключает генетическую причину.</p>"
    phenotypes = ", ".join(f'{p["label"]} ({p["hpo_id"]})' for p in report["recognized_phenotypes"]) or "не распознаны"
    warnings = "".join(f"<li>{html.escape(item)}</li>" for item in report["warnings"] + report["limitations"])
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Геномный детектив — {html.escape(report["case_name"])}</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;max-width:1000px;margin:40px auto;padding:0 20px;color:#18212f;background:#f5f7fb}}
header,.candidate,.panel{{background:white;border:1px solid #dce2ea;border-radius:14px;padding:22px;margin:16px 0}}
h1{{margin:0}} h2{{display:flex;justify-content:space-between;gap:16px}} h2 span{{color:#176a53;white-space:nowrap}}
small,.muted{{color:#667085}} .notice{{background:#fff5dc;border-left:4px solid #c78a22;padding:14px}}
a{{color:#165d9b}} code{{background:#eef1f5;padding:2px 5px;border-radius:4px}}
</style></head><body><header><h1>🧬 Геномный детектив</h1><p>{html.escape(report["case_name"])} · Статус: <b>{html.escape(report["status"])}</b></p>
<p class="notice">{html.escape(report["score_interpretation"])}</p></header>
<div class="panel"><b>Входные данные</b><p>Вариантов: {report["variant_count"]}</p><p>Распознанные фенотипы: {html.escape(phenotypes)}</p></div>
{candidates}
<div class="panel"><h2>Ограничения и предупреждения</h2><ul>{warnings}</ul></div></body></html>"""


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Геномный детектив — {report['case_name']}", "",
        f"**Статус:** {report['status']}", "",
        f"> {report['score_interpretation']}", "",
        f"**Вариантов:** {report['variant_count']}", "",
        "**Распознанные фенотипы:** " + (", ".join(f"{p['label']} ({p['hpo_id']})" for p in report["recognized_phenotypes"]) or "не распознаны"), "",
        "## Рейтинг кандидатов", "",
    ]
    if not report["candidates"]:
        lines.append("Убедительный кандидат по текущей базе не найден. Это не исключает генетическую причину.")
    for i, candidate in enumerate(report["candidates"], 1):
        lines.extend([f"### {i}. {candidate['name']} — {candidate['score_0_to_100']:.1f}/100", "",
                      f"Гены: {', '.join(candidate['genes'])}; наследование: {candidate['inheritance']}", "",
                      *[f"- {line}" for line in candidate["explanation"]], "", "**Источники:**"])
        lines.extend([f"- [{source['label']}]({source['url']})" for source in candidate["sources"]])
        lines.append("")
    lines.extend(["## Ограничения", *[f"- {item}" for item in report["limitations"] + report["warnings"]], ""])
    return "\n".join(lines)


def write_reports(reports: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for index, report in enumerate(reports, 1):
        stem = f"case_{index:02d}"
        (output_dir / f"{stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
        (output_dir / f"{stem}.html").write_text(render_html(report), encoding="utf-8")
        for candidate in report["candidates"]:
            all_rows.append({
                "case": report["case_name"], "rank": len([r for r in all_rows if r["case"] == report["case_name"]]) + 1,
                "condition": candidate["name"], "genes": ",".join(candidate["genes"]),
                "score_0_to_100": candidate["score_0_to_100"], "status": candidate["status"],
                "phenotype_score": candidate["experts"]["phenotype"]["score"],
                "molecular_score": candidate["experts"]["molecular"]["score"],
                "inheritance_score": candidate["experts"]["inheritance"]["score"],
            })
    if reports:
        (output_dir / "run.json").write_text(json.dumps({
            "cases": [{"name": r["case_name"], "status": r["status"], "complete": r["complete"]} for r in reports],
            "incomplete_cases": [r["case_name"] for r in reports if not r["complete"]],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "ranking.tsv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["case", "rank", "condition", "genes", "score_0_to_100", "status", "phenotype_score", "molecular_score", "inheritance_score"]
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(all_rows)

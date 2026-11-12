from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


FIELDS = ["case", "rank", "condition", "genes", "score_0_to_100", "status",
          "phenotype_score", "molecular_score", "inheritance_score"]


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
    gene_sections = []
    for index, gene in enumerate(report.get("gene_candidates", []), 1):
        variants = "".join(
            f"<li><code>{html.escape(str(v.get('locus', '')))}</code>"
            f" — {html.escape(str(v.get('consequence') or 'последствие не указано'))}"
            f" — GT: {html.escape(str(v.get('genotype') or 'не указан'))}</li>"
            for v in gene.get("variants", [])
        )
        matched = ", ".join(
            f"{item.get('label', '')} ({item.get('id', '')})"
            for item in gene.get("directly_matched_hpo", [])
        ) or "Нет прямых совпадений; сходство учитывает онтологические связи HPO."
        gtex = gene.get("gtex") or {}
        if gtex.get("status") == "available":
            tissues = "".join(
                f"<tr><td>{html.escape(str(item.get('tissue', '')))}</td>"
                f"<td>{float(item.get('median_tpm', 0)):.3f}</td></tr>"
                for item in gtex.get("top_tissues", [])
            )
            tissue_block = (
                f"<p><b>GTEx {html.escape(str(gtex.get('dataset', 'gtex_v10')))}</b> · "
                f"{html.escape(str(gtex.get('gencode_id', '')))}</p>"
                f"<table><thead><tr><th>Ткань</th><th>Медианная экспрессия</th></tr></thead>"
                f"<tbody>{tissues}</tbody></table>"
            )
        elif gtex:
            tissue_block = f"<p class='muted'>GTEx: {html.escape(str(gtex.get('reason', 'данные недоступны')))}</p>"
        else:
            tissue_block = "<p class='muted'>GTEx не запрашивался. Включите сетевую аннотацию в следующем запуске.</p>"
        gene_sections.append(f"""
        <section class="candidate">
          <h2>{index}. {html.escape(str(gene.get('gene', '')))}
            <span>{float(gene.get('hpo_similarity_percent', 0)):.1f}/100</span></h2>
          <p><b>Семантическое сходство PyHPO:</b> {html.escape(str(gene.get('similarity_method', '')))}.
             Это не вероятность диагноза.</p>
          <p><b>Прямые совпадения HPO:</b> {html.escape(matched)}</p>
          <h3>Варианты в гене</h3><ul>{variants or '<li>Варианты в загруженном файле не сопоставлены.</li>'}</ul>
          <h3>Экспрессия в нормальных тканях (GTEx)</h3>{tissue_block}
        </section>""")
    genes_html = "".join(gene_sections) or (
        "<p>Нет ранжированных генов. Проверьте, что введены HPO ID/названия и что "
        "вариантам сопоставлены символы генов (в VCF INFO или через VEP).</p>"
    )

    candidates_html = "".join(_candidate_html(c) for c in report.get("candidates", []))
    phenotypes = ", ".join(
        f'{p.get("label", "")} ({p.get("id") or p.get("hpo_id", "")})'
        for p in report.get("recognized_phenotypes", [])
    ) or "не распознаны"
    warnings = "".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in report.get("warnings", []) + report.get("limitations", [])
    )
    source_files = ", ".join(html.escape(Path(str(name)).name) for name in report.get("source_files", []))
    if candidates_html:
        candidates_html = (
            "<div class='panel'><h2>Дополнительные подсказки локального словаря заболеваний</h2>"
            "<p class='muted'>Это ограниченная демонстрационная база, не полный каталог заболеваний.</p>"
            + candidates_html + "</div>"
        )
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Результат анализа — {html.escape(str(report.get("case_name", "sample")))}</title>
<style>
:root{{color-scheme:light;--ink:#182433;--muted:#657386;--line:#e1e7ec;--green:#246b59;--wash:#f4f7f7}}
*{{box-sizing:border-box}}body{{font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;max-width:1040px;margin:34px auto;padding:0 20px;color:var(--ink);background:var(--wash)}}
header,.candidate,.panel{{background:white;border:1px solid var(--line);border-radius:16px;padding:22px;margin:16px 0;box-shadow:0 6px 22px #18243308}}
h1{{margin:0;font-size:30px}}h2{{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-top:0}}h2 span{{color:var(--green);white-space:nowrap;font-variant-numeric:tabular-nums}}
h3{{font-size:15px;margin-bottom:6px}}p{{margin:8px 0}}small,.muted{{color:var(--muted)}}.notice{{background:#fff5df;border-left:4px solid #c78a22;padding:14px;border-radius:8px}}
a{{color:#165d9b}}code{{background:#eef1f5;padding:2px 5px;border-radius:4px;overflow-wrap:anywhere}}
table{{width:100%;border-collapse:collapse;margin:8px 0 16px}}th,td{{text-align:left;border-bottom:1px solid var(--line);padding:7px 9px;font-size:14px}}th{{color:var(--muted)}}
.eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:11px;color:var(--green);font-weight:750}}
.back{{display:inline-block;margin:8px 0 20px;text-decoration:none;font-weight:650}}
</style></head><body><a class="back" href="/">← Новый анализ</a>
<header><p class="eyebrow">GENOMIC DETECTIVE / LOCAL WORKSPACE</p><h1>Результат анализа</h1>
<p>{html.escape(str(report.get("case_name", "uploaded sample")))} · Статус: <b>{html.escape(str(report.get("status", "unknown")))}</b></p>
<p class="notice">{html.escape(str(report.get("score_interpretation", "")))}</p>
<p class="muted">Вариантов: {int(report.get("variant_count", 0))} · HPO: {html.escape(phenotypes)}</p>
<p class="muted">Файлы: {source_files or "не указаны"}</p></header>
<section class="panel"><p class="eyebrow">01 / HPO GENE PRIORITIZATION</p><h2>Гены-кандидаты по фенотипу</h2>
<p class="muted">Библиотека: {html.escape(str(report.get("hpo_metadata", {}).get("library", "PyHPO")))} ·
Статус: {html.escape(str(report.get("hpo_metadata", {}).get("status", "unknown")))} ·
Терминов: {int(report.get("hpo_metadata", {}).get("recognized_terms", 0))}</p>
{genes_html}
</section>
{candidates_html}
<section class="panel"><h2>Ограничения и предупреждения</h2><ul>{warnings}</ul>
<p class="muted">Источники: <a href="https://hpo.jax.org/" target="_blank" rel="noopener">Human Phenotype Ontology</a> ·
<a href="https://gtexportal.org/home/apiPage" target="_blank" rel="noopener">GTEx Portal API v2</a> ·
<a href="https://rest.ensembl.org/" target="_blank" rel="noopener">Ensembl VEP</a></p></section>
</body></html>"""

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


def _ranking_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for rank, candidate in enumerate(report["candidates"], 1):
        rows.append({
            "case": report["case_name"], "rank": rank,
            "condition": candidate["name"], "genes": ",".join(candidate["genes"]),
            "score_0_to_100": candidate["score_0_to_100"], "status": candidate["status"],
            "phenotype_score": candidate["experts"]["phenotype"]["score"],
            "molecular_score": candidate["experts"]["molecular"]["score"],
            "inheritance_score": candidate["experts"]["inheritance"]["score"],
        })
    return rows


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_reports(reports: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    for index, report in enumerate(reports, 1):
        stem = f"case_{index:02d}"
        (output_dir / f"{stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
        (output_dir / f"{stem}.html").write_text(render_html(report), encoding="utf-8")
        case_rows = _ranking_rows(report)
        all_rows.extend(case_rows)
        _write_tsv(output_dir / f"{stem}_ranking.tsv", case_rows)

    if reports:
        (output_dir / "run.json").write_text(json.dumps({
            "cases": [{"name": r["case_name"], "status": r["status"], "complete": r["complete"]} for r in reports],
            "incomplete_cases": [r["case_name"] for r in reports if not r["complete"]],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_tsv(output_dir / "ranking.tsv", all_rows)

    completed = [report for report in reports if report["complete"]]
    incomplete = [report for report in reports if not report["complete"]]
    if completed:
        with (output_dir / "predictions.tsv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(["case", "prediction", "status"])
            for report in completed:
                top = report["candidates"][0]["condition_id"] if report["candidates"] else "no_causal_variant_in_vcf"
                writer.writerow([report["case_name"], top, report["status"]])
    if incomplete:
        with (output_dir / "predictions.partial.tsv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(["case", "status", "reason"])
            for report in incomplete:
                writer.writerow([report["case_name"], report["status"], "Incomplete data or unmatched phenotype"])

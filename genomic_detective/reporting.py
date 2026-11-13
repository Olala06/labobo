from __future__ import annotations
            f"{float(item.get('hpo_score') or 0):.1f}" if item.get("hpo_score") is not None else "NA",

import csv
import html
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote


FIELDS = ["case", "rank", "condition", "genes", "score_0_to_100", "status",
          "phenotype_score", "molecular_score", "inheritance_score"]


def _hpo_text(items: list[dict[str, Any]]) -> str:
    values = [
        f"{item.get('label') or item.get('id') or 'HPO'} ({item.get('id', '')})"
        for item in items
    ]
    return "; ".join(value.strip() for value in values if value.strip()) or "—"


def _candidate_html(candidate: dict[str, Any]) -> str:
    evidence = "".join(f"<li>{html.escape(str(line))}</li>" for line in candidate.get("explanation", []))
    sources = "".join(
        f'<li><a href="{html.escape(str(source.get("url", "")), quote=True)}" target="_blank" rel="noopener">{html.escape(str(source.get("label", "")))}</a></li>'
        for source in candidate.get("sources", [])
    )
    mechanism = (
        f"<h3>Механизм / контекст литературы</h3><p>{html.escape(str(candidate['mechanism']))}</p>"
        if candidate.get("mechanism") else ""
    )
    return f"""
    <section class="candidate">
      <h3>{html.escape(str(candidate.get("name", "Гипотеза")))}
        <span>{float(candidate.get("score_0_to_100", 0)):.1f}/100</span></h3>
      <p>Гены: {html.escape(", ".join(candidate.get("genes", [])))} ·
      наследование: {html.escape(str(candidate.get("inheritance", "не указано")))}</p>
      <h4>Объяснение</h4><ul>{evidence}</ul>
      {mechanism}
      <h4>Источники</h4><ul>{sources}</ul>
    </section>"""


def _variant_table(report: dict[str, Any]) -> str:
    rows = []
    for item in report.get("variant_candidates", []):
        rank = item.get("rank")
        positive = _hpo_text(item.get("positive_matches", []))
        excluded = _hpo_text(item.get("excluded_conflicts", []))
        context = str(item.get("inheritance_assessment") or "Наследование не оценено")
        mechanism = str(item.get("mechanism") or "")
        mechanism_check = str(item.get("mechanism_check") or "Механизм не оценён")
            context += " Механизм: " + mechanism
            context += " Механизм по литературе: " + mechanism
            str(rank) if rank is not None else "—",
            str(item.get("gene", "не аннотирован")),
            f"<code>{html.escape(str(item.get('variant', '')))}</code>",
            str(item.get("genotype", "NA")),
            str(item.get("consequence", "NA")),
            str(item.get("gnomad_af", "NA")),
            str(item.get("clinvar", "NA")),
            positive,
            excluded,
            context + " " + mechanism_check,
            str(item.get("published_reference_check", "—")),
        ]
        rows.append("<tr>" + "".join(
            f"<td>{cell if cell.startswith('<code>') else html.escape(cell)}</td>"
            for cell in cells
        ) + "</tr>")
    if not rows:
        return "<p>Вариантов в VCF не найдено.</p>"
    return """
    <div class="table-wrap"><table class="results">
      <thead><tr>
        <th>Ранг</th><th>HPO-балл</th><th>Ген</th><th>Точная запись VCF (GRCh38, 1-based)</th>
        <th>GT</th><th>Последствие</th><th>gnomAD AF</th><th>ClinVar</th>
        <th>Положительные HPO</th><th>Конфликты с excluded HPO</th>
        <th>Наследование / механизм</th><th>Сверка с опубликованной записью</th>
      </tr></thead><tbody>""" + "".join(rows) + "</tbody></table></div>"


def render_html(report: dict[str, Any]) -> str:
    positive = report.get("recognized_phenotypes", [])
    excluded = report.get("excluded_phenotypes", [])
    features_html = f"""
      <div class="phenotype-grid">
        <div><h3>Положительные признаки · {len(positive)}</h3><ul>
          {''.join(f'<li>{html.escape(str(p.get("label", "")))} <small>{html.escape(str(p.get("id", "")))}</small></li>' for p in positive) or '<li>Не распознаны</li>'}
        </ul></div>
        <div><h3>Исключённые признаки · {len(excluded)}</h3><ul>
          {''.join(f'<li>{html.escape(str(p.get("label", "")))} <small>{html.escape(str(p.get("id", "")))}</small></li>' for p in excluded) or '<li>В файле не указаны</li>'}
        </ul></div>
      </div>"""
    phenopacket_metadata = report.get("phenopacket_metadata") or {}
    diseases = phenopacket_metadata.get("diseases") or []
    disease_note = ""
    if diseases:
        disease_text = "; ".join(
            f"{item.get('label') or item.get('id') or 'термин'} [{item.get('id') or 'ID не указан'}]"
            for item in diseases
        )
        disease_note = (
            "<p class='muted'><b>Диагнозы, записанные во входном Phenopacket:</b> "
            + html.escape(disease_text)
            + ". Эти поля показаны как метаданные и не использовались для ранжирования.</p>"
        )

    warnings_html = "".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in report.get("warnings", []) + report.get("limitations", [])
    )
    source_files = ", ".join(
        html.escape(Path(str(name)).name) for name in report.get("source_files", [])
    )
    gene_sections = []
    for index, gene in enumerate(report.get("gene_candidates", []), 1):
        matched = _hpo_text(gene.get("directly_matched_hpo", []))
        conflicts = _hpo_text(gene.get("excluded_conflicts", []))
        gene_sections.append(f"""
        <tr><td>{index}</td><td><b>{html.escape(str(gene.get('gene', '')))}</b></td>
        <td>{float(gene.get('adjusted_hpo_score_percent', gene.get('hpo_similarity_percent', 0))):.1f}/100</td>
        <td>{html.escape(matched)}</td><td>{html.escape(conflicts)}</td></tr>""")
    gene_table = (
        "<div class='table-wrap'><table><thead><tr><th>Ранг</th><th>Ген</th><th>Скорректированный HPO-балл</th><th>Положительные совпадения</th><th>Excluded-конфликты</th></tr></thead><tbody>"
        + "".join(gene_sections) + "</tbody></table></div>"
        if gene_sections else
        "<p>Гены не удалось ранжировать. Проверьте, содержит ли VCF аннотацию гена (SYMBOL/GENE/CSQ/ANN); без неё таблица сохраняет точные записи, но генный HPO-рейтинг недоступен.</p>"
    )

    candidates_html = "".join(_candidate_html(c) for c in report.get("candidates", []))
    prediction = str(report.get("prediction") or "no_causal_variant_in_vcf")
    prediction_text = (
        f"<code>{html.escape(prediction)}</code>"
        if prediction != "no_causal_variant_in_vcf"
        else "<code>no_causal_variant_in_vcf</code>"
    )
    tsv = "case_id\tprediction\n" + f"{report.get('case_id', report.get('case_name', 'case'))}\t{prediction}\n"
    prediction_link = (
        '<a class="download" download="predictions.tsv" href="data:text/tab-separated-values;charset=utf-8,'
        + quote(tsv) + '">Скачать predictions.tsv</a>'
    )
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Результат — {html.escape(str(report.get("case_name", "sample")))}</title>
<style>
:root{{color-scheme:light;--ink:#172733;--muted:#647583;--line:#dfe7e9;--green:#176653;--wash:#f4f7f6}}
*{{box-sizing:border-box}}body{{font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;max-width:1240px;margin:30px auto;padding:0 20px;color:var(--ink);background:var(--wash)}}
header,.panel,.candidate{{background:white;border:1px solid var(--line);border-radius:16px;padding:22px;margin:16px 0;box-shadow:0 6px 22px #18243308}}
h1{{margin:0;font-size:30px;letter-spacing:-.03em}}h2{{margin:0 0 12px;font-size:20px}}h3{{margin:12px 0 6px;font-size:15px}}h4{{margin:12px 0 5px;font-size:13px}}
p{{margin:8px 0}}small,.muted{{color:var(--muted)}}.eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:11px;color:var(--green);font-weight:750}}
.notice{{background:#fff5df;border-left:4px solid #c78a22;padding:13px;border-radius:8px;margin-top:14px}}
a{{color:#165d9b}}code{{background:#eef2f4;padding:3px 5px;border-radius:5px;overflow-wrap:anywhere}}
.back{{display:inline-block;margin:8px 0 10px;text-decoration:none;font-weight:650}}.download{{display:inline-block;margin-top:10px;font-weight:700}}
.table-wrap{{overflow-x:auto;width:100%;border:1px solid var(--line);border-radius:10px}}
table{{border-collapse:collapse;width:100%;margin:0;min-width:1120px}}th,td{{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:10px 9px;font-size:12px;min-width:90px;max-width:280px;overflow-wrap:anywhere}}
th{{position:sticky;top:0;background:#f7faf9;color:var(--muted);font-weight:750;z-index:1}}tr:last-child td{{border-bottom:0}}.results td:nth-child(3){{min-width:190px}}.results td:nth-child(10){{min-width:260px}}
.phenotype-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.phenotype-grid>div{{background:#fafcfb;border:1px solid var(--line);border-radius:10px;padding:12px}}
.candidate h3{{display:flex;justify-content:space-between;gap:12px}}.candidate h3 span{{color:var(--green);white-space:nowrap}}
@media(max-width:760px){{body{{margin:18px auto}}header,.panel,.candidate{{padding:16px}}.phenotype-grid{{grid-template-columns:1fr}}h1{{font-size:25px}}}}
</style></head><body><a class="back" href="/">← Новый анализ</a>
<header><p class="eyebrow">GENOMIC DETECTIVE / EDUCATIONAL VERSION</p><h1>Результат анализа: {html.escape(str(report.get("case_name", "uploaded sample")))}</h1>
<p>Статус: <b>{html.escape(str(report.get("status", "unknown")))}</b> · Записей VCF: {int(report.get("variant_count", 0))}</p>
<p class="notice">{html.escape(str(report.get("score_interpretation", "")))}</p>
<p><b>Приоритетный вариант:</b> {prediction_text}</p>{prediction_link}
<p class="muted">Файлы: {source_files or "не указаны"} · Сборка координат: GRCh38 (ожидается для benchmark)</p>
{disease_note}</header>
<section class="panel"><p class="eyebrow">01 / PHENOTYPE PROFILE</p><h2>Фенотипический профиль из JSON</h2>
{features_html}</section>
<section class="panel"><p class="eyebrow">02 / VARIANT RANKING</p><h2>Таблица вариантов-кандидатов</h2>
<p class="muted">Одна строка — одна запись варианта из VCF. Ранг задаётся HPO-сходством гена; NA — отсутствие аннотации, а не доброкачественность.</p>
{_variant_table(report)}</section>
<section class="panel"><p class="eyebrow">03 / GENE CONTEXT</p><h2>Ранжирование генов и отрицательные признаки</h2>
<p class="muted">PyHPO funSimAvg · корректировка исключёнными признаками ограничена точными совпадениями генных HPO-аннотаций.</p>
{gene_table}</section>
{("<section class='panel'><h2>Курируемые подсказки о заболеваниях</h2><p class='muted'>Это небольшой локальный справочник, а не полный каталог. Его гипотезы не заменяют независимую проверку.</p>" + candidates_html + "</section>") if candidates_html else ""}
<section class="panel"><h2>Предупреждения и ограничения</h2><ul>{warnings_html}</ul>
<p class="muted">Источники: <a href="https://hpo.jax.org/" target="_blank" rel="noopener">Human Phenotype Ontology</a> ·
<a href="https://rest.ensembl.org/" target="_blank" rel="noopener">Ensembl VEP</a> ·
<a href="https://pubmed.ncbi.nlm.nih.gov/21594993/" target="_blank" rel="noopener">PubMed PMID:21594993</a></p></section>
</body></html>"""


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Геномный детектив — {report['case_name']}", "",
        f"**Статус:** {report['status']}", "",
        f"**Prediction:** {report.get('prediction', 'no_causal_variant_in_vcf')}", "",
        f"> {report['score_interpretation']}", "",
        f"**Вариантов:** {report['variant_count']}", "",
        "## Положительные HPO-признаки", "",
        *[f"- {p.get('label', '')} ({p.get('id', '')})" for p in report.get("recognized_phenotypes", [])],
        "", "## Исключённые HPO-признаки", "",
        *[f"- {p.get('label', '')} ({p.get('id', '')})" for p in report.get("excluded_phenotypes", [])],
        "", "## Рейтинг вариантов", "",
        "| Ранг | HPO-балл | Ген | Вариант | GT | Последствие | gnomAD AF | ClinVar | Совпадения HPO | Excluded-конфликты | Наследование / механизм | Сверка с публикацией |",
        "|---:|---:|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in report.get("variant_candidates", []):
        rank = item.get("rank") if item.get("rank") is not None else "—"
        positive = _hpo_text(item.get("positive_matches", []))
        excluded = _hpo_text(item.get("excluded_conflicts", []))
        context = item.get("inheritance_assessment", "")
        if item.get("mechanism"):
            context += " " + item["mechanism"]
        values = [rank, item.get("hpo_score") if item.get("hpo_score") is not None else "NA", item.get("gene", ""), item.get("variant", ""), item.get("genotype", ""),
                  item.get("consequence", ""), item.get("gnomad_af", ""), item.get("clinvar", ""),
                  positive, excluded, context, item.get("published_reference_check", "—")]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in values) + " |")
    lines.extend(["", "## Ограничения", *[f"- {item}" for item in report.get("limitations", []) + report.get("warnings", [])], ""])
    return "\n".join(lines)


def _ranking_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for rank, candidate in enumerate(report.get("candidates", []), 1):
        rows.append({
            "case": report["case_name"], "rank": rank,
            "condition": candidate["name"], "genes": ",".join(candidate["genes"]),
            "score_0_to_100": candidate["score_0_to_100"], "status": candidate["status"],
            "phenotype_score": candidate["experts"]["phenotype"]["score"],
            "molecular_score": candidate["experts"]["molecular"]["score"],
            "inheritance_score": candidate["experts"]["inheritance"]["score"],
        })
    return rows


def _write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    columns = fields or FIELDS
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


GENE_FIELDS = ["case", "rank", "gene", "hpo_similarity", "adjusted_hpo_score",
               "direct_hpo_matches", "excluded_conflicts", "variants"]
VARIANT_FIELDS = ["case_id", "rank", "gene", "variant", "genotype", "consequence",
                  "gnomad_af", "clinvar", "positive_matches", "excluded_conflicts",
                   "inheritance_assessment", "mechanism", "mechanism_check", "published_reference_check", "interpretation"]


def _gene_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for rank, gene in enumerate(report.get("gene_candidates", []), 1):
        rows.append({
            "case": report["case_name"],
            "rank": rank,
            "gene": gene.get("gene", ""),
            "hpo_similarity": gene.get("hpo_similarity", 0),
            "adjusted_hpo_score": gene.get("adjusted_hpo_score", 0),
            "direct_hpo_matches": _hpo_text(gene.get("directly_matched_hpo", [])),
            "excluded_conflicts": _hpo_text(gene.get("excluded_conflicts", [])),
            "variants": "; ".join(str(item.get("variant", "")) for item in gene.get("variants", [])),
        })
    return rows


def _variant_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in report.get("variant_candidates", []):
        row = dict(item)
        row["case_id"] = report.get("case_id", report.get("case_name", ""))
        row["positive_matches"] = _hpo_text(item.get("positive_matches", []))
        row["excluded_conflicts"] = _hpo_text(item.get("excluded_conflicts", []))
        rows.append(row)
    return rows


def write_reports(reports: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    all_gene_rows: list[dict[str, Any]] = []
    all_variant_rows: list[dict[str, Any]] = []
    for index, report in enumerate(reports, 1):
        stem = f"case_{index:02d}"
        (output_dir / f"{stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
        (output_dir / f"{stem}.html").write_text(render_html(report), encoding="utf-8")
        case_rows = _ranking_rows(report)
        all_rows.extend(case_rows)
        _write_tsv(output_dir / f"{stem}_ranking.tsv", case_rows)
        gene_rows = _gene_rows(report)
        all_gene_rows.extend(gene_rows)
        _write_tsv(output_dir / f"{stem}_gene_candidates.tsv", gene_rows, GENE_FIELDS)
        variant_rows = _variant_rows(report)
        all_variant_rows.extend(variant_rows)
        _write_tsv(output_dir / f"{stem}_variants.tsv", variant_rows, VARIANT_FIELDS)

    if reports:
        (output_dir / "run.json").write_text(json.dumps({
            "cases": [{"name": r["case_name"], "status": r["status"], "complete": r["complete"],
                       "prediction": r.get("prediction", "no_causal_variant_in_vcf")} for r in reports],
            "incomplete_cases": [r["case_name"] for r in reports if not r["complete"]],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_tsv(output_dir / "ranking.tsv", all_rows)
    _write_tsv(output_dir / "gene_candidates.tsv", all_gene_rows, GENE_FIELDS)
    _write_tsv(output_dir / "variant_candidates.tsv", all_variant_rows, VARIANT_FIELDS)

    # The benchmark contract is exactly two tab-separated columns.
    with (output_dir / "predictions.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["case_id", "prediction"])
        for report in reports:
            writer.writerow([
                report.get("case_id", report.get("case_name", "")),
                report.get("prediction") or "no_causal_variant_in_vcf",
            ])

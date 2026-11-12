import gzip
import io
import json
import re
from pathlib import Path
from urllib.parse import quote

import streamlit as st

st.set_page_config(page_title="Genomic Explorer", page_icon="🧬", layout="wide")

KB_PATH = Path(__file__).with_name("knowledge.json")
KB = json.loads(KB_PATH.read_text(encoding="utf-8"))


def read_text(upload):
    raw = upload.getvalue()
    if upload.name.lower().endswith(".gz"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8-sig", errors="replace")


def parse_vcf(text):
    variants = []
    errors = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line or line.startswith("##"):
            continue
        if line.startswith("#CHROM"):
            continue
        if line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 8:
            errors.append(f"Строка {line_no}: ожидалось не менее 8 колонок VCF")
            continue
        chrom, pos, vid, ref, alt, qual, filt, info = cols[:8]
        if not pos.isdigit():
            errors.append(f"Строка {line_no}: некорректная позиция")
            continue
        info_map = {}
        for item in info.split(";"):
            if "=" in item:
                k, v = item.split("=", 1)
                info_map[k] = v
            elif item:
                info_map[item] = True
        variants.append({
            "chrom": chrom, "pos": int(pos), "id": vid, "ref": ref, "alt": alt,
            "qual": qual, "filter": filt, "info": info_map,
            "gene": info_map.get("SYMBOL") or info_map.get("GENE") or info_map.get("Gene"),
            "consequence": info_map.get("Consequence") or info_map.get("ANN"),
        })
    return variants, errors


def phenotype_terms(text):
    normalized = re.sub(r"[^a-zа-яё0-9]+", " ", text.lower())
    hits = []
    for term in KB["phenotype_terms"]:
        aliases = [term["label"], *term.get("aliases", [])]
        if any(re.search(r"(?<!\w)" + re.escape(a.lower()) + r"(?!\w)", normalized) for a in aliases):
            hits.append(term)
    return hits


def analyze(variants, terms):
    observed = {str(v.get("gene", "")).upper() for v in variants if v.get("gene")}
    results = []
    for condition in KB["conditions"]:
        expected = set(condition["phenotypes"])
        matched = sorted(expected.intersection({t["hpo"] for t in terms}))
        phenotype_score = len(matched) / max(1, len(expected))
        gene_hits = [g for g in condition["genes"] if g.upper() in observed]
        # Transparent prioritization heuristic; deliberately not presented as probability.
        variant_bonus = min(0.25, 0.25 * len(gene_hits))
        score = min(1.0, 0.75 * phenotype_score + variant_bonus)
        if score > 0:
            results.append({
                **condition, "matched": matched, "phenotype_score": phenotype_score,
                "gene_hits": gene_hits, "score": score,
            })
    return sorted(results, key=lambda x: x["score"], reverse=True)


st.title("🧬 Genomic Explorer")
st.caption("Приоритизация генетических гипотез по варианту генома и фенотипу — исследовательский прототип")

with st.sidebar:
    st.subheader("Как это работает")
    st.write("Загрузите VCF, опишите фенотип и изучите ранжированные гипотезы с прозрачными основаниями и ссылками на литературу.")
    st.warning("Оценка совместимости — не клиническая вероятность и не диагноз.")

left, right = st.columns([1, 1], gap="large")
with left:
    st.subheader("1. Генетический файл")
    uploaded = st.file_uploader("Загрузить VCF", type=["vcf", "gz"], help="Поддерживаются .vcf и .vcf.gz")
    st.caption("Для определения гена в INFO желательно наличие поля SYMBOL или GENE. Аннотация не выполняется автоматически.")
with right:
    st.subheader("2. Фенотип")
    phenotype = st.text_area(
        "Опишите признаки пациента",
        placeholder="Например: высокий рост, арахнодактилия, эктопия хрусталика...",
        height=150,
    )
    st.caption("Можно вводить признаки на русском или английском. В этой версии используются только явно заданные словари синонимов.")

if st.button("Проанализировать", type="primary", use_container_width=True):
    if not uploaded:
        st.error("Сначала загрузите VCF-файл.")
    elif not phenotype.strip():
        st.error("Добавьте описание фенотипа.")
    else:
        try:
            variants, parse_errors = parse_vcf(read_text(uploaded))
            terms = phenotype_terms(phenotype)
            results = analyze(variants, terms)
            st.session_state["analysis"] = {
                "variants": variants, "errors": parse_errors, "terms": terms, "results": results
            }
        except Exception as exc:
            st.error(f"Не удалось обработать файл: {exc}")

data = st.session_state.get("analysis")
if data:
    st.divider()
    st.subheader("Результаты анализа")
    a, b, c = st.columns(3)
    a.metric("Вариантов в VCF", len(data["variants"]))
    b.metric("Распознано фенотипов", len(data["terms"]))
    c.metric("Кандидатов", len(data["results"]))
    if data["errors"]:
        with st.expander(f"Предупреждения при чтении ({len(data['errors'])})"):
            for error in data["errors"]:
                st.write("• " + error)
    if data["terms"]:
        st.write("**Распознанные признаки:** " + ", ".join(f"{t['label']} ({t['hpo']})" for t in data["terms"]))
    else:
        st.info("Словарь не распознал ни одного признака. Попробуйте добавить более точные формулировки на русском или английском.")
    if not data["variants"]:
        st.warning("В VCF не найдено валидных строк вариантов.")
    if not data["results"]:
        st.info("По текущему небольшому демонстрационному словарю кандидаты не найдены. Это не исключает генетическую причину.")
    for i, item in enumerate(data["results"], 1):
        with st.expander(f"{i}. {item['name']} — оценка совместимости {item['score']*100:.0f}/100", expanded=(i == 1)):
            st.write(item["summary"])
            st.markdown("**Почему эта гипотеза попала в список**")
            st.write(f"- Совпало фенотипических признаков: {len(item['matched'])} из {len(item['phenotypes'])}.")
            st.write(f"- Фенотипическая составляющая: {item['phenotype_score']*100:.0f}/100.")
            st.write(f"- Варианты в известных генах-кандидатах, найденные по INFO: {', '.join(item['gene_hits']) if item['gene_hits'] else 'не обнаружены / поле гена отсутствует'}.")
            st.write(f"- Гены, связанные с состоянием в демонстрационной базе: {', '.join(item['genes'])}.")
            st.write("**Совпавшие признаки**")
            st.write(", ".join(item["matched"]) if item["matched"] else "Нет точных совпадений из словаря.")
            st.markdown("**Литература и базы знаний**")
            for source in item["sources"]:
                st.markdown(f"- [{source['label']}]({source['url']})")
            q = quote(item["name"] + " " + " ".join(item["genes"]) + " phenotype genotype")
            st.markdown(f"- [Найти публикации в PubMed] (https://pubmed.ncbi.nlm.nih.gov/?term={q})")
    with st.expander("Просмотреть прочитанные варианты"):
        st.dataframe(data["variants"], use_container_width=True)
    report = {
        "notice": "Research prioritization only; score is not a clinical probability.",
        "recognized_phenotypes": [{"label": t["label"], "hpo": t["hpo"]} for t in data["terms"]],
        "variant_count": len(data["variants"]),
        "candidates": [{"name": r["name"], "score_0_to_1": round(r["score"], 4), "matched_phenotypes": r["matched"], "genes_in_vcf": r["gene_hits"], "genes": r["genes"], "sources": r["sources"]} for r in data["results"]],
        "parse_warnings": data["errors"],
    }
    st.download_button("Скачать отчёт JSON", json.dumps(report, ensure_ascii=False, indent=2), "genomic_report.json", "application/json")

st.divider()
st.caption("Ограничения: небольшой курируемый демонстрационный набор; нет полноценной VEP/ClinVar-аннотации, проверки наследования, покрытия, фазирования и калибровки вероятностей. Не используйте для постановки диагноза или выбора лечения.")

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .annotations import annotate_case
from .dataset import load_case
from .evaluation import evaluate_reports
from .knowledge import load_knowledge
from .pipeline import analyze_case
from .reporting import write_reports
from .web import serve


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genomic-detective", description="Исследовательская приоритизация генетических гипотез.")
    parser.add_argument("--version", action="version", version=f"genomic-detective {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Проверить локальную базу знаний и входной набор.")
    prepare.add_argument("--dataset", type=Path, help="Необязательный ZIP/VCF/TSV или каталог для проверки.")
    prepare.add_argument("--online", action="store_true", help="Получить consequence-аннотации через Ensembl VEP.")
    prepare.add_argument("--assembly", choices=["GRCh38"], help="Сборка генома; для online-аннотации требуется явно указать GRCh38.")
    prepare.add_argument("--cache", type=Path, default=Path("data/ensembl-vep.sqlite"))
    prepare.add_argument("--batch-size", type=int, default=200)

    run = sub.add_parser("run", help="Проанализировать VCF/TSV/ZIP и сохранить объяснимые отчёты.")
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--phenotype", default="", help="Свободное описание фенотипа или HPO ID.")
    run.add_argument("--case", default=None, help="Имя случая для отчёта.")
    run.add_argument("--output", type=Path, default=Path("outputs/demo"))
    run.add_argument("--online", action="store_true", help="Получить отсутствующие consequence-аннотации через Ensembl VEP.")
    run.add_argument("--gtex", action="store_true", help="Получить контекст медианной экспрессии генов в тканях GTEx V10 (не влияет на HPO-рейтинг).")
    run.add_argument("--assembly", choices=["GRCh38"], help="Сборка входного VCF; обязательна при --online.")
    run.add_argument("--cache", type=Path, default=Path("data/ensembl-vep.sqlite"))
    run.add_argument("--batch-size", type=int, default=200)

    evaluation = sub.add_parser("evaluate", help="Сравнить top-1 результаты с переданными ожидаемыми ответами.")
    evaluation.add_argument("--reports", type=Path, required=True)
    evaluation.add_argument("--expected", type=Path, required=True)
    evaluation.add_argument("--output", type=Path, default=Path("outputs/evaluation.json"))

    server = sub.add_parser("serve", help="Запустить локальный веб-интерфейс.")
    server.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    server.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")) )
    server.add_argument("--open", action="store_true", help="Открыть браузер после старта сервера.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        knowledge = load_knowledge()
        if args.command == "prepare":
            print(f"Локальная база знаний загружена: {len(knowledge['conditions'])} профилей заболеваний, {len(knowledge['phenotype_terms'])} фенотипических терминов.")
            if args.online and not args.dataset:
                raise ValueError("Для online prepare укажите --dataset.")
            if args.online and args.assembly != "GRCh38":
                raise ValueError("Перед online-аннотацией явно укажите --assembly GRCh38 и проверьте сборку входного файла.")
            if args.dataset:
                case = load_case(args.dataset)
                if args.online:
                    stats = annotate_case(case, args.cache, args.batch_size)
                    print(f"VEP: cache={stats['cached']}, annotated={stats['annotated']}, failed={stats['failed']}, skipped={stats['skipped']}.")
                print(f"Найдено вариантов: {len(case.variants)}; файлов-источников: {len(case.source_files)}.")
                for warning in case.warnings:
                    print(f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
                return 0 if case.variants and not case.warnings else 2
            print("Внешнее скачивание данных не выполняется; prepare проверяет локальные данные и конфигурацию.")
            return 0

        if args.command == "run":
            case = load_case(args.dataset, args.phenotype)
            if args.online:
                if args.assembly != "GRCh38":
                    raise ValueError("Перед online-аннотацией явно укажите --assembly GRCh38 и проверьте сборку входного файла.")
                stats = annotate_case(case, args.cache, args.batch_size)
                print(f"VEP: cache={stats['cached']}, annotated={stats['annotated']}, failed={stats['failed']}, skipped={stats['skipped']}.")
            if args.case:
                case.name = args.case
            report = analyze_case(case, knowledge)
            if args.gtex:
                from .gtex import GTExProvider
                report["gtex_warnings"] = GTExProvider().annotate_gene_candidates(
                    report.get("gene_candidates", []), limit=12
                )
                report["warnings"].extend(report["gtex_warnings"])
                report["gtex_metadata"] = {
                    "dataset": "gtex_v10",
                    "api": "GTEx Portal API v2",
                    "score_contribution": 0,
                }
            write_reports([report], args.output)
            print(f"Статус: {report['status']}; вариантов: {report['variant_count']}; кандидатов: {len(report['candidates'])}.")
            print(f"Отчёты сохранены в: {args.output.resolve()}")
            for warning in report["warnings"]:
                print(f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
            return 0 if report["complete"] else 2

        if args.command == "evaluate":
            result = evaluate_reports(args.reports, args.expected, args.output)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["checked"] else 2

        if args.command == "serve":
            if args.port < 1 or args.port > 65535:
                print("Порт должен быть в диапазоне 1–65535.", file=sys.stderr)
                return 1
            if args.open:
                webbrowser.open(f"http://{args.host}:{args.port}")
            serve(args.host, args.port)
            return 0
    except FileNotFoundError as exc:
        print(f"Файл не найден: {exc}", file=sys.stderr)
        return 1
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

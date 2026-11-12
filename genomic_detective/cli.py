from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import __version__
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

    run = sub.add_parser("run", help="Проанализировать VCF/TSV/ZIP и сохранить объяснимые отчёты.")
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--phenotype", default="", help="Свободное описание фенотипа или HPO ID.")
    run.add_argument("--case", default=None, help="Имя случая для отчёта.")
    run.add_argument("--output", type=Path, default=Path("outputs/demo"))

    evaluation = sub.add_parser("evaluate", help="Сравнить top-1 результаты с переданными ожидаемыми ответами.")
    evaluation.add_argument("--reports", type=Path, required=True)
    evaluation.add_argument("--expected", type=Path, required=True)
    evaluation.add_argument("--output", type=Path, default=Path("outputs/evaluation.json"))

    server = sub.add_parser("serve", help="Запустить локальный веб-интерфейс.")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--open", action="store_true", help="Открыть браузер после старта сервера.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        knowledge = load_knowledge()
        if args.command == "prepare":
            print(f"Локальная база знаний загружена: {len(knowledge['conditions'])} профилей заболеваний, {len(knowledge['phenotype_terms'])} фенотипических терминов.")
            if args.dataset:
                case = load_case(args.dataset)
                print(f"Найдено вариантов: {len(case.variants)}; файлов-источников: {len(case.source_files)}.")
                for warning in case.warnings:
                    print(f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
                return 0 if case.variants else 2
            print("Внешнее скачивание данных не выполняется; prepare проверяет локальные данные и конфигурацию.")
            return 0

        if args.command == "run":
            case = load_case(args.dataset, args.phenotype)
            if args.case:
                case.name = args.case
            report = analyze_case(case, knowledge)
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

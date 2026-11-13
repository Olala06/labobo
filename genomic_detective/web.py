from __future__ import annotations

import base64
import binascii
import html
import hmac
import ipaddress
import json
import os
import zipfile
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .annotations import annotate_case
from .dataset import parse_case_files
from .gtex import GTExProvider
from .hpo import get_hpo_engine
from .knowledge import load_knowledge
from .pipeline import analyze_case
from .reporting import render_html

MAX_UPLOAD = 50 * 1024 * 1024
MAX_REQUEST = MAX_UPLOAD * 2 + 1024 * 1024
MAX_EXPANDED = 150 * 1024 * 1024
MAX_ARCHIVE_ITEMS = 250

PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Учебная приоритизация генетических вариантов по Phenopacket JSON и VCF">
<title>Геномный детектив — загрузка файлов</title>
<style>
:root{color-scheme:light;--ink:#172733;--muted:#657784;--line:#dfe8e8;--green:#196c5a;--mint:#eaf4f0;--paper:#f4f7f6}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Inter,system-ui,-apple-system,Segoe UI,sans-serif}
header{height:70px;padding:0 max(24px,calc((100vw - 1120px)/2));display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);background:#fff}
.brand{display:flex;align-items:center;gap:12px;font-weight:750;letter-spacing:-.02em}.mark{width:34px;height:34px;border-radius:11px;background:var(--green);color:white;display:grid;place-items:center;font-size:20px}
.brand small{display:block;font-size:10px;letter-spacing:.13em;color:var(--muted);font-weight:650;text-transform:uppercase}.local{font-size:12px;color:var(--green);background:var(--mint);padding:7px 11px;border-radius:999px}
main{max-width:1040px;margin:44px auto;padding:0 22px}.intro{display:flex;justify-content:space-between;gap:26px;align-items:flex-end;margin-bottom:24px}
.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--green);text-transform:uppercase;margin:0 0 8px}
h1{font-size:clamp(28px,4vw,42px);line-height:1.12;letter-spacing:-.04em;margin:0 0 10px}.subtitle{color:var(--muted);max-width:680px;margin:0}.version{font-size:11px;color:var(--muted);white-space:nowrap;padding-bottom:7px}
.panel{background:white;border:1px solid var(--line);border-radius:18px;padding:25px;margin:16px 0;box-shadow:0 8px 28px #193c3210}
.panel-title{display:flex;gap:12px;align-items:center;margin-bottom:20px}.number{height:30px;width:30px;border-radius:10px;background:var(--mint);color:var(--green);font-weight:800;display:grid;place-items:center;font-size:12px}
h2{font-size:18px;letter-spacing:-.02em;margin:0}.field-label{display:block;font-weight:720;margin:0 0 8px}
.upload-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.upload-card{min-width:0}
.dropzone{display:block;border:1.5px dashed #a9c2bb;border-radius:15px;padding:30px 18px;text-align:center;background:#fbfdfc;cursor:pointer;transition:.15s;min-height:185px;display:flex;flex-direction:column;justify-content:center;align-items:center}
.dropzone.drag{border-color:var(--green);background:var(--mint)}.upload-icon{font-size:28px;color:var(--green);margin-bottom:7px}
.dropzone strong{display:block;font-size:15px}.dropzone span{display:block;color:var(--muted);font-size:12px;margin-top:5px}
input[type=file]{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
.file-list{font-size:12px;color:var(--muted);padding-top:9px;min-height:30px;overflow-wrap:anywhere}
.optin{display:flex;gap:11px;align-items:flex-start;padding:14px;border:1px solid var(--line);background:#fbfcfc;border-radius:12px;margin:20px 0 12px}.optin input{margin-top:4px;accent-color:var(--green)}.optin b{display:block;font-size:13px}.optin small{display:block;color:var(--muted);font-size:12px;margin-top:3px}
.actions{display:flex;justify-content:flex-end;align-items:center;gap:14px;margin-top:18px}
button.primary{background:var(--green);color:#fff;border:0;border-radius:11px;padding:13px 20px;font-weight:750;cursor:pointer;min-width:210px}
button.primary:hover{background:#125747}button:disabled{opacity:.55;cursor:wait}
.privacy{font-size:11px;color:var(--muted);max-width:520px}.notice{margin-top:18px;padding:13px 15px;background:#fff7e7;border-left:3px solid #c48b32;border-radius:8px;color:#69512b;font-size:12px}
.error{background:#fff0ed;border:1px solid #f3c5ba;border-radius:12px;padding:15px;color:#8d2e1a;white-space:pre-wrap;margin:16px 0}
footer{max-width:1040px;margin:26px auto 44px;padding:0 22px;color:var(--muted);font-size:11px;display:flex;justify-content:space-between;gap:18px}
@media(max-width:760px){main{margin:28px auto}.intro{display:block}.version{display:none}.upload-grid{grid-template-columns:1fr}.panel{padding:18px}.actions{display:block}.actions button{width:100%;margin-top:12px}header{padding:0 18px}footer{display:block}}
</style></head>
<body>
<header><div class="brand"><div class="mark">✳</div><div>GENOMIC DETECTIVE<small>EDUCATIONAL WORKSPACE</small></div></div><span class="local">● Файлы обрабатываются в памяти</span></header>
<main><section class="intro"><div><p class="eyebrow">ГЕНОМНЫЙ ДЕТЕКТИВ / УЧЕБНАЯ ВЕРСИЯ</p><h1>Загрузите фенотип и VCF</h1><p class="subtitle">Выберите JSON-файл с Phenopacket/HPO-признаками и VCF с генотипами. Система сопоставит положительные и исключённые признаки, найдёт записи вариантов и сформирует единую таблицу ранжирования.</p></div><span class="version">HPO · VCF · GRCh38</span></section>
<div id="error" class="error" role="alert" hidden></div>
<form id="upload-form" class="panel" method="post" action="/analyze" enctype="multipart/form-data">
<div class="panel-title"><span class="number">01</span><h2>Два входных файла для одного случая</h2></div>
<div class="upload-grid">
<div class="upload-card"><label class="field-label" for="phenotype-file">Файл фенотипов · JSON</label>
<label class="dropzone" id="phenotype-drop" for="phenotype-file"><div class="upload-icon">▤</div><strong>Загрузить Phenopacket JSON</strong><span>case_01_phenotype.json · положительные и excluded=true признаки</span></label>
<input id="phenotype-file" name="phenotype_file" type="file" accept=".json,application/json" required>
<div id="phenotype-list" class="file-list">Файл фенотипов не выбран</div></div>
<div class="upload-card"><label class="field-label" for="variant-file">Генетические варианты · VCF</label>
<label class="dropzone" id="variant-drop" for="variant-file"><div class="upload-icon">⇧</div><strong>Загрузить VCF с генотипами</strong><span>.vcf · .vcf.gz · sample genotype / GT</span></label>
<input id="variant-file" name="variant_file" type="file" accept=".vcf,.gz" required>
<div id="variant-list" class="file-list">VCF-файл не выбран</div></div>
</div>
<label class="optin"><input type="checkbox" name="online" value="1"><span><b>Дополнительно аннотировать варианты через Ensembl VEP и получить контекст GTEx</b><small>Необязательно. Потребуется интернет и подтверждение GRCh38. Для учебного benchmark аннотации VEP/ClinVar/gnomAD из внешних источников не предполагаются; без них соответствующие ячейки будут NA.</small></span></label>
<label class="optin" style="margin-top:8px"><input type="checkbox" name="assembly" value="GRCh38"><span><b>Подтверждаю, что координаты VCF относятся к GRCh38</b><small>Требуется только при включении внешней аннотации Ensembl VEP.</small></span></label>
<div class="actions"><span class="privacy">Не загружайте идентифицируемые медицинские данные на недоверенный или публичный сервер. Учебный рейтинг не является диагнозом.</span><button id="submit" class="primary" type="submit">Проанализировать два файла ↗</button></div>
<div class="notice">Synthetic composite genotype ≠ геном пациента. Результат — исследовательское ранжирование, а не клиническая экспертиза. Наличие варианта само по себе недостаточно для диагностики.</div>
</form></main>
<footer><span>Геномный детектив — учебная версия</span><span>Положительные и исключённые HPO · точные координаты VCF · проверка GT / inheritance</span></footer>
<script>
function bindUpload(inputId,dropId,listId,emptyText){
 const input=document.getElementById(inputId),drop=document.getElementById(dropId),list=document.getElementById(listId);
 function show(){const f=input.files[0];list.textContent=f?f.name+' ('+(f.size/1024/1024).toFixed(2)+' MB)':emptyText;}
 input.addEventListener('change',show);
 ['dragenter','dragover'].forEach(n=>drop.addEventListener(n,e=>{e.preventDefault();drop.classList.add('drag');}));
 ['dragleave','drop'].forEach(n=>drop.addEventListener(n,e=>{e.preventDefault();drop.classList.remove('drag');}));
 drop.addEventListener('drop',e=>{if(e.dataTransfer.files.length){input.files=e.dataTransfer.files;show();}});
 return input;
}
const phenotypeFile=bindUpload('phenotype-file','phenotype-drop','phenotype-list','Файл фенотипов не выбран');
const variantFile=bindUpload('variant-file','variant-drop','variant-list','VCF-файл не выбран');
document.getElementById('upload-form').addEventListener('submit',e=>{
 const error=document.getElementById('error');error.hidden=true;
 if(!phenotypeFile.files.length||!variantFile.files.length){e.preventDefault();error.textContent='Загрузите оба файла: Phenopacket JSON и VCF.';error.hidden=false;return;}
 const phenotype=phenotypeFile.files[0],variant=variantFile.files[0];
 if(!phenotype.name.toLowerCase().endsWith('.json')){e.preventDefault();error.textContent='Файл фенотипов должен иметь расширение .json.';error.hidden=false;return;}
 if(!/\.vcf(\.gz)?$/i.test(variant.name)){e.preventDefault();error.textContent='Генетический файл должен иметь расширение .vcf или .vcf.gz.';error.hidden=false;return;}
 if(phenotype.size>50*1024*1024||variant.size>50*1024*1024){e.preventDefault();error.textContent='Каждый файл должен быть не больше 50 MB.';error.hidden=false;return;}
 const online=document.querySelector('input[name=online]').checked,assembly=document.querySelector('input[name=assembly]').checked;
 if(online&&!assembly){e.preventDefault();error.textContent='Для Ensembl VEP подтвердите сборку GRCh38.';error.hidden=false;return;}
 document.getElementById('submit').disabled=true;document.getElementById('submit').textContent='Анализируем…';
});
</script></body></html>"""


def _parse_multipart(content_type: str, body: bytes) -> dict[str, list[tuple[str, bytes]]]:
    headers = (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode()
    message = BytesParser(policy=policy.default).parsebytes(headers + body)
    fields: dict[str, list[tuple[str, bytes]]] = {}
    if not message.is_multipart():
        return fields
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename() or ""
        payload = part.get_payload(decode=True) or b""
        fields.setdefault(str(name), []).append((filename, payload))
    return fields


def _expand_uploads(files: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    expanded: list[tuple[str, bytes]] = []
    total = 0
    for filename, payload in files:
        if not filename or not payload:
            continue
        if filename.lower().endswith(".zip"):
            try:
                archive = zipfile.ZipFile(BytesIO(payload))
            except zipfile.BadZipFile as exc:
                raise ValueError(f"ZIP повреждён: {Path(filename).name}") from exc
            with archive:
                members = [item for item in archive.infolist() if not item.is_dir()]
                if len(members) > MAX_ARCHIVE_ITEMS:
                    raise ValueError("В ZIP слишком много файлов (лимит 250).")
                for item in members:
                    total += int(item.file_size)
                    if total > MAX_EXPANDED or item.file_size > MAX_UPLOAD:
                        raise ValueError("Распакованный ZIP превышает безопасный лимит.")
                    safe_name = Path(item.filename.replace("\\", "/")).name
                    if not safe_name or safe_name.startswith("."):
                        continue
                    expanded.append((safe_name, archive.read(item)))
        else:
            total += len(payload)
            expanded.append((Path(filename.replace("\\", "/")).name, payload))
        if total > MAX_EXPANDED:
            raise ValueError("Общий размер файлов после распаковки превышает лимит.")
    if not expanded:
        raise ValueError("Не найдены файлы для анализа.")
    return expanded


class Handler(BaseHTTPRequestHandler):
    APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
    APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

    def _send(self, body: str | bytes, status: int = 200,
              content_type: str = "text/html; charset=utf-8") -> None:
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _authorized(self) -> bool:
        if not self.APP_PASSWORD:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:], validate=True)
            username, password = decoded.split(b":", 1)
        except (binascii.Error, ValueError):
            return False
        return (hmac.compare_digest(username, self.APP_USERNAME.encode("utf-8"))
                and hmac.compare_digest(password, self.APP_PASSWORD.encode("utf-8")))

    def _unauthorized(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Genomic Detective", charset="UTF-8"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path == "/healthz":
            self._send("ok")
            return
        if not self._authorized():
            self._unauthorized()
            return
        if url.path == "/":
            self._send(PAGE)
        elif url.path == "/hpo":
            query = parse_qs(url.query).get("q", [""])[0][:120]
            try:
                results = get_hpo_engine().search(query)
                self._send(json.dumps(results, ensure_ascii=False),
                           content_type="application/json; charset=utf-8")
            except Exception as exc:
                self._send(json.dumps({"error": f"HPO search unavailable: {type(exc).__name__}"},
                                      ensure_ascii=False), 503, "application/json; charset=utf-8")
        else:
            self._send("<h1>404</h1><p>Not found</p>", 404)

    def do_POST(self) -> None:
        if not self._authorized():
            self._unauthorized()
            return
        if urlsplit(self.path).path != "/analyze":
            self._send("<h1>404</h1>", 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
        if length <= 0 or length > MAX_REQUEST:
            self._send("<h1>Ошибка</h1><p>Размер запроса с двумя файлами должен быть не больше 101 МБ.</p><a href='/'>Назад</a>", 413)
            self._send("<h1>Ошибка</h1><p>Размер загрузки должен быть от 1 байта до 50 МБ.</p><a href='/'>Назад</a>", 413)
            return
        if not self.headers.get("Content-Type", "").lower().startswith("multipart/form-data"):
            self._send("<h1>Ожидается multipart/form-data</h1><a href='/'>Назад</a>", 400)
            return

        try:
            fields = _parse_multipart(self.headers.get("Content-Type", ""), self.rfile.read(length))
            phenotype_uploads = fields.get("phenotype_file", [])
            variant_uploads = fields.get("variant_file", [])
            if len(phenotype_uploads) != 1 or len(variant_uploads) != 1:
                raise ValueError("Загрузите ровно один JSON-файл фенотипов и один VCF-файл.")
            phenotype_name, phenotype_payload = phenotype_uploads[0]
            variant_name, variant_payload = variant_uploads[0]
            phenotype_name = Path(phenotype_name.replace(chr(92), "/")).name
            variant_name = Path(variant_name.replace(chr(92), "/")).name
            if not phenotype_name.lower().endswith(".json"):
                raise ValueError("Файл фенотипов должен иметь расширение .json.")
            if not variant_name.lower().endswith((".vcf", ".vcf.gz")):
                raise ValueError("Генетический файл должен иметь расширение .vcf или .vcf.gz.")
            if not phenotype_payload or not variant_payload:
                raise ValueError("Оба входных файла должны быть непустыми.")
            if len(phenotype_payload) > MAX_UPLOAD or len(variant_payload) > MAX_UPLOAD:
                raise ValueError("Размер каждого входного файла не должен превышать 50 МБ.")
            case = parse_case_files(
                [(variant_name, variant_payload), (phenotype_name, phenotype_payload)],
                Path(variant_name).stem,
            )
            if not case.phenotype_features:
                raise ValueError("JSON не содержит распознаваемых положительных или исключённых HPO-признаков.")
            if not case.variants:
                details = "; ".join(case.warnings[:4])
                raise ValueError("В VCF не найдены варианты. " + details)

            online = bool(fields.get("online", []))
            assembly = bool(fields.get("assembly", []))
            if online and not assembly:
                raise ValueError("Для внешней аннотации Ensembl VEP необходимо явно подтвердить сборку GRCh38.")
            vep_stats = None
            if online:
                vep_stats = annotate_case(case)
            report = analyze_case(case, load_knowledge())
            if vep_stats is not None:
                report["vep"] = vep_stats
                report["sources"]["vep"] = "Ensembl VEP REST API (GRCh38)"
                report["gtex_warnings"] = GTExProvider().annotate_gene_candidates(
                    report.get("gene_candidates", []), limit=12)
                report["warnings"].extend(report["gtex_warnings"])
                report["gtex_metadata"] = {
                    "dataset": "gtex_v10",
                    "api": "GTEx Portal API v2",
                    "queried_genes": sum(1 for item in report.get("gene_candidates", [])
                                         if (item.get("gtex") or {}).get("status") == "available"),
                    "score_contribution": 0,
                }
            return self._send(render_html(report))
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            message = html.escape(str(exc))
            self._send(f"<h1>Не удалось обработать данные</h1><p>{message}</p><a href='/'>Назад</a>", 400)
        except Exception as exc:
            # Keep server internals and uploaded data out of the HTTP response.
            self._send(
                "<h1>Ошибка анализа</h1><p>Обработка не завершилась. "
                f"Тип ошибки: {html.escape(type(exc).__name__)}.</p><a href='/'>Назад</a>", 500)

    def log_message(self, format: str, *args: object) -> None:
        # Do not log uploaded contents or query strings.
        super().log_message(format, self.command, self.path.split("?", 1)[0], "request")


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    password = os.environ.get("APP_PASSWORD", "")
    username = os.environ.get("APP_USERNAME", "admin")
    if not _is_loopback(host) and len(password) < 16:
        raise ValueError("For a public host, set APP_PASSWORD to a random secret of at least 16 characters.")
    Handler.APP_USERNAME = username
    Handler.APP_PASSWORD = password
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Геномный детектив доступен: http://{host}:{port}")
    print("Режим запуска: без демонстрационных кейсов — каждый запуск начинается с загрузки генетического файла.")
    if password:
        print(f"Включена HTTP Basic авторизация для пользователя: {username}")
    print("Остановить сервер: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    finally:
        server.server_close()

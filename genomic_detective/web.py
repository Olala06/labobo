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
MAX_EXPANDED = 150 * 1024 * 1024
MAX_ARCHIVE_ITEMS = 250

PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Локальная исследовательская приоритизация генов по фенотипу HPO и контексту экспрессии GTEx">
<title>Genomic Detective — загрузка генома</title>
<style>
:root{color-scheme:light;--ink:#172733;--muted:#657784;--line:#dfe8e8;--green:#196c5a;--mint:#eaf4f0;--paper:#f4f7f6}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Inter,system-ui,-apple-system,Segoe UI,sans-serif}
header{height:70px;padding:0 max(24px,calc((100vw - 1120px)/2));display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);background:#fff}
.brand{display:flex;align-items:center;gap:12px;font-weight:750;letter-spacing:-.02em}.mark{width:34px;height:34px;border-radius:11px;background:var(--green);color:white;display:grid;place-items:center;font-size:20px}
.brand small{display:block;font-size:10px;letter-spacing:.13em;color:var(--muted);font-weight:650;text-transform:uppercase}.local{font-size:12px;color:var(--green);background:var(--mint);padding:7px 11px;border-radius:999px}
main{max-width:1040px;margin:44px auto;padding:0 22px}.intro{display:flex;justify-content:space-between;gap:26px;align-items:flex-end;margin-bottom:24px}
.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--green);text-transform:uppercase;margin:0 0 8px}
h1{font-size:clamp(28px,4vw,42px);line-height:1.12;letter-spacing:-.04em;margin:0 0 10px}.subtitle{color:var(--muted);max-width:620px;margin:0}.version{font-size:11px;color:var(--muted);white-space:nowrap;padding-bottom:7px}
.panel{background:white;border:1px solid var(--line);border-radius:18px;padding:25px;margin:16px 0;box-shadow:0 8px 28px #193c3210}
.panel-title{display:flex;gap:12px;align-items:center;margin-bottom:20px}.number{height:30px;width:30px;border-radius:10px;background:var(--mint);color:var(--green);font-weight:800;display:grid;place-items:center;font-size:12px}
h2{font-size:18px;letter-spacing:-.02em;margin:0}.field-label{display:block;font-weight:720;margin:0 0 8px}
.dropzone{display:block;border:1.5px dashed #a9c2bb;border-radius:15px;padding:28px 18px;text-align:center;background:#fbfdfc;cursor:pointer;transition:.15s}
.dropzone.drag{border-color:var(--green);background:var(--mint)}.upload-icon{font-size:28px;color:var(--green);margin-bottom:7px}
.dropzone strong{display:block;font-size:15px}.dropzone span{display:block;color:var(--muted);font-size:12px;margin-top:5px}
input[type=file]{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
.file-list{font-size:12px;color:var(--muted);padding-top:9px;min-height:22px;overflow-wrap:anywhere}
textarea,input[type=search]{width:100%;padding:12px 13px;border:1px solid #ccd9d7;border-radius:10px;background:#fff;color:var(--ink);font:inherit;outline:none}
textarea{min-height:105px;resize:vertical}textarea:focus,input[type=search]:focus{border-color:var(--green);box-shadow:0 0 0 3px #196c5a17}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}.helper{font-size:12px;color:var(--muted);margin:7px 0 0}
.hpo-search{position:relative;margin-top:14px}.suggestions{position:absolute;z-index:4;top:100%;left:0;right:0;background:white;border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 28px #17273320;overflow:hidden;max-height:230px;overflow-y:auto}
.suggestion{display:block;border:0;border-bottom:1px solid #edf1ef;border-radius:0;background:white;color:var(--ink);padding:10px 12px;text-align:left;font-weight:600;cursor:pointer}.suggestion:hover{background:var(--mint)}.suggestion small{display:block;color:var(--muted);font-weight:500}
.optin{display:flex;gap:11px;align-items:flex-start;padding:14px;border:1px solid var(--line);background:#fbfcfc;border-radius:12px;margin:20px 0 12px}.optin input{margin-top:4px;accent-color:var(--green)}.optin b{display:block;font-size:13px}.optin small{display:block;color:var(--muted);font-size:12px;margin-top:3px}
.actions{display:flex;justify-content:flex-end;align-items:center;gap:14px;margin-top:18px}
button.primary{background:var(--green);color:#fff;border:0;border-radius:11px;padding:13px 20px;font-weight:750;cursor:pointer;min-width:190px}
button.primary:hover{background:#125747}button:disabled{opacity:.55;cursor:wait}
.privacy{font-size:11px;color:var(--muted);max-width:520px}.notice{margin-top:18px;padding:13px 15px;background:#fff7e7;border-left:3px solid #c48b32;border-radius:8px;color:#69512b;font-size:12px}
.error{background:#fff0ed;border:1px solid #f3c5ba;border-radius:12px;padding:15px;color:#8d2e1a;white-space:pre-wrap;margin:16px 0}
footer{max-width:1040px;margin:26px auto 44px;padding:0 22px;color:var(--muted);font-size:11px;display:flex;justify-content:space-between;gap:18px}
@media(max-width:760px){main{margin:28px auto}.intro{display:block}.version{display:none}.grid{grid-template-columns:1fr}.panel{padding:18px}.actions{display:block}.actions button{width:100%;margin-top:12px}header{padding:0 18px}footer{display:block}}
</style></head>
<body>
<header><div class="brand"><div class="mark">✳</div><div>GENOMIC DETECTIVE<small>RESEARCH WORKSPACE</small></div></div><span class="local">● Локальная обработка</span></header>
<main><section class="intro"><div><p class="eyebrow">ГЕНОМНЫЙ АНАЛИЗ / ЗАГРУЗКА</p><h1>От генетического файла<br>к генам-кандидатам</h1><p class="subtitle">Загрузите VCF/TSV и опишите фенотип. PyHPO сопоставит клинические признаки с генными аннотациями; GTEx добавит контекст экспрессии по тканям.</p></div><span class="version">HPO · GTEx V10 · Ensembl VEP</span></section>
<div id="error" class="error" role="alert" hidden></div>
<form id="upload-form" class="panel" method="post" action="/analyze" enctype="multipart/form-data">
<div class="panel-title"><span class="number">01</span><h2>Генетические данные</h2></div>
<label class="dropzone" id="dropzone" for="files"><div class="upload-icon">⇧</div><strong>Перетащите файлы сюда или нажмите для выбора</strong><span>VCF · VCF.GZ · TSV · ZIP · можно выбрать несколько файлов</span></label>
<input id="files" name="files" type="file" accept=".vcf,.gz,.tsv,.zip" multiple required>
<div id="file-list" class="file-list">Файлы ещё не выбраны</div>
<div style="height:20px"></div>
<div class="panel-title"><span class="number">02</span><h2>Фенотип пациента</h2></div>
<div class="grid"><div><label class="field-label" for="phenotype">Клинические признаки / HPO ID</label>
<textarea id="phenotype" name="phenotype" placeholder="Например: HP:0002650, HP:0001166&#10;или названия признаков на английском, по одному/через запятую"></textarea>
<p class="helper">Можно вставить HPO ID или название признака. Для точного сопоставления используйте поиск HPO справа.</p></div>
<div><label class="field-label" for="hpo-search">Найти термин в HPO</label>
<div class="hpo-search"><input type="search" id="hpo-search" placeholder="Например, scoliosis или HP:0002650" autocomplete="off" maxlength="120">
<div id="suggestions" class="suggestions" hidden></div></div>
<p class="helper">Выберите термин из списка — его HPO ID добавится в поле фенотипа.</p>
<div class="notice">Точный HPO ID предпочтительнее свободной формулировки. Не найденные фразы не трактуются как отсутствие симптома.</div></div></div>
<label class="optin"><input type="checkbox" name="online" value="1"><span><b>Подключить Ensembl VEP и GTEx (опционально)</b><small>Потребуется интернет. Ensembl получит координаты и аллели вариантов для аннотации; GTEx получит только ID/символы генов. Текст фенотипа этим сервисам не отправляется.</small></span></label>
<label class="optin" style="margin-top:8px"><input type="checkbox" name="assembly" value="GRCh38"><span><b>Подтверждаю, что VCF использует сборку GRCh38</b><small>Обязательно для внешней аннотации Ensembl VEP. Если не уверены, оставьте онлайн-аннотацию выключенной.</small></span></label>
<div class="actions"><span class="privacy">Локальный режим не отправляет файлы наружу. Сетевые запросы выполняются только после установки флажка выше.</span><button id="submit" class="primary" type="submit">Проанализировать данные ↗</button></div>
</form></main>
<footer><span>Исследовательский инструмент. Не является медицинским изделием или диагностической системой.</span><span>HPO gene similarity ≠ вероятность заболевания · GTEx ≠ доказательство патогенности</span></footer>
<script>
const files=document.getElementById('files'), fileList=document.getElementById('file-list'), drop=document.getElementById('dropzone');
function showFiles(){fileList.textContent=files.files.length?Array.from(files.files).map(f=>f.name+' ('+(f.size/1024/1024).toFixed(2)+' MB)').join(' · '):'Файлы ещё не выбраны';}
files.addEventListener('change',showFiles);
['dragenter','dragover'].forEach(n=>drop.addEventListener(n,e=>{e.preventDefault();drop.classList.add('drag');}));
['dragleave','drop'].forEach(n=>drop.addEventListener(n,e=>{e.preventDefault();drop.classList.remove('drag');}));
drop.addEventListener('drop',e=>{if(e.dataTransfer.files.length){files.files=e.dataTransfer.files;showFiles();}});
const search=document.getElementById('hpo-search'), suggestions=document.getElementById('suggestions'), phenotype=document.getElementById('phenotype');
let delay=null, controller=null;
search.addEventListener('input',()=>{
 clearTimeout(delay); const q=search.value.trim();
 if(q.length<2){suggestions.hidden=true;return;}
 delay=setTimeout(async()=>{
   if(controller)controller.abort(); controller=new AbortController();
   try{
     const response=await fetch('/hpo?q='+encodeURIComponent(q),{signal:controller.signal});
     const items=await response.json(); suggestions.replaceChildren();
     if(!response.ok) throw new Error(items.error||'HPO search unavailable');
     items.forEach(item=>{
       const button=document.createElement('button');button.type='button';button.className='suggestion';
       button.textContent=item.label;
       const small=document.createElement('small');small.textContent=item.id;button.appendChild(small);
       button.addEventListener('click',()=>{
         const id=item.id;const current=phenotype.value.trim();
         const ids=current.split(/[\\s,;]+/).filter(Boolean);
         if(!ids.includes(id)) phenotype.value=current?(current.replace(/[,;\\s]+$/,'')+', '+id):id;
         search.value=item.label;suggestions.hidden=true;phenotype.focus();
       });suggestions.appendChild(button);
     });
     suggestions.hidden=!items.length;
   }catch(error){if(error.name!=='AbortError'){suggestions.replaceChildren();const item=document.createElement('div');item.className='suggestion';item.textContent='Поиск HPO временно недоступен';suggestions.appendChild(item);suggestions.hidden=false;}}
 },250);
});
document.addEventListener('click',e=>{if(!e.target.closest('.hpo-search'))suggestions.hidden=true;});
document.getElementById('upload-form').addEventListener('submit',e=>{
 const error=document.getElementById('error');error.hidden=true;
 if(!files.files.length){e.preventDefault();error.textContent='Выберите генетический файл.';error.hidden=false;return;}
 const online=document.querySelector('input[name=online]').checked;
 const assembly=document.querySelector('input[name=assembly]').checked;
 if(online&&!assembly){e.preventDefault();error.textContent='Для Ensembl VEP подтвердите сборку GRCh38.';error.hidden=false;return;}
 if(Array.from(files.files).some(f=>f.size>50*1024*1024)){e.preventDefault();error.textContent='Один из файлов превышает лимит 50 MB.';error.hidden=false;return;}
 document.getElementById('submit').disabled=true;document.getElementById('submit').textContent='Анализируем…';
});
</script></body></html>"""


def _parse_multipart(content_type: str, body: bytes) -> dict[str, list[tuple[str, bytes]]]:
    headers = (f"Content-Type: {content_type}\\r\\nMIME-Version: 1.0\\r\\n\\r\\n").encode()
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
            length = 0
        if length <= 0 or length > MAX_UPLOAD:
            self._send("<h1>Ошибка</h1><p>Размер загрузки должен быть от 1 байта до 50 МБ.</p><a href='/'>Назад</a>", 413)
            return
        if not self.headers.get("Content-Type", "").lower().startswith("multipart/form-data"):
            self._send("<h1>Ожидается multipart/form-data</h1><a href='/'>Назад</a>", 400)
            return

        try:
            fields = _parse_multipart(self.headers.get("Content-Type", ""), self.rfile.read(length))
            uploads = fields.get("files", []) + fields.get("file", [])
            files = _expand_uploads(uploads)
            phenotype = fields.get("phenotype", [("", b"")])[0][1].decode("utf-8", errors="replace")
            if len(phenotype) > 20000:
                raise ValueError("Поле фенотипа превышает 20 000 символов.")
            if not any(name.lower().endswith((".vcf", ".vcf.gz", ".tsv")) for name, _ in files):
                raise ValueError("Нужен хотя бы один файл VCF, VCF.GZ или TSV с вариантами.")
            analysis_name = Path(files[0][0]).stem[:80] or "uploaded_genome"
            case = parse_case_files(files, analysis_name, phenotype)
            if not case.variants:
                details = "; ".join(case.warnings[:4])
                raise ValueError("В файле не найдены варианты. " + details)

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

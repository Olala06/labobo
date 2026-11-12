from __future__ import annotations

import html
import json
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .dataset import uploaded_case
from .knowledge import load_knowledge
from .pipeline import analyze_case
from .reporting import render_html


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Геномный детектив</title><style>
*{box-sizing:border-box}body{font:16px/1.5 system-ui,sans-serif;background:#f5f7fb;color:#192334;margin:0}
main{max-width:1000px;margin:40px auto;padding:0 20px}.hero,.card{background:white;border:1px solid #dce2ea;border-radius:16px;padding:24px;margin:18px 0}
h1{margin:0 0 8px;font-size:32px}.muted{color:#657184}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
label{display:block;font-weight:650;margin:8px 0}textarea,input[type=file]{width:100%;margin:8px 0 12px;padding:12px;border:1px solid #cbd3df;border-radius:10px;background:#fff}
textarea{min-height:150px;font:inherit}button{background:#184f46;color:white;border:0;border-radius:10px;padding:14px 18px;font-weight:700;cursor:pointer;width:100%}
.notice{padding:14px;background:#fff5df;border-left:4px solid #bd8427;border-radius:6px}a{color:#145c96}
@media(max-width:720px){.grid{grid-template-columns:1fr}main{margin:18px auto}}
</style></head><body><main><section class="hero"><h1>🧬 Геномный детектив</h1>
<p>Исследовательская приоритизация генетических гипотез по вариантам и фенотипу.</p>
<p class="notice">Балл — эвристическая оценка для ранжирования, а не вероятность диагноза. Не используйте для клинических решений.</p></section>
<form class="card" method="post" action="/analyze" enctype="multipart/form-data">
<div class="grid"><div><label for="file">1. Генетические данные</label><input id="file" name="file" type="file" accept=".vcf,.gz,.zip,.tsv" required>
<p class="muted">VCF, VCF.GZ, TSV или ZIP с файлами вариантов и фенотипа HPO.</p></div>
<div><label for="phenotype">2. Фенотип</label><textarea id="phenotype" name="phenotype" placeholder="Опишите клинические признаки или перечислите HPO ID..."></textarea>
<p class="muted">Поддерживаются только термины из демонстрационного словаря.</p></div></div><button type="submit">Проанализировать</button></form>
<p class="muted">Локальный режим: загруженные данные обрабатываются этим процессом и не отправляются на внешний API.</p></main></body></html>"""


def _parse_multipart(content_type: str, body: bytes) -> dict[str, tuple[str, bytes]]:
    headers = (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode()
    message = BytesParser(policy=policy.default).parsebytes(headers + body)
    fields: dict[str, tuple[str, bytes]] = {}
    if not message.is_multipart():
        return fields
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename() or ""
        payload = part.get_payload(decode=True) or b""
        fields[str(name)] = (filename, payload)
    return fields


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: str, status: int = 200) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/":
            self._send(PAGE)
        else:
            self._send("<h1>404</h1><p>Not found</p>", 404)

    def do_POST(self) -> None:
        if self.path != "/analyze":
            self._send("<h1>404</h1>", 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 50 * 1024 * 1024:
            self._send("<h1>Ошибка</h1><p>Размер загрузки должен быть от 1 байта до 50 МБ.</p>", 413)
            return
        fields = _parse_multipart(self.headers.get("Content-Type", ""), self.rfile.read(length))
        filename, file_content = fields.get("file", ("", b""))
        phenotype = fields.get("phenotype", ("", b""))[1].decode("utf-8", errors="replace")
        if not filename or not file_content:
            self._send("<h1>Не выбран файл</h1><a href='/'>Назад</a>", 400)
            return
        try:
            case = uploaded_case(filename, file_content, phenotype)
            report = analyze_case(case, load_knowledge())
            self._send(render_html(report) + "<p><a href='/'>← Новый анализ</a></p>")
        except Exception as exc:
            self._send(f"<h1>Не удалось обработать данные</h1><pre>{html.escape(str(exc))}</pre><a href='/'>Назад</a>", 400)

    def log_message(self, format: str, *args: object) -> None:
        # Keep local server output minimal; do not print uploaded content.
        super().log_message(format, *args)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Геномный детектив доступен: http://{host}:{port}")
    print("Остановить сервер: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    finally:
        server.server_close()

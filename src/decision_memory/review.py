"""A loopback-only human review surface. It is deliberately not an MCP tool."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, urlsplit

from .store import MemoryError, Store, digest


def create_server(store: Store, port: int = 0) -> ThreadingHTTPServer:
    capability = secrets.token_urlsafe(32)
    pending = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # URLs contain the local capability; don't write them to access logs.

        def reply(self, code, value, content_type="application/json; charset=utf-8"):
            raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def allowed(self):
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != host:
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://{host}":
                return False
            return urlsplit(self.path).path.startswith(f"/review/{capability}/")

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {"error": "此页面仅供本机授权审核"})
            suffix = urlsplit(self.path).path.removeprefix(f"/review/{capability}/")
            try:
                if suffix == "":
                    raw = (Path(__file__).parent / "web/review.html").read_bytes()
                    return self.reply(200, raw, "text/html; charset=utf-8")
                if suffix == "api/list":
                    records, warnings = store.inventory()
                    return self.reply(200, {"drafts": store.drafts(), "warnings": warnings,
                        "records": [{"id": r["record"].id, "title": r["record"].title,
                                     "version": r["entry"]["version"], "sha256": r["entry"]["sha256"]}
                                    for r in records]})
                if suffix == "api/identity":
                    return self.reply(200, {"pid": os.getpid(), "vault": str(store.root)})
                if suffix == "api/draft":
                    relative = parse_qs(urlsplit(self.path).query).get("path", [""])[0]
                    record, raw = store.draft(relative)
                    token = secrets.token_urlsafe(24)
                    pending[token] = (relative, digest(raw))
                    return self.reply(200, {"record": record.model_dump(), "sha256": digest(raw),
                                            "review_token": token, "path": relative})
                if suffix == "api/record":
                    record_id = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
                    manifest = store._manifest()
                    entry = manifest["entries"].get(record_id)
                    if not entry or entry["status"] != "active":
                        raise MemoryError("记录不存在或已停用")
                    record, _ = store._load_entry(record_id, entry)
                    token = secrets.token_urlsafe(24)
                    pending[token] = (record_id, entry["sha256"])
                    return self.reply(200, {"record": record.model_dump(), "version": entry["version"],
                                            "sha256": entry["sha256"], "review_token": token})
                return self.reply(404, {"error": "页面不存在"})
            except (OSError, ValueError) as exc:
                return self.reply(400, {"error": str(exc)})

        def do_POST(self):
            if not self.allowed():
                return self.reply(403, {"error": "请求来源不匹配"})
            try:
                if self.headers.get("Content-Type") != "application/json":
                    raise MemoryError("需要 JSON 请求")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise MemoryError("请求大小不正确")
                data = json.loads(self.rfile.read(length))
                if data.get("confirmed") is not True:
                    raise MemoryError("请先确认已经审核")
                token = data.get("review_token", "")
                reviewed = pending.get(token)
                if not reviewed:
                    raise MemoryError("请先重新阅读这条记录")
                target, expected_hash = reviewed
                suffix = urlsplit(self.path).path.removeprefix(f"/review/{capability}/")
                if suffix == "api/publish" and target.startswith("drafts/"):
                    result = store.publish(target, expected_hash)
                elif suffix == "api/revoke" and not target.startswith("drafts/"):
                    result = store.revoke(target, expected_hash)
                else:
                    raise MemoryError("此确认不适用于该操作")
                pending.pop(token, None)
                return self.reply(200, result)
            except (OSError, ValueError, TypeError) as exc:
                return self.reply(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.review_url = f"http://127.0.0.1:{server.server_port}/review/{capability}/"
    return server

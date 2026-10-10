"""
เซิร์ฟเวอร์สำหรับทดสอบในเครื่อง (ใช้แทน Live Server / http.server)

  http://127.0.0.1:5500/          -> ไฟล์ในโฟลเดอร์ frontend/ (หน้าแรกของระบบ)
  http://127.0.0.1:5500/api/...   -> ส่งต่อไป Django ที่ http://127.0.0.1:8000/api/...
  /admin/, /static/, /media/      -> ส่งต่อไป Django เช่นกัน

วิธีใช้ (เปิด 2 เทอร์มินัล):
  1) cd backend ; python manage.py runserver            (พอร์ต 8000)
  2) python dev_server.py                                (อยู่ที่โฟลเดอร์รากโปรเจกต์)

หมายเหตุ: ไม่ตัด /api ออกตอนส่งต่อ เพราะเส้นทางของ Django ขึ้นต้นด้วย /api/ อยู่แล้ว
"""
import http.server
import os
import socketserver
import sys
import urllib.error
import urllib.request

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
BACKEND = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
PORT = int(os.environ.get("PORT", "5500"))
PROXY_PREFIXES = ("/api/", "/admin/", "/static/", "/media/")
HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
              "proxy-authorization", "proxy-authenticate"}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def _is_proxy(self):
        return self.path.startswith(PROXY_PREFIXES) or self.path in ("/api", "/admin")

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        # คง Host เดิม (เช่น 127.0.0.1:5500) เพื่อให้ลิงก์รูปที่ Django สร้างชี้กลับมาที่พอร์ตนี้
        req = urllib.request.Request(BACKEND + self.path, data=body, headers=headers, method=self.command)
        try:
            resp = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as err:
            resp = err
        except Exception as exc:  # backend ปิดอยู่
            msg = f"เชื่อมต่อ backend ไม่ได้ ({exc}) — เปิด python manage.py runserver แล้วหรือยัง".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return
        data = resp.read()
        self.send_response(resp.status if hasattr(resp, "status") else resp.code)
        for k, v in resp.headers.items():
            if k.lower() not in HOP_BY_HOP and k.lower() != "content-length":
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _dispatch(self):
        if self._is_proxy():
            self._proxy()
        elif self.command in ("GET", "HEAD"):
            (super().do_GET if self.command == "GET" else super().do_HEAD)()
        else:
            self.send_error(405)

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _dispatch

    def end_headers(self):
        if not self._is_proxy():
            self.send_header("Cache-Control", "no-store")  # กันเบราว์เซอร์จำไฟล์เก่าตอนพัฒนา
        super().end_headers()


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    if not os.path.isdir(FRONTEND_DIR):
        sys.exit(f"ไม่พบโฟลเดอร์ {FRONTEND_DIR} — รันไฟล์นี้จากโฟลเดอร์รากของโปรเจกต์")
    print(f"หน้าเว็บ  : http://127.0.0.1:{PORT}/")
    print(f"ส่งต่อ API : /api /admin /static /media -> {BACKEND}")
    Server(("127.0.0.1", PORT), Handler).serve_forever()
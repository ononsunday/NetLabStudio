import http.server, threading, urllib.request
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"local HTTP response"
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
try:
    with urllib.request.urlopen("http://127.0.0.1:%d/" % server.server_port, timeout=2) as response:
        print("status:", response.status); print(response.read().decode())
finally:
    server.shutdown(); server.server_close(); thread.join(2)

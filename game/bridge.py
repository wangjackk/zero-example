\"\"\"Game Bridge: 游戏浏览器 <-> Agent 通信桥梁。

GET  /api/level   -> 返回当前关卡配置 (JSON)
POST /api/report  -> 游戏上报关卡结果,写入队列供 Agent 轮询
GET  /api/poll    -> Agent 轮询新上报 (内部用)
POST /api/level   -> Agent 写入新关卡配置

运行在 127.0.0.1:9100。
\"\"\"
import json, threading, time
from http.server import HTTPServer, BaseHTTPRequestHandler

# ---- 共享状态 ----
_state_lock = threading.Lock()
_current_level = {
    "level": 1,
    "name": "第 1 关 - 热身",
    "enemies": [
        {"type": "grunt", "count": 5, "speed": 1.0, "hp": 1, "shoot": False}
    ],
    "spawn_interval": 1500,
    "boss": None,
    "desc": "简单的敌人，慢慢来。"
}
_report_queue = []  # [(timestamp, {level, result, stats})]

class BridgeHandler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        if self.path == '/api/level':
            with _state_lock:
                self.wfile.write(json.dumps(_current_level).encode())
        elif self.path == '/api/poll':
            with _state_lock:
                # 返回并清空队列
                reports = list(_report_queue)
                _report_queue.clear()
            self.wfile.write(json.dumps({"reports": reports}).encode())
        else:
            self.wfile.write(json.dumps({"error": "not found"}).encode())

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length else '{}'
        data = json.loads(body)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()

        if self.path == '/api/report':
            with _state_lock:
                _report_queue.append((time.time(), data))
            self.wfile.write(json.dumps({"ok": True}).encode())
        elif self.path == '/api/level':
            global _current_level
            with _state_lock:
                _current_level = data
            self.wfile.write(json.dumps({"ok": True}).encode())
        else:
            self.wfile.write(json.dumps({"error": "not found"}).encode())

    def log_message(self, *args):
        pass  # 安静

def run_server():
    server = HTTPServer(('127.0.0.1', 9100), BridgeHandler)
    print("Game Bridge running on http://127.0.0.1:9100")
    server.serve_forever()

if __name__ == '__main__':
    run_server()

"""The self-hosted AI path: an OpenAI-compatible server (as vLLM serves it) selected by env."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from sonariq.llm import LLM, OpenAICompatGateway, make_gateway


class _Stub(BaseHTTPRequestHandler):
    reply = "Stair 3B needs 1,380 mm and has 1,350 mm."

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["messages"][0]["role"] == "system"
        out = json.dumps({"choices": [{"message": {"content": _Stub.reply}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def _serve():
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_env_selects_the_openai_compatible_gateway(monkeypatch):
    monkeypatch.setenv("SONARIQ_AI_GATEWAY", "vllm")
    monkeypatch.setenv("SONARIQ_AI_URL", "http://10.0.0.5:8000/v1")
    g = make_gateway()
    assert isinstance(g, OpenAICompatGateway) and g.name.endswith("@10.0.0.5:8000")


def test_self_hosted_server_answers_through_the_gateway(monkeypatch, tmp_path):
    monkeypatch.setenv("SONARIQ_AI", "on")
    monkeypatch.setattr("sonariq.llm.CACHE", tmp_path)
    srv = _serve()
    llm = LLM(OpenAICompatGateway(url=f"http://127.0.0.1:{srv.server_port}/v1", model="stub"))
    text, src = llm.call("sys", "prompt", use_cache=False)
    assert src == "ai" and "1,380" in text
    srv.shutdown()

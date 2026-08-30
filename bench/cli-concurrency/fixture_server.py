"""Serve a deterministic model fixture, outside the benchmark's constrained cgroup.

This measures CLI startup and tool overhead. Its canned tokens are never evidence of real
model throughput. Only loopback HTTP is exposed, and request credentials are never logged.
"""

# ruff: noqa: INP001 -- launched by path, outside the installed package

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import json
import resource
import sys
import threading
import time
import zlib
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fixture_plan import Turn, auxiliary_reason, declared, locate, request_shape
from fixture_wire import response

MAX_BODY = 32 * 1024 * 1024
HISTORY_LIMIT = 4096


def _protocol(path: str) -> str:
    for suffix, protocol in (
        (":generateContent", "gemini"),
        (":streamGenerateContent", "gemini"),
        (":countTokens", "gemini"),
        ("/messages", "anthropic"),
        ("/responses", "responses"),
        ("/chat/completions", "chat"),
    ):
        if path.endswith(suffix):
            return protocol
    raise ValueError("Unknown fixture model route")


class Fixture(ThreadingHTTPServer):
    """Hold bounded Responses continuation state and nonsecret measurement records."""

    daemon_threads = True
    request_queue_size = 256

    def __init__(self, port: int, log: Path, models: list[str]) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.log = log
        self.models = models
        self.lock = threading.Lock()
        self.history: OrderedDict[str, Turn] = OrderedDict()
        self.first: set[tuple[str, str]] = set()
        self.active = 0

    def previous(self, ident: str) -> Turn | None:
        with self.lock:
            return self.history.get(ident)

    def remember(self, ident: str, turn: Turn | None) -> None:
        if turn is None:
            return
        with self.lock:
            self.history[ident] = turn
            while len(self.history) > HISTORY_LIMIT:
                self.history.popitem(last=False)

    def write(self, row: dict[str, Any]) -> None:
        with self.lock, self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")


class Handler(BaseHTTPRequestHandler):
    """Serve only model-fixture routes and avoid retaining any authentication headers."""

    protocol_version = "HTTP/1.1"
    server: Fixture

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 -- stdlib signature
        pass

    def _json(self, body: dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

    def _stream(self, chunks: list[tuple[str | None, Any]]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for event, chunk in chunks:
            payload = chunk if isinstance(chunk, str) else json.dumps(chunk)
            self.wfile.write(
                (
                    (f"event: {event}\n" if event else "") + f"data: {payload}\n\n"
                ).encode()
            )
        self.wfile.flush()
        self.close_connection = True

    def do_GET(self) -> None:
        """Expose model discovery and a models.dev-shaped local registry."""
        path = self.path.split("?", 1)[0]
        if path.endswith("/models"):
            self._json(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": model,
                            "object": "model",
                            "created": 1700000000,
                            "owned_by": "deterministic-fixture",
                        }
                        for model in self.server.models
                    ],
                }
            )
        elif path.endswith("/api.json"):
            self._json(
                {
                    "fixture": {
                        "id": "fixture",
                        "name": "Deterministic fixture",
                        "type": "openai",
                        "npm": "@ai-sdk/openai-compatible",
                        "api": f"http://127.0.0.1:{self.server.server_port}/v1",
                        "env": ["FIXTURE_API_KEY"],
                        "models": {
                            model: {
                                "id": model,
                                "name": model,
                                "attachment": False,
                                "reasoning": False,
                                "tool_call": True,
                                "temperature": True,
                                "modalities": {"input": ["text"], "output": ["text"]},
                                "cost": {"input": 0, "output": 0},
                                "limit": {"context": 200000, "output": 32000},
                            }
                            for model in self.server.models
                        },
                    }
                }
            )
        elif path.endswith("/api-key"):
            self._json(
                {
                    "redacted_api_key": "fixture",
                    "name": "fixture",
                    "acls": ["api-key:model:*"],
                    "api_key_blocked": False,
                    "api_key_disabled": False,
                    "team_blocked": False,
                }
            )
        elif path in ("/", "/health"):
            self._json(
                {"fixture": True, "purpose": "CLI startup and tool overhead only"}
            )
        else:
            self._json({"error": {"message": "Unknown fixture route"}}, 404)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= MAX_BODY:
            raise ValueError(
                "Fixture request needs a Content-Length between 1 and 32 MiB"
            )
        data = self.rfile.read(length)
        encoding = self.headers.get("Content-Encoding", "identity")
        if encoding == "gzip":
            data = gzip.decompress(data)
        elif encoding == "deflate":
            data = zlib.decompress(data)
        elif encoding == "zstd":
            import zstandard

            data = zstandard.ZstdDecompressor().decompress(
                data, max_output_size=MAX_BODY
            )
        elif encoding != "identity":
            raise ValueError(f"Unsupported fixture request encoding: {encoding}")
        if len(data) > MAX_BODY:
            raise ValueError("Decoded fixture request exceeds 32 MiB")
        body = json.loads(data)
        if not isinstance(body, dict):
            raise TypeError("Expected a JSON object")
        return body

    def do_POST(self) -> None:
        """Timestamp request arrival before body decoding and emit one deterministic step."""
        received = time.monotonic_ns()
        record: dict[str, Any] = {
            "received_monotonic_ns": received,
            "received_unix_ns": time.time_ns(),
            "path": self.path.split("?", 1)[0],
            "synthetic_model": True,
        }
        with self.server.lock:
            self.server.active += 1
            record["active_requests"] = self.server.active
        try:
            body = self._body()
            path = record["path"]
            token_count = path.endswith(("/messages/count_tokens", ":countTokens"))
            protocol = (
                "anthropic"
                if path.endswith("/messages/count_tokens")
                else _protocol(path)
            )
            if protocol == "gemini":
                from fixture_gemini import normalize

                body = normalize(body, path)
            turn = locate(
                body, self.server.previous(str(body.get("previous_response_id", "")))
            )
            record.update(
                protocol=protocol,
                model=body.get("model"),
                tools=[tool["name"] for tool in declared(body)],
            )
            reason = "token_count" if token_count else auxiliary_reason(body, turn)
            record.update(request_shape(body))
            record["request_kind"] = "auxiliary" if reason else "workload"
            if reason:
                record["auxiliary_reason"] = reason
            if turn:
                key = (turn.marker, turn.phase)
                with self.server.lock:
                    first = key not in self.server.first
                    self.server.first.add(key)
                record.update(
                    correlation_id=turn.marker,
                    phase=turn.phase,
                    completed_steps=turn.completed,
                    first_provider_request=first,
                )
            if token_count:
                self._json(
                    {"totalTokens" if protocol == "gemini" else "input_tokens": 1000}
                )
                record["ok"] = True
                return
            response_turn = turn if reason in (None, "completion_review") else None
            whole, chunks = response(body, protocol, response_turn)
            if protocol == "responses":
                self.server.remember(whole["id"], turn)
            if body.get("stream"):
                self._stream(chunks)
            else:
                self._json(whole)
            record["ok"] = True
        except (ValueError, TypeError, KeyError, ImportError, zlib.error) as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            self._json(
                {"error": {"message": record["error"], "type": "fixture_error"}}, 400
            )
        except (BrokenPipeError, ConnectionResetError):
            record["client_disconnected"] = True
        finally:
            record["processing_seconds"] = (time.monotonic_ns() - received) / 1e9
            usage = resource.getrusage(resource.RUSAGE_SELF)
            record["fixture_cpu_seconds"] = usage.ru_utime + usage.ru_stime
            record["fixture_maxrss_kib"] = usage.ru_maxrss
            with self.server.lock:
                self.server.active -= 1
            self.server.write(record)


def main() -> None:
    """Start an explicitly synthetic provider on loopback and retain request timings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument(
        "--models",
        default="fixture-model,kimi-k2,claude-sonnet-4-5,gpt-5-codex,deepseek-chat",
    )
    args = parser.parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with Fixture(args.port, args.log, args.models.split(",")) as server:
        sys_message = {
            "url": f"http://127.0.0.1:{server.server_port}",
            "log": str(args.log),
            "synthetic_model": True,
        }
        server.write(
            {
                "kind": "fixture_started",
                **sys_message,
                "monotonic_ns": time.monotonic_ns(),
                "fixture_revision": "gemini-user-envelope-v4",
                "python": sys.version,
                "fixture_source_sha256": {
                    str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted(Path(__file__).parent.glob("fixture*.py"))
                },
            }
        )
        print(json.dumps(sys_message), flush=True)  # noqa: T201 -- server announces its local endpoint
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()


if __name__ == "__main__":
    main()

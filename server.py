"""Red Team Console — Ollama chat with files, web search, history, and memory."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

APP_DIR = Path(__file__).resolve().parent
FILES_DIR = APP_DIR / "files"
DATA_DIR = APP_DIR / "data"
CHATS_DIR = DATA_DIR / "chats"
MEMORY_FILE = DATA_DIR / "memory.json"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
MAX_TOOL_ROUNDS = 8
MAX_FILE_BYTES = 2_000_000
MAX_MEMORY_ITEMS = 200

FILES_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
CHATS_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="/static")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create or overwrite a file inside the local files/ workspace. "
                "Use relative paths like project/app.py. Use this to build projects."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path under files/, e.g. myapp/main.py",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file contents to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the files/ workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path under files/"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and folders currently in the files/ workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Optional subfolder under files/ to list",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the public internet for current information. "
                "Use when the user asks to search, look up, or research something online."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results (1-8)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": (
                "Save a lasting memory about the user, their environment, preferences, "
                "targets they are authorized to assess, or important facts. "
                "Use when the user says remember this, or when a durable fact should persist across chats."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Short clear memory to store",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget",
            "description": "Remove a memory by id or by matching text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Memory id to remove"},
                    "text": {"type": "string", "description": "Substring match to remove"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memory",
            "description": "List all lasting memories currently stored.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_memory() -> dict:
    if not MEMORY_FILE.exists():
        return {"items": []}
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "items" not in data:
            return {"items": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"items": []}


def save_memory(data: dict) -> None:
    MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def format_memory_block(data: dict | None = None) -> str:
    data = data or load_memory()
    items = data.get("items") or []
    if not items:
        return ""
    lines = ["\n\n## Persistent memory (across chats)"]
    for item in items:
        lines.append(f"- [{item.get('id', '?')}] {item.get('text', '')}")
    lines.append("Use remember/forget tools to update this list when appropriate.")
    return "\n".join(lines)


def tool_remember(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return json.dumps({"error": "Empty memory text"})
    data = load_memory()
    items = data.setdefault("items", [])
    # avoid exact duplicates
    for item in items:
        if item.get("text", "").strip().lower() == text.lower():
            return json.dumps({"ok": True, "id": item.get("id"), "duplicate": True})
    item = {"id": uuid.uuid4().hex[:10], "text": text, "created_at": utc_now()}
    items.append(item)
    if len(items) > MAX_MEMORY_ITEMS:
        data["items"] = items[-MAX_MEMORY_ITEMS:]
    save_memory(data)
    return json.dumps({"ok": True, "id": item["id"], "text": text})


def tool_forget(mem_id: str = "", text: str = "") -> str:
    data = load_memory()
    items = data.get("items") or []
    before = len(items)
    mem_id = (mem_id or "").strip()
    text = (text or "").strip().lower()
    kept = []
    for item in items:
        if mem_id and item.get("id") == mem_id:
            continue
        if text and text in (item.get("text") or "").lower():
            continue
        kept.append(item)
    data["items"] = kept
    save_memory(data)
    return json.dumps({"ok": True, "removed": before - len(kept), "remaining": len(kept)})


def tool_list_memory() -> str:
    data = load_memory()
    return json.dumps({"items": data.get("items") or [], "count": len(data.get("items") or [])})


def chat_path(chat_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", chat_id or "")
    if not safe:
        raise ValueError("Invalid chat id")
    return CHATS_DIR / f"{safe}.json"


def list_chats_meta() -> list[dict]:
    chats = []
    for path in CHATS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            chats.append(
                {
                    "id": data.get("id") or path.stem,
                    "title": data.get("title") or "Untitled",
                    "updated_at": data.get("updated_at") or "",
                    "message_count": len(data.get("messages") or []),
                }
            )
        except (json.JSONDecodeError, OSError):
            continue
    chats.sort(key=lambda c: c.get("updated_at") or "", reverse=True)
    return chats


def load_chat(chat_id: str) -> dict | None:
    path = chat_path(chat_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_chat(chat: dict) -> dict:
    chat_id = chat.get("id") or uuid.uuid4().hex
    chat["id"] = chat_id
    chat["updated_at"] = utc_now()
    if not chat.get("title"):
        chat["title"] = "New chat"
    chat_path(chat_id).write_text(json.dumps(chat, indent=2, ensure_ascii=False), encoding="utf-8")
    return chat


def title_from_messages(messages: list) -> str:
    for m in messages:
        if m.get("role") == "user" and (m.get("content") or "").strip():
            text = m["content"].strip().replace("\n", " ")
            return (text[:48] + "…") if len(text) > 48 else text
    return "New chat"


def safe_files_path(rel: str) -> Path:
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel or rel in (".", "..") or ".." in rel.split("/"):
        raise ValueError("Invalid path")
    target = (FILES_DIR / rel).resolve()
    if not str(target).startswith(str(FILES_DIR.resolve())):
        raise ValueError("Path escapes files/ workspace")
    return target


def tool_write_file(path: str, content: str) -> str:
    if content is None:
        content = ""
    data = content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        return json.dumps({"error": f"File too large (max {MAX_FILE_BYTES} bytes)"})
    target = safe_files_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return json.dumps(
        {
            "ok": True,
            "path": str(target.relative_to(FILES_DIR)).replace("\\", "/"),
            "bytes": len(data),
        }
    )


def tool_read_file(path: str) -> str:
    target = safe_files_path(path)
    if not target.is_file():
        return json.dumps({"error": "File not found"})
    if target.stat().st_size > MAX_FILE_BYTES:
        return json.dumps({"error": "File too large to read"})
    return json.dumps(
        {
            "path": str(target.relative_to(FILES_DIR)).replace("\\", "/"),
            "content": target.read_text(encoding="utf-8", errors="replace"),
        }
    )


def tool_list_files(path: str = "") -> str:
    base = FILES_DIR if not path else safe_files_path(path)
    if not base.exists():
        return json.dumps({"error": "Path not found", "entries": []})
    if base.is_file():
        return json.dumps({"entries": [str(base.relative_to(FILES_DIR)).replace("\\", "/")]})
    entries = []
    for root, dirs, files in os.walk(base):
        dirs.sort()
        files.sort()
        root_p = Path(root)
        for d in dirs:
            entries.append((root_p / d).relative_to(FILES_DIR).as_posix() + "/")
        for f in files:
            entries.append((root_p / f).relative_to(FILES_DIR).as_posix())
    return json.dumps({"entries": entries[:500], "count": len(entries)})


def tool_search_web(query: str, max_results: int = 5) -> str:
    max_results = max(1, min(int(max_results or 5), 8))
    query = (query or "").strip()
    if not query:
        return json.dumps({"error": "Empty query"})

    try:
        from duckduckgo_search import DDGS  # type: ignore

        with DDGS() as ddgs:
            rows = list(ddgs.text(query, max_results=max_results))
        results = [
            {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
            for r in rows
        ]
        return json.dumps({"query": query, "results": results})
    except Exception:
        pass

    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        r = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RedTeamConsole/1.0)"},
        )
        r.raise_for_status()
        html = r.text
        results = []
        for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</(?:a|td|div)',
            html,
            flags=re.I | re.S,
        ):
            href, title, snippet = m.group(1), m.group(2), m.group(3)
            title = re.sub(r"<[^>]+>", "", unescape(title)).strip()
            snippet = re.sub(r"<[^>]+>", "", unescape(snippet)).strip()
            if href.startswith("//"):
                href = "https:" + href
            results.append({"title": title, "url": href, "snippet": snippet})
            if len(results) >= max_results:
                break
        if not results:
            from urllib.parse import unquote

            for m in re.finditer(r'uddg=([^&"]+)', html):
                link = unquote(m.group(1))
                results.append({"title": link, "url": link, "snippet": ""})
                if len(results) >= max_results:
                    break
        return json.dumps({"query": query, "results": results})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"Search failed: {exc}", "results": []})


def run_tool(name: str, args: dict) -> str:
    try:
        if name == "write_file":
            return tool_write_file(args.get("path", ""), args.get("content", ""))
        if name == "read_file":
            return tool_read_file(args.get("path", ""))
        if name == "list_files":
            return tool_list_files(args.get("path") or "")
        if name == "search_web":
            return tool_search_web(args.get("query", ""), args.get("max_results", 5))
        if name == "remember":
            return tool_remember(args.get("text", ""))
        if name == "forget":
            return tool_forget(args.get("id", ""), args.get("text", ""))
        if name == "list_memory":
            return tool_list_memory()
        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


def parse_tool_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
    return {}


def inject_memory(messages: list) -> list:
    block = format_memory_block()
    if not block:
        return list(messages)
    msgs = [dict(m) for m in messages]
    if msgs and msgs[0].get("role") == "system":
        base = msgs[0].get("content") or ""
        # strip previous memory block if re-sent
        base = re.sub(r"\n\n## Persistent memory \(across chats\).*", "", base, flags=re.S)
        msgs[0]["content"] = base.rstrip() + block
    else:
        msgs.insert(0, {"role": "system", "content": "You are a helpful assistant." + block})
    return msgs


def ollama_chat(model: str, messages: list, stream: bool = False, tools=None) -> dict:
    body = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "tools": tools or TOOLS,
    }
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=600)
    r.raise_for_status()
    return r.json()


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.get("/")
def index():
    return send_from_directory(APP_DIR, "index.html")


@app.get("/api/health")
def health():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
        models = [m.get("name", "") for m in r.json().get("models", [])]
        return jsonify(
            {
                "ok": True,
                "ollama": True,
                "models": models,
                "default": DEFAULT_MODEL,
                "files_dir": "files",
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify(
            {
                "ok": False,
                "ollama": False,
                "error": str(exc),
                "default": DEFAULT_MODEL,
                "models": [],
            }
        ), 503


@app.get("/api/files")
def list_workspace_files():
    return jsonify(json.loads(tool_list_files("")))


@app.get("/api/memory")
def get_memory():
    return jsonify(load_memory())


@app.put("/api/memory")
def put_memory():
    payload = request.get_json(force=True, silent=True) or {}
    items = payload.get("items")
    if not isinstance(items, list):
        return jsonify({"error": "items must be a list"}), 400
    cleaned = []
    for item in items[:MAX_MEMORY_ITEMS]:
        if isinstance(item, str):
            text = item.strip()
            if text:
                cleaned.append({"id": uuid.uuid4().hex[:10], "text": text, "created_at": utc_now()})
        elif isinstance(item, dict) and (item.get("text") or "").strip():
            cleaned.append(
                {
                    "id": item.get("id") or uuid.uuid4().hex[:10],
                    "text": item["text"].strip(),
                    "created_at": item.get("created_at") or utc_now(),
                }
            )
    data = {"items": cleaned}
    save_memory(data)
    return jsonify(data)


@app.post("/api/memory")
def add_memory():
    payload = request.get_json(force=True, silent=True) or {}
    return jsonify(json.loads(tool_remember(payload.get("text", ""))))


@app.delete("/api/memory/<mem_id>")
def delete_memory(mem_id: str):
    return jsonify(json.loads(tool_forget(mem_id=mem_id)))


@app.get("/api/chats")
def api_list_chats():
    return jsonify({"chats": list_chats_meta()})


@app.post("/api/chats")
def api_create_chat():
    payload = request.get_json(force=True, silent=True) or {}
    chat = {
        "id": uuid.uuid4().hex,
        "title": payload.get("title") or "New chat",
        "messages": payload.get("messages") or [],
        "created_at": utc_now(),
    }
    return jsonify(write_chat(chat))


@app.get("/api/chats/<chat_id>")
def api_get_chat(chat_id: str):
    chat = load_chat(chat_id)
    if not chat:
        return jsonify({"error": "not found"}), 404
    return jsonify(chat)


@app.put("/api/chats/<chat_id>")
def api_save_chat(chat_id: str):
    payload = request.get_json(force=True, silent=True) or {}
    existing = load_chat(chat_id) or {"id": chat_id, "created_at": utc_now()}
    messages = payload.get("messages")
    if messages is not None:
        existing["messages"] = messages
    if payload.get("title"):
        existing["title"] = payload["title"]
    elif messages:
        existing["title"] = title_from_messages(messages)
    return jsonify(write_chat(existing))


@app.delete("/api/chats/<chat_id>")
def api_delete_chat(chat_id: str):
    path = chat_path(chat_id)
    if path.exists():
        path.unlink()
    return jsonify({"ok": True})


@app.post("/api/chat")
def chat():
    payload = request.get_json(force=True, silent=True) or {}
    model = payload.get("model") or DEFAULT_MODEL
    messages = payload.get("messages") or []
    if not messages:
        return jsonify({"error": "messages required"}), 400

    msgs = inject_memory(messages)

    def generate():
        nonlocal msgs
        try:
            for round_i in range(MAX_TOOL_ROUNDS):
                # refresh memory each round in case remember/forget ran
                if msgs and msgs[0].get("role") == "system":
                    msgs = inject_memory(
                        [{"role": "system", "content": re.sub(
                            r"\n\n## Persistent memory \(across chats\).*",
                            "",
                            msgs[0].get("content") or "",
                            flags=re.S,
                        )}]
                        + msgs[1:]
                    )
                yield sse({"type": "status", "text": f"Thinking (round {round_i + 1})…"})
                data = ollama_chat(model, msgs, stream=False, tools=TOOLS)
                message = data.get("message") or {}
                tool_calls = message.get("tool_calls") or []
                content = message.get("content") or ""

                if tool_calls:
                    msgs.append(
                        {
                            "role": "assistant",
                            "content": content,
                            "tool_calls": tool_calls,
                        }
                    )
                    for tc in tool_calls:
                        fn = tc.get("function") or {}
                        name = fn.get("name") or ""
                        args = parse_tool_args(fn.get("arguments"))
                        yield sse(
                            {
                                "type": "tool",
                                "name": name,
                                "args": {
                                    k: (v if k != "content" else f"<{len(str(v))} chars>")
                                    for k, v in args.items()
                                },
                            }
                        )
                        result = run_tool(name, args)
                        msgs.append({"role": "tool", "content": result})
                        if name == "write_file":
                            try:
                                info = json.loads(result)
                                if info.get("ok"):
                                    yield sse({"type": "file_written", "path": info.get("path")})
                            except json.JSONDecodeError:
                                pass
                        if name in ("remember", "forget"):
                            yield sse({"type": "memory_updated"})
                    continue

                if content:
                    step = 24
                    for i in range(0, len(content), step):
                        yield sse({"type": "token", "content": content[i : i + step]})
                else:
                    yield sse(
                        {
                            "type": "token",
                            "content": "(no response — try another Ollama model that supports tools)",
                        }
                    )
                yield sse({"type": "done"})
                return

            yield sse(
                {
                    "type": "token",
                    "content": "Stopped after too many tool rounds. Try a narrower request.",
                }
            )
            yield sse({"type": "done"})
        except requests.RequestException as exc:
            yield sse({"type": "error", "error": str(exc)})
            yield sse({"type": "done"})
        except Exception as exc:  # noqa: BLE001
            yield sse({"type": "error", "error": str(exc)})
            yield sse({"type": "done"})

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7860"))
    print(f"Open http://127.0.0.1:{port}")
    print(f"Default model: {DEFAULT_MODEL}")
    print(f"Workspace: {FILES_DIR}")
    print(f"Data: {DATA_DIR}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)

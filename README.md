# Red Team Console

Local **red**-themed chat UI for **Ollama**, built for **ethical red team / authorized security assessment**.

Features:

- Chat with any model installed in your local Ollama
- **Chat history** — multiple chats in the left sidebar (saved under `data/chats/`)
- **Memory** — lasting facts across chats (`data/memory.json`); model can remember/forget
- **Settings** panel for model + system prompt (kept off the main chat)
- **`files/` workspace** — the model can create/read project files
- **Web search** — the model can search the internet when asked

## Requirements

- Windows 10/11
- [Python 3.10+](https://www.python.org/downloads/)
- [Ollama](https://ollama.com)

## Quick start

1. Double-click **`setup.bat`**
2. Double-click **`start.bat`**

Open [http://127.0.0.1:7860](http://127.0.0.1:7860)

## Models

The Settings dropdown lists models already installed in **Ollama** on your machine.

Default: `qwen2.5-coder:7b` (tool-capable). Prefer a model that supports Ollama **tools**.

Optional:

```bat
ollama pull huihui_ai/qwen2.5-coder-abliterate:14b
```

## Tools

| Tool | Purpose |
|------|---------|
| `write_file` / `read_file` / `list_files` | Build projects under `files/` |
| `search_web` | Internet lookup when you ask |
| `remember` / `forget` / `list_memory` | Persistent memory across chats |

Example prompts:

- “Create a small Python scanner project in files/”
- “Search the web for recent CVE notes on …”

## Manual start

```bat
python -m pip install -r requirements.txt
python server.py
```

| Variable       | Default                  |
|----------------|--------------------------|
| `PORT`         | `7860`                   |
| `OLLAMA_URL`   | `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b`       |

## Layout

```
├── setup.bat / start.bat
├── server.py
├── index.html
├── static/
├── files/                 # model workspace
└── requirements.txt
```

## Ethics

For **authorized** testing only. Pair findings with remediation.

## License

MIT

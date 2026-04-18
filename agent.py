import json, os, subprocess, re, sys
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "https://api.z.ai/api/coding/paas/v4")
MODEL = os.getenv("MODEL", "glm-4.7")
API_KEY = os.getenv("API_KEY", "")

def _headers(k):
    return {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}

C_YOU = "\033[94m"
C_BOT = "\033[93m"
C_TOOL = "\033[90m"
C_RST = "\033[0m"

def _resolve(p):
    path = Path(p).expanduser()
    return path if path.is_absolute() else (Path.cwd() / path).resolve()

def read_file(path):
    p = _resolve(path)
    if not p.is_file():
        return f"Error: {path} not found"
    return p.read_text(encoding="utf-8", errors="replace")

def list_files(path):
    p = _resolve(path)
    if not p.is_dir():
        return f"Error: {path} is not a directory"
    return "\n".join(f"{'[D]' if i.is_dir() else '[F]'} {i.name}" for i in sorted(p.iterdir()))

def edit_file(path, old_str, new_str):
    p = _resolve(path)
    if old_str == "":
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_str, encoding="utf-8")
        return f"Created {path}"
    if not p.is_file():
        return f"Error: {path} not found"
    content = p.read_text(encoding="utf-8")
    if old_str not in content:
        return f"Error: old_str not found in {path}"
    p.write_text(content.replace(old_str, new_str, 1), encoding="utf-8")
    return f"Edited {path}"

def run_bash(command):
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, cwd=str(Path.cwd()))
        return (r.stdout or "") + (r.stderr or "") or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out (30s)"
    except Exception as e:
        return f"Error: {e}"

def search_files(pattern, path="."):
    results = []
    base = _resolve(path)
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex: {e}"
    for fp in base.rglob("*"):
        if fp.is_file():
            try:
                for i, line in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        results.append(f"{fp.relative_to(base)}:{i}: {line.strip()}")
                        if len(results) >= 50:
                            return "\n".join(results) + "\n... (truncated)"
            except Exception:
                pass
    return "\n".join(results) or "No matches found"

TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read the full contents of a file.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "list_files", "description": "List files and directories in a given path.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory path"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Edit or create a file. If old_str is empty, create the file with new_str. Otherwise replace first occurrence of old_str with new_str.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path"}, "old_str": {"type": "string", "description": "Text to find (empty = create file)"}, "new_str": {"type": "string", "description": "Replacement text or full file content"}}, "required": ["path", "old_str", "new_str"]}}},
    {"type": "function", "function": {"name": "run_bash", "description": "Execute a shell command and return stdout/stderr.", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Shell command to run"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "search_files", "description": "Search files for a regex pattern recursively.", "parameters": {"type": "object", "properties": {"pattern": {"type": "string", "description": "Regex pattern"}, "path": {"type": "string", "description": "Directory to search in", "default": "."}}, "required": ["pattern"]}}},
]

TOOL_MAP = {
    "read_file": read_file,
    "list_files": list_files,
    "edit_file": edit_file,
    "run_bash": run_bash,
    "search_files": search_files,
}

SYSTEM_PROMPT = (
    "You are a helpful coding assistant with access to tools for reading, editing, "
    "and searching files, and running shell commands. Use them to accomplish the user's tasks. "
    "Always read files before editing. Be concise."
)

def call_llm(messages):
    url = f"{BASE_URL}/chat/completions"
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": 4096,
    }
    resp = requests.post(url, headers=_headers(API_KEY), json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]

def run():
    if not API_KEY:
        print(f"Error: API key not set. Copy .env.example to .env and add your key.")
        sys.exit(1)
    print(f"{C_TOOL}pico-agent | model={MODEL}{C_RST}")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    while True:
        try:
            user_input = input(f"\n{C_YOU}You:{C_RST} ")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C_TOOL}Bye.{C_RST}")
            break
        if not user_input.strip():
            continue
        messages.append({"role": "user", "content": user_input})
        while True:
            try:
                reply = call_llm(messages)
            except Exception as e:
                print(f"{C_TOOL}API error: {e}{C_RST}")
                break
            messages.append(reply)
            tool_calls = reply.get("tool_calls")
            if not tool_calls:
                print(f"\n{C_BOT}Assistant:{C_RST} {reply.get('content', '')}")
                break
            for tc in tool_calls:
                fn = tc["function"]
                name = fn["name"]
                args = fn["arguments"] if isinstance(fn["arguments"], dict) else json.loads(fn["arguments"])
                print(f"  {C_TOOL}[tool] {name}({json.dumps(args)}){C_RST}")
                result = TOOL_MAP[name](**args)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)})

if __name__ == "__main__":
    run()

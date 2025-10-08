#!/usr/bin/env python3
# Ensure repo root is on sys.path so running this script from within lyrallm/scripts works
import os, sys
_here = os.path.abspath(os.path.dirname(__file__))
candidates = [
    os.path.abspath(os.path.join(_here, "..")),
    os.path.abspath(os.path.join(_here, "..", "..")),
]
for c in candidates:
    if os.path.isdir(os.path.join(c, "lyrallm")) and c not in sys.path:
        sys.path.insert(0, c)
        break

        #10/8
"""
Interactive chat CLI to call the endpoints exposed by main.py.

Behavior:
- Prefer in-process calls using FastAPI TestClient (no server needed).
- If that fails, fall back to HTTP requests to the host/port from config or defaults.

Usage:
  python Scripts/chat_cli.py

Type your message at the prompt, Ctrl-C or 'exit' to quit.
"""
import sys
import json
import time
from typing import List, Dict

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081


def try_inprocess_client():
    try:
        from fastapi.testclient import TestClient
        import main
        client = TestClient(main.app)
        # attempt a quick health call to ensure lifespan runs
        r = client.get("/api/chat/health")
        if r.status_code == 200:
            print("Using in-process TestClient (no separate server required).")
            return client, True
    except Exception:
        return None, False
    return None, False


def try_http_client():
    import requests
    # try to get host/port from main.config_manager if possible
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    try:
        import main
        try:
            server_cfg = main.config_manager.get_server_config()
            host = server_cfg.get('host', host)
            port = server_cfg.get('port', port)
        except Exception:
            pass
    except Exception:
        pass

    base = f"http://{host}:{port}"
    try:
        r = requests.get(f"{base}/api/chat/health", timeout=3)
        if r.status_code == 200:
            print(f"Using HTTP client to {base}")
            return requests, base
    except Exception:
        return None, None

    return None, None


def send_message_inprocess(client, model: str, messages: List[Dict]):
    payload = {"model": model, "messages": messages}
    r = client.post("/api/chat/completions", json=payload)
    return r


def send_message_http(requests_mod, base: str, model: str, messages: List[Dict]):
    payload = {"model": model, "messages": messages}
    r = requests_mod.post(f"{base}/api/chat/completions", json=payload, timeout=30)
    return r


def extract_text_from_response(r):
    try:
        data = r.json()
    except Exception:
        return r.text

    # try to extract assistant message
    try:
        choices = data.get('choices')
        if choices and len(choices) > 0:
            msg = choices[0].get('message')
            if isinstance(msg, dict):
                return msg.get('content')
            return str(msg)
    except Exception:
        pass

    # fallback: pretty-print JSON
    return json.dumps(data, ensure_ascii=False, indent=2)


def interactive_loop(client_mode, client_obj, base=None):
    print("開始互動式聊天。輸入 'exit' 或 Ctrl-C 結束。\n")
    model = None
    # try to get default model
    try:
        import main
        model = main.config_manager.get_default_model()
    except Exception:
        model = None

    if not model:
        model = input("請輸入模型名稱 (或直接按 Enter 使用預設): ") or None

    messages = []
    try:
        while True:
            user = input('You: ')
            if not user:
                continue
            if user.strip().lower() in ('exit', 'quit'):
                break

            messages.append({"role": "user", "content": user})

            if client_mode == 'inprocess':
                r = send_message_inprocess(client_obj, model, messages)
            else:
                r = send_message_http(client_obj, base, model, messages)

            print(f"HTTP {r.status_code}")
            text = extract_text_from_response(r)
            print(f"AI: {text}\n")

            # append assistant reply to history if possible
            try:
                # if JSON structure contains choices.message.content
                j = r.json()
                ans = None
                if isinstance(j, dict):
                    ch = j.get('choices')
                    if ch and len(ch) > 0:
                        msg = ch[0].get('message')
                        if isinstance(msg, dict):
                            ans = msg.get('content')
                if ans:
                    messages.append({"role": "assistant", "content": ans})
            except Exception:
                pass

    except KeyboardInterrupt:
        print('\nGoodbye')


def main():
    # Try in-process first
    client, ok = try_inprocess_client()
    if ok and client is not None:
        interactive_loop('inprocess', client)
        return

    # Fallback to HTTP
    requests_mod, base = try_http_client()
    if requests_mod and base:
        interactive_loop('http', requests_mod, base)
        return

    print("無法建立與 main.py 的連線。請確認 server 是否正在執行，或確保 fastapi 可用以使用 in-process 模式.")


if __name__ == '__main__':
    main()

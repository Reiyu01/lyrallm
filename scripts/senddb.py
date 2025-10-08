import socket, json, time

payload = {
    "request_id": f"smoke_py_{int(time.time())}",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "model_name": "gpt-test",
    "prompt_tokens": 5,
    "completion_tokens": 5,
    "total_tokens": 10,
    "cost_usd": 0.0005,
    "user_id": "smoke",
    "endpoint": "/api/chat/completions",
    "status": "success"
    ""
}

HOST = "elk.54ucl.com"
PORT = 50000
MSG = (json.dumps(payload) + "\n").encode("utf-8")
RETRIES = 3
TIMEOUT = 5

for attempt in range(1, RETRIES+1):
    try:
        with socket.create_connection((HOST, PORT), timeout=TIMEOUT) as s:
            s.sendall(MSG)
        print("Sent:", payload["request_id"])
        break
    except Exception as e:
        print(f"Attempt {attempt} failed: {e}")
        if attempt == RETRIES:
            raise
        time.sleep(1 * attempt)
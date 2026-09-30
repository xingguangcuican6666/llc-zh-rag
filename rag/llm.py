"""Thin client for the two local llama.cpp servers."""
import requests, time

BGE_URL  = "http://127.0.0.1:18080"
QWEN_URL = "http://127.0.0.1:8080"

def embed(texts, batch=64, retry=3, max_chars=300):
    """Return list of 512-d vectors (BGE-small-zh) for texts.
    BGE context is 512 tokens; truncate long inputs (same rule for index & query)."""
    texts = [(t or "")[:max_chars] for t in texts]
    out = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i+batch]
        for attempt in range(retry):
            try:
                r = requests.post(f"{BGE_URL}/v1/embeddings",
                                  json={"input": chunk}, timeout=120)
                r.raise_for_status()
                data = sorted(r.json()["data"], key=lambda d: d["index"])
                out.extend(d["embedding"] for d in data)
                break
            except Exception as e:
                if attempt == retry-1: raise
                time.sleep(1.5*(attempt+1))
    return out

def chat(messages, temperature=0.2, max_tokens=1024, stop=None, retry=3):
    """One Qwen chat completion -> assistant text.
    Retries transient (connection / 5xx) errors; a 4xx (e.g. prompt over the
    context window) is not retried — it will not fix itself."""
    body = {"messages": messages, "temperature": temperature,
            "max_tokens": max_tokens}
    if stop: body["stop"] = stop
    for attempt in range(retry):
        try:
            r = requests.post(f"{QWEN_URL}/v1/chat/completions",
                              json=body, timeout=600)
            if 400 <= r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()          # client error -> raise now, no retry
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except requests.exceptions.HTTPError as e:
            code = getattr(e.response, "status_code", None)
            if code and 400 <= code < 500 and code != 429:
                raise
            if attempt == retry-1: raise
            time.sleep(1.5*(attempt+1))
        except Exception:
            if attempt == retry-1: raise
            time.sleep(1.5*(attempt+1))

def health():
    ok = {}
    for name, url in (("bge", BGE_URL), ("qwen", QWEN_URL)):
        try:
            ok[name] = requests.get(f"{url}/health", timeout=3).ok
        except Exception:
            ok[name] = False
    return ok

if __name__ == "__main__":
    print("health:", health())
    v = embed(["관리자님, 안녕하세요"])
    print("embed dim:", len(v[0]))
    print("chat:", chat([{"role":"user","content":"用一个词回答：你好的英文？"}], max_tokens=16))

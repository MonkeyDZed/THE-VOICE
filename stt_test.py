import json, time, sys, uuid
from urllib.request import Request, urlopen

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:31415"
WAV = r"F:\THE-VOICE\Enregistrement1.wav"

key = None
for line in open(r"F:\THE-VOICE\.env", encoding="utf-8"):
    if line.startswith("FREEAPI_API_KEY="):
        key = line.strip().split("=", 1)[1]
        break
if not key:
    print("freeapi_api_key absent de .env")
    sys.exit(1)

model = sys.argv[1] if len(sys.argv) > 1 else "auto"

boundary = "----VoicePrompt" + uuid.uuid4().hex[:12]

def part_field(name, value):
    return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()

def part_file(name, filename, data, mime):
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
            f"filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n").encode()
    return head + data + b"\r\n"

with open(WAV, "rb") as f:
    audio = f.read()

t0 = time.perf_counter()
body = b""
body += part_field("model", model)
body += part_field("language", "fr")
body += part_field("response_format", "json")
body += part_file("file", "test.wav", audio, "audio/wav")
body += f"--{boundary}--\r\n".encode()

req = Request(f"{BASE}/v1/audio/transcriptions", data=body, method="POST")
req.add_header("Authorization", f"Bearer {key}")
req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
try:
    with urlopen(req, timeout=60) as r:
        status = r.status
        provider = r.headers.get("X-Provider")
        out = json.loads(r.read().decode("utf-8"))
    dt = time.perf_counter() - t0
    print(f"HTTP {status} | provider={provider} | {dt:.2f}s | size_sent={len(audio)}")
    print("TEXT:", out.get("text", "")[:400])
    if out.get("language") is not None:
        print("detected language:", out.get("language"))
    if out.get("duration") is not None:
        print("upstream duration:", out.get("duration"))
except Exception as e:
    dt = time.perf_counter() - t0
    print(f"FAILED after {dt:.2f}s: {type(e).__name__} {e}")
    if hasattr(e, "read"):
        print("BODY:", e.read().decode("utf-8", "replace")[:500])

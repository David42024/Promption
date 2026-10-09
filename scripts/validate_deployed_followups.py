"""Focused production reproductions and streaming checks after a moderate run."""
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx


OUT = Path(sys.argv[1])
TOKEN = os.environ["VALIDATION_CHAT_TOKEN"]
HEADERS = {"X-Chat-Service-Token": TOKEN}
CHAT = "https://chat-service-l31i.onrender.com/api/v1"
USER = {"id": "followup-" + uuid.uuid4().hex[:12], "name": "Validation", "email": "validation@example.com",
        "roles": ["customer"], "authenticated": True}
EVIDENCE = json.loads((OUT / "evidence.json").read_text(encoding="utf-8"))
STREAM_ONLY = os.environ.get("FOLLOWUPS_STREAM_ONLY") == "1"
CHECKS = json.loads((OUT / "followups.json").read_text(encoding="utf-8")) if STREAM_ONLY else []


def save():
    (OUT / "followups.json").write_text(json.dumps(CHECKS, ensure_ascii=False, indent=2).replace(TOKEN, "[REDACTED_CREDENTIAL]"), encoding="utf-8")


with httpx.Client(timeout=httpx.Timeout(130, connect=20)) as client:
    for case_id in (() if STREAM_ONLY else ("budget", "quoted_product")):
        case = next(item for item in EVIDENCE["cases"] if item["case_id"] == case_id)
        for index in range(2):
            start = time.perf_counter()
            try:
                response = client.post(CHAT + "/chat", headers=HEADERS, json={"text": case["prompt"], "user": USER,
                    "context": {"conversation_id": str(uuid.uuid4())}})
                data = response.json()
                CHECKS.append({"case": f"repeat_{case_id}_{index + 1}", "http": response.status_code,
                               "latency_ms": round((time.perf_counter() - start)*1000, 2), "data": data})
                print(json.dumps({"case": CHECKS[-1]["case"], "http": response.status_code,
                    "blocked": data.get("blocked"), "reason": data.get("reason"), "metrics": data.get("execution_metrics")}), flush=True)
            except Exception as exc:
                CHECKS.append({"case": f"repeat_{case_id}_{index + 1}", "error_type": type(exc).__name__})
            save()
            time.sleep(2)
    for cancel in ((True,) if STREAM_ONLY else (False, True)):
        conv = str(uuid.uuid4())
        prompt = "Explica brevemente las características de una laptop para estudiar." if not cancel else "Busco una laptop para estudiar con presupuesto moderado. Dame tres recomendaciones de características."
        frames, cancellation = [], None
        start = time.perf_counter()
        check = {"case": "stream_cancel_generation" if cancel else "stream_success"}
        try:
            with client.stream("POST", CHAT + "/chat/stream", headers=HEADERS,
                    json={"text": prompt, "user": USER, "context": {"conversation_id": conv}}) as stream:
                check["http"] = stream.status_code
                for line in stream.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    frame = json.loads(line[6:])
                    frames.append(frame)
                    if cancel and cancellation is None and "Generando respuesta" in frame.get("stage", ""):
                        time.sleep(0.5)
                        response = client.post(CHAT + "/chat/cancel", headers=HEADERS, json={"conversation_id": conv, "user": USER})
                        cancellation = {"http": response.status_code, "data": response.json()}
                    if frame.get("type") in ("result", "error"):
                        break
        except Exception as exc:
            check["error_type"] = type(exc).__name__
        check.update({"frames": frames, "cancel": cancellation,
                      "latency_ms": round((time.perf_counter()-start)*1000, 2)})
        CHECKS.append(check)
        save()
        print(json.dumps({"case": check["case"], "http": check.get("http"), "events": [frame.get("type") for frame in frames],
            "terminal": {k: frames[-1].get(k) for k in ("type", "code", "status")} if frames else None,
            "cancel": cancellation}), flush=True)

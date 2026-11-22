import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import numpy as np

from app import search

MODEL = os.environ["LLM_MODEL"]
INPUT_PRICE = float(os.environ.get("INPUT_PRICE_PER_MTOK", "3.00"))
OUTPUT_PRICE = float(os.environ.get("OUTPUT_PRICE_PER_MTOK", "15.00"))
LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "requests.jsonl"

client = anthropic.Anthropic(max_retries=3, timeout=30.0)

SYSTEM = (
    "You are a study assistant. Answer the question using ONLY the notes provided. "
    "If the notes don't contain the answer, say \"That's not in my notes.\" "
    "Cite the note numbers you used, like [2]. Keep answers under 150 words."
)

BLOCKED_MESSAGE = "Sorry, I can't help with that request."
UNAVAILABLE_MESSAGE = "I'm temporarily unable to answer. Please try again in a moment."
UNSAFE_MESSAGE = "That response was blocked by a safety check."

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior)\s+instructions",
    r"(reveal|show|print)\s+(your\s+)?system\s+prompt",
    r"you\s+are\s+now\s+",
]

PII_PATTERNS = {
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    "email": r"\b[\w.%+-]+@[\w.-]+\.[a-zA-Z]{2,}\b",
}

BANNED_OUTPUT_PATTERNS = [
    r"(?i)(drop|delete|truncate)\s+table",
    r"(?i)rm\s+-rf\s+/",
]


def check_input(text):
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "possible prompt injection", text, []

    pii_found = []
    cleaned = text
    for pii_type, pattern in PII_PATTERNS.items():
        if re.search(pattern, cleaned):
            pii_found.append(pii_type)
            cleaned = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", cleaned)
    return None, cleaned, pii_found


def check_output(text):
    return not any(re.search(pattern, text) for pattern in BANNED_OUTPUT_PATTERNS)


class SemanticCache:
    def __init__(self, threshold=0.92):
        self.threshold = threshold
        self.vectors = []
        self.answers = []

    def get(self, question):
        if not self.vectors:
            return None
        scores = np.array(self.vectors) @ search.embed(question)
        best = int(np.argmax(scores))
        if scores[best] >= self.threshold:
            return self.answers[best], float(scores[best])
        return None

    def put(self, question, answer):
        self.vectors.append(search.embed(question))
        self.answers.append(answer)


class StudyAssistant:
    def __init__(self, use_cache=True, cache_threshold=0.92):
        self.use_cache = use_cache
        self.cache = SemanticCache(cache_threshold)
        self.logs = []

    def ask(self, question):
        start = time.time()
        log = self._new_log(question)
        answer, cleaned, prompt = self._prepare(question, log)
        if answer is not None:
            return self._finish(log, start, answer)

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=500,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as e:
            log["error"] = f"LLM failed: {type(e).__name__}"
            return self._finish(log, start, UNAVAILABLE_MESSAGE)

        answer = response.content[0].text
        self._record_usage(log, response.usage)

        if not check_output(answer):
            log["blocked"] = "unsafe output"
            return self._finish(log, start, UNSAFE_MESSAGE)

        self._cache_put(cleaned, answer, log)
        return self._finish(log, start, answer)

    def ask_stream(self, question):
        start = time.time()
        log = self._new_log(question)
        log["streamed"] = True
        answer, cleaned, prompt = self._prepare(question, log)
        if answer is not None:
            self._finish(log, start, answer)
            yield answer
            return

        pieces = []
        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=500,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    pieces.append(text)
                    yield text
                final = stream.get_final_message()
        except anthropic.APIError as e:
            log["error"] = f"LLM failed: {type(e).__name__}"
            self._finish(log, start, UNAVAILABLE_MESSAGE)
            yield "\n" + UNAVAILABLE_MESSAGE
            return

        answer = "".join(pieces)
        self._record_usage(log, final.usage)

        if check_output(answer):
            self._cache_put(cleaned, answer, log)
        else:
            log["blocked"] = "unsafe output (already streamed)"
        self._finish(log, start, answer)

    def stats(self):
        if not self.logs:
            return {"requests": 0}
        latencies = [entry["latency_ms"] for entry in self.logs]
        n = len(self.logs)
        return {
            "requests": n,
            "p50_latency_ms": round(float(np.percentile(latencies, 50))),
            "p99_latency_ms": round(float(np.percentile(latencies, 99))),
            "cache_hit_rate": round(sum(entry["cache_hit"] for entry in self.logs) / n, 2),
            "blocked": sum(1 for entry in self.logs if entry["blocked"]),
            "errors": sum(1 for entry in self.logs if entry["error"]),
            "total_cost_usd": round(sum(entry["cost_usd"] for entry in self.logs), 6),
        }

    def _new_log(self, question):
        return {
            "request_id": uuid.uuid4().hex[:8],
            "time": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "blocked": None,
            "pii": [],
            "cache_hit": False,
            "notes_used": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "error": None,
        }

    def _prepare(self, question, log):
        blocked, cleaned, pii = check_input(question)
        log["question"] = cleaned
        log["pii"] = pii
        if blocked:
            log["blocked"] = blocked
            return BLOCKED_MESSAGE, None, None

        if self.use_cache:
            try:
                hit = self.cache.get(cleaned)
            except Exception as e:
                hit = None
                log["error"] = f"cache failed: {e}"
            if hit:
                answer, similarity = hit
                log["cache_hit"] = True
                log["cache_similarity"] = round(similarity, 3)
                return answer, None, None

        try:
            results = search.search(cleaned, 3)
        except Exception as e:
            results = []
            log["error"] = f"search failed: {e}"
        log["notes_used"] = len(results)

        notes = "\n".join(f"[{i}] {chunk}" for i, (score, chunk) in enumerate(results, start=1))
        prompt = f"<notes>\n{notes}\n</notes>\n\nQuestion: {cleaned}"
        return None, cleaned, prompt

    def _record_usage(self, log, usage):
        log["input_tokens"] = usage.input_tokens
        log["output_tokens"] = usage.output_tokens
        log["cost_usd"] = round(
            usage.input_tokens / 1_000_000 * INPUT_PRICE
            + usage.output_tokens / 1_000_000 * OUTPUT_PRICE, 6)

    def _cache_put(self, question, answer, log):
        if not self.use_cache:
            return
        try:
            self.cache.put(question, answer)
        except Exception as e:
            log["error"] = f"cache write failed: {e}"

    def _finish(self, log, start, answer):
        log["latency_ms"] = round((time.time() - start) * 1000)
        self.logs.append(log)
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(log) + "\n")
        return {"answer": answer, **log}

import ipaddress
import json
import os
import socket
from urllib.parse import urlsplit

import httpx

from onyx.meetings.models import Analysis
from onyx.meetings.models import Segment
from onyx.meetings.models import Topic
from onyx.prompts.meetings import SYSTEM_PROMPT


def local_ollama_url() -> str:
    url = urlsplit(os.environ.get("MEETINGS_OLLAMA_URL", "http://127.0.0.1:11434"))
    if (
        url.scheme != "http"
        or not url.hostname
        or url.username
        or url.password
        or url.path not in ("", "/")
        or url.query
        or url.fragment
    ):
        raise ValueError("Ollama must be a local HTTP origin")
    addresses = {
        entry[4][0]
        for entry in socket.getaddrinfo(
            url.hostname, url.port or 11434, type=socket.SOCK_STREAM
        )
    }
    allowed = [
        ipaddress.ip_network(net)
        for net in (
            "127.0.0.0/8",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "::1/128",
            "fc00::/7",
        )
    ]
    if not addresses or any(
        not any(ipaddress.ip_address(address) in net for net in allowed)
        for address in addresses
    ):
        raise ValueError("Public Ollama endpoints are forbidden")
    address = sorted(addresses)[0]
    # Pin the validated address: no second DNS lookup or redirect/proxy escape.
    host = f"[{address}]" if ":" in address else address
    return f"http://{host}:{url.port or 11434}"


def ask_ollama(payload: dict) -> Analysis:
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > 20000:
        raise ValueError("Local context budget exceeded; shorten agenda or summaries")
    model = os.environ["MEETINGS_OLLAMA_MODEL"]
    if "cloud" in model.lower() or "/" in model or "://" in model:
        raise ValueError("Only installed local Ollama models are allowed")
    with httpx.Client(
        base_url=local_ollama_url(),
        trust_env=False,
        follow_redirects=False,
        timeout=int(os.environ.get("MEETINGS_OLLAMA_TIMEOUT", "600")),
    ) as client:
        metadata = client.post("/api/show", json={"model": model})
        metadata.raise_for_status()
        if metadata.json().get("remote_host") or metadata.json().get("remote_model"):
            raise ValueError("Remote Ollama model aliases are forbidden")
        response = client.post(
            "/api/chat",
            json={
                "model": model,
                "stream": False,
                "format": Analysis.model_json_schema(),
                "keep_alive": os.environ.get("MEETINGS_OLLAMA_KEEP_ALIVE", "0"),
                "options": {"temperature": 0, "num_ctx": 32768, "num_predict": 8192},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": serialized,
                    },
                ],
            },
        )
        response.raise_for_status()
        return Analysis.model_validate_json(response.json()["message"]["content"])


def timeline(
    topics: list[Topic], segments: list[Segment], duration: float, agenda: str
) -> dict:
    assigned: dict[int, str] = {}
    ranges: list[dict] = []
    for topic in topics:
        category = topic.category
        if not agenda.strip() and category in ("agenda", "off_topic"):
            category = "unknown"
        intervals = []
        for index in topic.segment_ids:
            if index < 0 or index >= len(segments) or index in assigned:
                raise ValueError(
                    "Analysis contains invalid or duplicate segment references"
                )
            assigned[index] = category
            segment = segments[index]
            intervals.append({"start": segment.start, "end": segment.end})
        ranges.append({**topic.model_dump(), "category": category, "ranges": intervals})
    # Sweep all endpoints to avoid double-counting overlapping speech. Conflicting
    # categories and silence stay unknown rather than inventing agenda coverage.
    events: dict[float, list[tuple[str, int]]] = {0.0: [], duration: []}
    for index, segment in enumerate(segments):
        start, end = max(0, segment.start), min(duration, segment.end)
        if end <= start:
            continue
        category = assigned.get(index, "unknown")
        events.setdefault(start, []).append((category, 1))
        events.setdefault(end, []).append((category, -1))
    seconds = dict.fromkeys(("agenda", "off_topic", "repeated", "unknown"), 0.0)
    active: dict[str, int] = {}
    previous = 0.0
    for point in sorted(events):
        categories = [key for key, count in active.items() if count > 0]
        category = categories[0] if len(categories) == 1 else "unknown"
        seconds[category] += point - previous
        for key, delta in events[point]:
            active[key] = active.get(key, 0) + delta
        previous = point
    return {
        "topics": ranges,
        "seconds": seconds,
        "percent": {
            key: round(value / duration * 100, 2) if duration else 0
            for key, value in seconds.items()
        },
        "agenda_provided": bool(agenda.strip()),
        "estimated": True,
    }


def analyze(segments: list[Segment], duration: float, agenda: str) -> dict:
    if not segments:
        raise ValueError("No speech found to analyze")
    chunks: list[list[dict]] = [[]]
    size = 0
    for index, segment in enumerate(segments):
        item = {"id": index, **segment.model_dump()}
        length = len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
        if length > 12000:
            raise ValueError("Transcript segment exceeds local context budget")
        if size + length > 12000:
            chunks.append([])
            size = 0
        chunks[-1].append(item)
        size += length
    partials: list[Analysis] = []
    topics: list[Topic] = []
    for chunk in chunks:
        partial = ask_ollama({"agenda": agenda, "segments": chunk})
        valid_ids = {item["id"] for item in chunk}
        if any(
            index not in valid_ids
            for topic in partial.topics
            for index in topic.segment_ids
        ):
            raise ValueError("Analysis cites a segment outside its chunk")
        topics.extend(partial.topics)
        partials.append(partial)
    metrics = timeline(topics, segments, duration, agenda)
    # Hierarchical bounded reduction prevents silent truncation of long meetings.
    while len(partials) > 1:
        merged: list[Analysis] = []
        for index in range(0, len(partials), 2):
            pair = partials[index : index + 2]
            data = [part.model_dump(exclude={"topics"}) for part in pair]
            if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > 16000:
                raise ValueError("Summaries exceed local context budget")
            merged.append(ask_ollama({"agenda": agenda, "merge_parts": data}))
        partials = merged
    return {
        **partials[0].model_dump(exclude={"topics"}),
        **metrics,
        "model": os.environ["MEETINGS_OLLAMA_MODEL"],
        "duration": duration,
    }

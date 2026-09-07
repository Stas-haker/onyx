import socket
from unittest.mock import patch

import httpx
import pytest

from onyx.meetings.analysis import ask_ollama
from onyx.meetings.analysis import local_ollama_url
from onyx.meetings.analysis import timeline
from onyx.meetings.config import enabled
from onyx.meetings.config import storage_path
from onyx.meetings.models import Segment
from onyx.meetings.models import Topic


def topic(category: str, ids: list[int]) -> Topic:
    return Topic.model_validate(
        {
            "title": "topic",
            "category": category,
            "segment_ids": ids,
            "explanation": "evidence",
        }
    )


def test_overlap_and_gaps_never_double_count() -> None:
    segments = [Segment(start=0, end=6, text="a"), Segment(start=4, end=8, text="b")]
    result = timeline(
        [topic("agenda", [0]), topic("off_topic", [1])], segments, 10, "agenda"
    )
    assert result["seconds"] == {
        "agenda": 4,
        "off_topic": 2,
        "repeated": 0,
        "unknown": 4,
    }
    assert sum(result["percent"].values()) == 100


def test_missing_agenda_does_not_invent_compliance() -> None:
    result = timeline(
        [topic("agenda", [0])], [Segment(start=0, end=5, text="a")], 5, ""
    )
    assert result["seconds"]["unknown"] == 5
    assert result["agenda_provided"] is False


@pytest.mark.parametrize("ids", [[-1], [1], [0, 0]])
def test_invalid_references_fail(ids: list[int]) -> None:
    with pytest.raises(ValueError):
        timeline(
            [topic("agenda", ids)], [Segment(start=0, end=1, text="a")], 1, "agenda"
        )


@pytest.mark.parametrize(
    "address", ["8.8.8.8", "169.254.169.254", "0.0.0.0", "2606:4700:4700::1111"]
)
def test_external_and_metadata_hosts_rejected(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    monkeypatch.setenv("MEETINGS_OLLAMA_URL", "http://ollama:11434")
    with patch.object(
        socket, "getaddrinfo", return_value=[(0, 0, 0, "", (address, 11434))]
    ):
        with pytest.raises(ValueError):
            local_ollama_url()


def test_private_host_is_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETINGS_OLLAMA_URL", "http://ollama:11434")
    with patch.object(
        socket, "getaddrinfo", return_value=[(0, 0, 0, "", ("192.168.1.2", 11434))]
    ):
        assert local_ollama_url() == "http://192.168.1.2:11434"


def test_remote_alias_rejected_before_sending_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEETINGS_OLLAMA_MODEL", "innocent-alias")
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"remote_host": "https://ollama.com"})

    client = httpx.Client(
        transport=httpx.MockTransport(respond), base_url="http://127.0.0.1:11434"
    )
    with patch("onyx.meetings.analysis.httpx.Client", return_value=client):
        with pytest.raises(ValueError, match="aliases"):
            ask_ollama({"transcript": "sensitive"})
    assert calls == ["/api/show"]


def test_feature_flag_and_path_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEETINGS_ENABLED", raising=False)
    assert enabled() is False
    monkeypatch.setenv("MEETINGS_ENABLED", "true")
    assert enabled() is True
    with pytest.raises(ValueError):
        storage_path("../../outside")

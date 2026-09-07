"""One isolated, timeout-bounded stage. Started only by the meeting worker."""

import json
import os
import sys
from pathlib import Path


def main() -> None:
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "PYANNOTE_METRICS_ENABLED": "0",
        }
    )
    directory = Path(sys.argv[1])
    stage = sys.argv[2]
    from onyx.meetings.models import MeetingSnapshot

    snapshot = MeetingSnapshot.model_validate_json(
        (directory / "input.json").read_text(encoding="utf-8")
    )
    if stage in ("transcribe", "diarize"):
        # Model libraries cannot reach a network, even if a local config refers
        # to a missing remote model. FFmpeg separately limits allowed protocols.
        def deny_network(event: str, args: tuple[object, ...]) -> None:
            if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto"):
                raise RuntimeError("Network disabled for audio processing")

        sys.addaudithook(deny_network)
        from onyx.meetings.media import diarize
        from onyx.meetings.media import transcribe

        result = (
            transcribe(directory)
            if stage == "transcribe"
            else diarize(directory, snapshot.segments)
        )
    elif stage == "analyze":
        from onyx.meetings.analysis import analyze

        result = {
            "analysis": analyze(
                snapshot.segments, snapshot.duration or 0, snapshot.agenda
            )
        }
    else:
        raise ValueError("Invalid stage")
    temporary = directory / "result.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(directory / "result.json")


if __name__ == "__main__":
    main()

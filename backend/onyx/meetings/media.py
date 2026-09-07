import os
import subprocess
import wave
from pathlib import Path

from onyx.meetings.models import Segment


def normalize(directory: Path) -> float:
    max_seconds = int(os.environ.get("MEETINGS_MAX_SECONDS", "14400"))
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            "mp3,wav,mov,matroska,webm,ogg,flac,avi,aac,asf,amr,aiff,au",
            "-i",
            str(directory / "source"),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-t",
            str(max_seconds + 1),
            str(directory / "audio.wav"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=int(os.environ.get("MEETINGS_FFMPEG_TIMEOUT", "1800")),
    )
    with wave.open(str(directory / "audio.wav")) as audio:
        duration = audio.getnframes() / audio.getframerate()
    if duration <= 0 or duration > max_seconds:
        raise ValueError("Empty audio or recording exceeds duration limit")
    return duration


def transcribe(directory: Path) -> dict:
    from faster_whisper import WhisperModel

    model_path = Path(os.environ["MEETINGS_WHISPER_MODEL_PATH"])
    if not (model_path / "model.bin").is_file():
        raise ValueError("Local Whisper model is missing")
    duration = normalize(directory)
    model = WhisperModel(
        str(model_path),
        device="cuda",
        device_index=0,
        compute_type=os.environ.get("MEETINGS_COMPUTE_TYPE", "float16"),
        local_files_only=True,
    )
    segments, _ = model.transcribe(
        str(directory / "audio.wav"),
        vad_filter=True,
        word_timestamps=True,
        language=os.environ.get("MEETINGS_LANGUAGE") or None,
    )
    # Word boundaries reduce incorrect speaker assignment when turns change inside
    # a Whisper sentence. The UI can search and export every timestamped word.
    result: list[dict] = []
    for segment in segments:
        for word in segment.words or []:
            result.append(
                Segment(start=word.start, end=word.end, text=word.word).model_dump()
            )
        if not segment.words:
            result.append(
                Segment(
                    start=segment.start, end=segment.end, text=segment.text
                ).model_dump()
            )
    return {"duration": duration, "segments": result}


def diarize(directory: Path, segments: list[Segment]) -> dict:
    import numpy as np
    import torch
    from pyannote.audio import Pipeline

    model_path = Path(os.environ["MEETINGS_DIARIZATION_MODEL_PATH"])
    if not model_path.is_dir():
        raise ValueError("Local diarization model is missing")
    pipeline = Pipeline.from_pretrained(str(model_path))
    pipeline.to(torch.device("cuda:0"))
    with wave.open(str(directory / "audio.wav")) as audio:
        waveform = torch.from_numpy(
            np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(
                "float32"
            )
            / 32768
        ).unsqueeze(0)
    output = pipeline({"waveform": waveform, "sample_rate": 16000})
    turns = [
        (turn.start, turn.end, speaker)
        for turn, speaker in output.exclusive_speaker_diarization
    ]
    result: list[dict] = []
    cursor = 0
    for segment in segments:
        while cursor < len(turns) and turns[cursor][1] <= segment.start:
            cursor += 1
        overlaps: dict[str, float] = {}
        for start, end, speaker in turns[cursor:]:
            if start >= segment.end:
                break
            overlap = max(0, min(end, segment.end) - max(start, segment.start))
            overlaps[speaker] = overlaps.get(speaker, 0) + overlap
        speaker = (
            max(overlaps, key=lambda name: overlaps[name]) if overlaps else "UNKNOWN"
        )
        # Merge adjacent words for readable UI and smaller local LLM context.
        if (
            result
            and result[-1]["speaker"] == speaker
            and segment.start - result[-1]["end"] < 1
            and segment.end - result[-1]["start"] < 20
        ):
            result[-1]["end"] = segment.end
            result[-1]["text"] += segment.text
        else:
            result.append(segment.model_copy(update={"speaker": speaker}).model_dump())
    return {"segments": result}

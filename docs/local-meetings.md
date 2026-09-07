# MIRATORG local meetings

Target host: Windows 11 Pro, Threadripper PRO 7955WX, 128 GB ECC RAM,
**four RTX 3090 cards, each with 24 GB VRAM**. Run Linux containers under WSL2.

## Integration

The module extends Onyx: `/app/transcription`, FastAPI `/meetings`, existing
`BASIC_ACCESS` permission, owner-scoped records, tenant-aware PostgreSQL sessions,
Alembic and the existing Redis/Celery broker. No separate identity system.
The API and workers share a local filesystem volume. Redis messages contain IDs,
tenant and stage only. Transcripts and analysis remain in PostgreSQL.

`MEETINGS_ENABLED=false` by default. Do not enable until workers and local model
files are installed. The feature is delivered as stacked PRs: API/storage,
processing, then UI/deployment/validation. No direct changes to main.

Pipeline: upload → FFmpeg mono 16 kHz PCM → faster-whisper with timestamps →
local pyannote diarization → local Ollama structured analysis. Each stage has its
own queue. GPU0 and GPU1 run independent transcription workers; GPU2 diarization;
GPU3 Ollama. GPU IDs are configurable; 4×24 GB is not a unified 96 GB allocation.

Analysis is an estimate, not a personnel performance measurement. Categories are
exclusive, durations are computed from timestamp unions, and missing coverage is
reported as unknown. With no supplied agenda, agenda compliance is unknown.
Speaker labels are anonymous and may be inaccurate, especially during overlap.

## Future sources

Upload is the only implemented source. Media URL adapters and meeting capture
adapters must produce the same local source file before entering this pipeline.
Do not let FFmpeg open remote URLs in the upload path. Meeting capture requires
explicit participant notice/consent and platform-supported access; bypassing
Teams, Zoom, Telemost, TrueConf or WebRTC protections is outside the design.

## Validation gates

Before production: apply migration against a disposable PostgreSQL database,
verify owner/tenant isolation, process Russian audio/video on all configured
GPU pools, test queue/worker failure recovery, and run with outbound access
blocked. Verify browser telemetry and Ollama cloud features are disabled.
Source inspection and static checks alone do not establish these runtime gates.

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

## Install and run (WSL2/Linux containers)

1. Check out the final `feature/local-meeting-transcription` branch. Install
   Docker Desktop with WSL2 GPU support and verify that containers see all four
   cards. The implementation environment did not have Docker or `nvidia-smi`.
2. Stage model files before disconnecting internet: put a complete converted
   faster-whisper model (including `model.bin`) into `models/whisper`, and a full
   pyannote Community-1 offline checkout including actual LFS weights into
   `models/diarization`. Accept pyannote's model conditions yourself before
   downloading. No token is required or sent by inference workers.
3. Ensure an appropriate model is installed in the existing Ollama instance.
   Use its exact local model name in `MEETINGS_OLLAMA_MODEL`; the example is not
   proof that this tag is installed on your machine. Set `OLLAMA_NO_CLOUD=1`
   on that Ollama service and restart it. Restrict its outbound traffic. A local
   endpoint alone does not guarantee that a daemon cannot forward to a cloud.
4. Copy the meeting env values from `deployment/meetings/env.example` into the
   Onyx deployment `.env`, keeping your existing DB/Redis credentials. Set an
   absolute WSL directory for `MEETINGS_MODELS_DIR`. Never commit `.env` or
   credentials. The frontend is built without PostHog/Sentry when meetings are
   enabled. Use local authentication and local providers for the rest of Onyx.

From the repository root, build while package access is available:

```sh
docker build -t onyx-local-backend:meetings backend
docker build -t onyx-local-meetings:meetings -f deployment/meetings/Dockerfile .
cd deployment/docker_compose
docker compose -f docker-compose.yml -f docker-compose.meetings.yml build web_server
docker compose -f docker-compose.yml -f docker-compose.meetings.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.meetings.yml up -d
```

Download the other base Onyx service images and its local embedding/tokenizer
models before offline startup as well. The API applies `alembic upgrade head`
using the existing startup command; first test this against a disposable database.
The overlay uses an internal Docker network, disables backend telemetry and
initializes a shared local volume for uid 1001. Verify the existing host Ollama
is reachable from this network; if necessary use its explicit private LAN IP
instead of `host.docker.internal`. Never expose Ollama directly to the internet.
Keep browser outbound traffic restricted too; the rest of Onyx contains external
integrations which this module does not remove.

Open Onyx and select **Транскрибация**. Supply a short agenda, upload a file, wait
for the stage status to finish, then inspect speaker/timestamp accuracy and the
estimated analysis. Initial limits are 2 GiB upload and 4 hours per recording,
with a 6-hour deadline per stage. Larger files fail explicitly, not silently
truncate. Supported containers are a bounded FFmpeg allowlist, not every possible
format. Remote playlists and media URLs are deliberately excluded.

## GPU configuration and coexistence with Ollama

| Host GPU | Initial workload | Setting |
| --- | --- | --- |
| 0 | Transcription worker 0 | `MEETINGS_TRANSCRIBE_GPU_0` |
| 1 | Transcription worker 1 | `MEETINGS_TRANSCRIBE_GPU_1` |
| 2 | Diarization | `MEETINGS_DIARIZE_GPU` |
| 3 | Existing Ollama service | `CUDA_VISIBLE_DEVICES=3` on Ollama |

Docker exposes one chosen physical device per audio worker, then
`CUDA_VISIBLE_DEVICES=0` selects that container's single visible device. The
analysis queue has no CUDA device; Ollama owns its own GPU allocation.

If Ollama already uses multiple cards, leave it in place and map workers to
explicitly available cards through the settings above. Start only one ASR worker
if required (`docker compose ... stop meeting_transcribe_1`). Do not map active
ASR and diarization workers to the same card without measuring available VRAM.
When no card is free, stop audio workers and resume them after Ollama releases
memory. This MVP offers configurable allocation, **not automatic GPU eviction or
dynamic scheduling across the independently running Ollama process**. Stages
release their model memory on subprocess exit; Ollama analysis requests use
`keep_alive=0`. A 70B model may require several cards and does not fit GPU3 alone.

## Operational limits and checks

Queue messages expire after 24 hours. Failure retries restart preprocessing;
completed meetings can rerun analysis. Worker crashes or expired messages may
leave a status pending; after 25 hours the owner can retry. There is no automatic
recovery scheduler yet. Uploads and normalized audio are retained locally; storage
retention/cleanup is an administrator responsibility in this MVP, including files
orphaned by user deletion. Back up the PostgreSQL database and file volume together.

Run the isolated tests with the repository environment activated:

```sh
PYTHONPATH=backend pytest --confcutdir=backend/tests/unit/meetings backend/tests/unit/meetings
```

Run `backend/tests/integration/tests/meetings` only against a disposable local
Onyx deployment, with `MEETINGS_TEST_URL=http://localhost:3000/api` and the
normal Onyx integration fixtures. The tests use real uploads and owner checks.
They do not constitute multi-tenant isolation or actual GPU-inference validation.

Implementation checks (2026-09-08): 12 isolated tests passed; changed Python files
parsed successfully; the migration rendered valid PostgreSQL SQL offline; Compose
YAML and GPU/volume declarations passed static checks; frontend TypeScript and
Prettier checks passed. Frontend checking required resolving existing transitive
imports in the local dependency environment, without changing dependency manifests.
Docker image builds, actual migrations, GPU inference and browser end-to-end tests
remain unverified. Keep the PRs in draft until these deployment gates pass.

Primary implementation references:
[faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[Community-1 offline model](https://huggingface.co/pyannote/speaker-diarization-community-1),
[Ollama structured output](https://docs.ollama.com/capabilities/structured-outputs),
[Ollama local/cloud configuration](https://docs.ollama.com/faq).

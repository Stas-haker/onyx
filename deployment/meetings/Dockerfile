ARG ONYX_MEETINGS_BASE=onyx-local-backend:meetings
FROM ${ONYX_MEETINGS_BASE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY deployment/meetings/requirements.txt /tmp/meetings-requirements.txt
RUN python -m venv /opt/meetings && /opt/meetings/bin/pip install --no-cache-dir -r /tmp/meetings-requirements.txt
COPY backend/scripts/process_local_meeting.py /app/scripts/process_local_meeting.py
ENV MEETINGS_PYTHON=/opt/meetings/bin/python \
    LD_LIBRARY_PATH=/opt/meetings/lib/python3.11/site-packages/nvidia/cublas/lib:/opt/meetings/lib/python3.11/site-packages/nvidia/cudnn/lib \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 PYANNOTE_METRICS_ENABLED=0
RUN mkdir -p /var/lib/onyx/meetings && chown onyx:onyx /var/lib/onyx/meetings
USER onyx

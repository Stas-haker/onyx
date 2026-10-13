# Local meeting operations (configurable source templates)

These scripts preserve the startup and backup workflows as portable source.
They are not an exact export of any workstation. Local settings and credentials
are deliberately excluded. Do not replace a working installation without testing.

Copy settings.example.json to settings.local.json and supply the selected WSL
distribution, Linux user, absolute Linux package/repository/backup paths, Compose
project name, and Windows timezone ID (Get-TimeZone). The Linux package path is
this directory as seen inside WSL. Paths with spaces are currently unsupported.
Keep the package in a location writable only by trusted users. Never commit local
settings, .env, databases, recordings, transcripts, logs, or model weights.

Run Install.ps1 in Windows PowerShell as the user running Docker Desktop. It adds
Onyx Meetings startup (at Windows sign-in) and Onyx Meetings backup (daily 03:00
in the configured/verified Windows timezone). Windows must stay signed in; screen
locking is fine. Docker Desktop needs its own startup enabled. Missed backup runs
are not caught up during the day. Installation does not run either task immediately.
Existing tasks under other names are not disabled: avoid duplicate schedules by
reviewing and disabling superseded tasks before installing this template.

Startup starts only existing project containers, never recreates them, checks API,
worker ping and local Ollama availability, and leaves Ollama/GPU settings alone.
It starts workers even if deliberately stopped previously for large-model use.
It is not a continuous monitor and does not reserve GPU memory. Do not run manual
mode switching simultaneously. The backup directory lock coordinates these two
scripts only when they share the same backup path.

Backup requires the five compose files listed in backup.py, relay config and the
expected services/volumes. Busy workers/queues skip scheduled runs. Other preflight
failures are errors. It stops portal writers, dumps DB and local file volumes,
archives configuration plus tracked working source, tests restore in isolated
resources, then resumes prior services. No retention or remote copy is configured.
It excludes Docker images, model weights, Open WebUI and untracked source files.
Archive secrets and recordings remain local; protect backups and copy them to an
approved separate device. Monitor free disk space. Pending messages are not backed
up; do not submit work or switch modes during backup. A crash may require manual
service recovery. Application-level/GPU behavior is not tested by restore rehearsal.

Read backups/logs/latest.txt and its referenced log: exit 0 can mean SKIPPED, not
a verified copy. Successful backup has BACKUP VERIFIED and SUCCESS. Startup logs
are under backups/startup-logs. Disable tasks with Disable-ScheduledTask using the
names above; this does not stop services already running.

Validation: Python/PowerShell syntax and isolated configured-container checks.
The pre-generalization workflows were exercised on a deployment; these configurable
variants still need WSL/Docker and scheduler integration testing before rollout.

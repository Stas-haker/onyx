#!/usr/bin/env python3
"""Offline portal backup with a disposable PostgreSQL restore rehearsal.

Run in Ubuntu/WSL. Does not stop or configure the existing Windows Ollama.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import uuid
from datetime import datetime, timezone

FILES = ["docker-compose.yml", "docker-compose.onyx-lite.yml",
         "docker-compose.meetings.yml", "docker-compose.local-access.yml",
         "docker-compose.ollama-relay.yml"]
WORKERS = dict(zip(
    ["meeting_transcribe_0", "meeting_transcribe_1", "meeting_diarize", "meeting_analyze"],
    ["meeting-transcribe-0", "meeting-transcribe-1", "meeting-diarize", "meeting-analyze"]))
WRITERS = ["nginx", "api_server", *WORKERS]
ALLOWED = set(WRITERS) | {"web_server", "cache", "relational_db", "ollama-relay", "meeting_storage_init"}


class BackupError(Exception):
    pass


def run(args, **kwargs):
    kwargs.setdefault('timeout', 1800)
    result = subprocess.run(args, check=False, **kwargs)
    if result.returncode:
        raise BackupError(f"Command failed: {args[0]} {args[1] if len(args) > 1 else ''}; code={result.returncode}")
    return result


def output(args):
    return run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout.decode().strip()


def stop_service(service, cid, seconds=120):
    print(f'Stopping {service} (up to {seconds}s)...', flush=True)
    if service == 'nginx':
        run(['docker', 'stop', '--time', '20', cid], timeout=40, stdout=subprocess.DEVNULL)
    else:
        # Explicit TERM only: never force-kill early-ack Celery jobs.
        run(['docker', 'kill', '--signal=TERM', cid], timeout=30, stdout=subprocess.DEVNULL)
    deadline = time.monotonic() + seconds
    while True:
        state = json.loads(output(['docker', 'inspect', cid]))[0]['State']
        if not state['Running'] and state['Status'] == 'exited':
            print(f'Stopped: {service}', flush=True)
            return
        if time.monotonic() >= deadline:
            raise BackupError(f'{service} did not exit within {seconds}s; no forced kill. '
                              'It may still be shutting down; inspect its state before further work.')
        time.sleep(2)


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def named_volume(container, destination):
    mounts = [m for m in container['Mounts'] if m['Destination'] == destination]
    if len(mounts) != 1 or mounts[0]['Type'] != 'volume':
        raise BackupError(f"Expected one named volume at {destination}; no backup started.")
    return mounts[0]['Name']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scheduled', action='store_true', help='Unattended run; skip busy queues')
    parser.add_argument('--repo', type=Path, default=Path(os.environ['MEETINGS_REPO']))
    parser.add_argument('--destination', type=Path, default=Path(os.environ['MEETINGS_BACKUPS']))
    opts = parser.parse_args()
    if sys.platform != 'linux':
        raise BackupError('Run this script inside Ubuntu/WSL, not Windows Python.')
    os.umask(0o077)
    repo = opts.repo.resolve(strict=True)
    compose_dir = repo / 'deployment/docker_compose'
    for name in [*FILES, '.env', 'ollama-relay.conf']:
        if not (compose_dir / name).is_file():
            raise BackupError(f'Missing required file: {name}')
    guard_path = Path(__file__).with_name('check_workers.py')
    guard = base64.b64encode(guard_path.read_bytes()).decode('ascii')
    code = f"import base64; exec(compile(base64.b64decode('{guard}'), 'check_workers.py', 'exec'))"
    dc = ['docker', 'compose', '--project-directory', str(compose_dir), '-p', os.environ['MEETINGS_PROJECT']]
    for name in FILES:
        dc.extend(['-f', str(compose_dir / name)])
    run(dc + ['config', '--quiet'])
    ids = output(dc + ['ps', '-a', '-q']).splitlines()
    if not ids:
        raise BackupError('Portal containers not found.')
    containers = json.loads(output(['docker', 'inspect', *ids]))
    services = {c['Config']['Labels']['com.docker.compose.service']: c for c in containers}
    if any(c['State']['Status'] not in ('running', 'exited', 'created') for c in containers):
        raise BackupError('A container is restarting/paused. Repair its state first.')
    running = {s for s, c in services.items() if c['State']['Running']}
    if running - ALLOWED:
        raise BackupError('Additional running Onyx services found; backup scope needs review.')
    if not {'nginx', 'web_server', 'ollama-relay', 'api_server', 'relational_db', 'cache'}.issubset(running):
        raise BackupError('Portal, Ollama relay, API, PostgreSQL and Redis must be running for preflight.')
    if not set(WORKERS).issubset(services):
        raise BackupError('Expected meeting worker containers are missing.')
    if len(set(WORKERS) & running) not in (0, 4):
        raise BackupError('Use a stable mode with either all four workers running or all four stopped.')
    nodes = [f"{prefix}@{services[name]['Config']['Hostname']}"
             for name, prefix in WORKERS.items() if name in running]
    pg = services['relational_db']
    api = services['api_server']
    volumes = {
        'meeting-files.tar.gz': named_volume(api, '/var/lib/onyx/meetings'),
        'portal-files.tar.gz': named_volume(api, '/app/file-system'),
    }
    opts.destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = opts.destination.resolve()
    if destination.is_relative_to(repo):
        raise BackupError('Choose a backup destination outside the repository.')
    print('Backup includes database, recordings, portal files, configuration (with secrets), and tracked source files.')
    print('Model weights, Docker images and Open WebUI are NOT included.')
    print('Portal will be temporarily unavailable. Existing Ollama/Open WebUI remain running.')
    print(f'Destination: {destination}')
    print('Do not upload recordings or switch modes until this operation ends.')
    if not opts.scheduled and input('Type YES when all portal work is finished: ').strip().upper() != 'YES':
        print('Cancelled. No services changed.')
        return
    # Fail closed before any shutdown if the queue is busy or a worker is unknown.
    preflight = subprocess.run(dc + ['exec', '-T', 'api_server', 'python', '-c', code, 'idle', *nodes], timeout=120)
    if opts.scheduled and preflight.returncode == 75:
        print('SKIPPED: meeting workers or queues are busy; no services changed.')
        return
    if preflight.returncode:
        raise BackupError('Worker preflight failed; no services changed.')
    token = uuid.uuid4().hex
    label = 'onyx.meetings.backup.check=' + token
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + token[:8]
    staging = destination / (stamp + '.incomplete')
    staging.mkdir(mode=0o700)
    resume = []
    temporary_containers = []
    temporary_volumes = []
    failure = None
    finalized = False
    lock = None
    try:
        import fcntl
        lock = (destination / '.backup.lock').open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError('Another backup is already running.')
        # Stop ingress and API before workers so no new portal upload can enqueue.
        for service in WRITERS:
            if service in running:
                cid = services[service]['Id']
                resume.append(cid)
                stop_service(service, cid)
        # Detect a stage queued during graceful shutdown. Do not discard it.
        run(dc + ['run', '--rm', '--no-deps', '-T', 'api_server',
                  'python', '-c', code, 'idle'])
        print('Creating database archive...')
        with (staging / 'database.dump').open('wb') as target, (staging / 'dump.log').open('wb') as log:
            run(['docker', 'exec', pg['Id'], 'sh', '-c',
                 'exec pg_dump -Fc -U "$POSTGRES_USER" -d "${POSTGRES_DB:-postgres}"'],
                stdout=target, stderr=log)
        for filename, volume in volumes.items():
            print(f'Archiving {filename}...')
            name = 'onyx-meetings-backup-' + uuid.uuid4().hex
            temporary_containers.append(name)
            with (staging / filename).open('wb') as target:
                run(['docker', 'run', '--rm', '--name', name, '--label', label,
                     '--network', 'none', '--user', '0', '--entrypoint', 'tar',
                     '--mount', f'type=volume,src={volume},dst=/source,readonly',
                     api['Image'], '-C', '/source', '-czf', '-', '.'], stdout=target)
        with tarfile.open(staging / 'configuration.tar.gz', 'w:gz') as archive:
            for name in [*FILES, '.env', 'ollama-relay.conf']:
                archive.add(compose_dir / name, arcname='docker_compose/' + name)
            archive.add(repo / 'deployment/data/nginx', arcname='data/nginx')
        tracked = run(['git', '-C', str(repo), 'ls-files', '-z'], stdout=subprocess.PIPE).stdout
        with tarfile.open(staging / 'source.tar.gz', 'w:gz') as archive:
            for entry in tracked.split(b'\0'):
                if not entry:
                    continue
                relative = Path(os.fsdecode(entry))
                if relative.is_absolute() or '..' in relative.parts:
                    raise BackupError('Invalid tracked repository path.')
                source = repo / relative
                if source.exists() or source.is_symlink():
                    archive.add(source, arcname=str(relative), recursive=False)
        metadata = {
            'created_utc': stamp, 'project': os.environ['MEETINGS_PROJECT'],
            'commit': output(['git', '-C', str(repo), 'rev-parse', 'HEAD']),
            'volumes': volumes,
            'services': {s: {'image_id': c['Image'], 'image_reference': c['Config']['Image'],
                             'was_running': s in running} for s, c in services.items()},
            'scope': 'Portal data and configuration; excludes models, Docker image layers and Open WebUI.',
        }
        (staging / 'manifest.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        print('Checking archive integrity...')
        for archive in staging.glob('*.tar.gz'):
            run(['gzip', '-t', str(archive)])
            run(['tar', '-tzf', str(archive)], stdout=subprocess.DEVNULL)
        # Restore into a fresh isolated PostgreSQL instance. No production mounts.
        print('Testing database restore in a temporary isolated container...')
        check_name = 'onyx-meetings-restore-' + uuid.uuid4().hex
        temporary_containers.append(check_name)
        run(['docker', 'run', '-d', '--name', check_name, '--label', label,
             '--network', 'none', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust',
             pg['Image']], stdout=subprocess.DEVNULL)
        ready = False
        for _ in range(90):
            # Force TCP localhost: the temporary initialization server uses a socket only.
            result = subprocess.run(['docker', 'exec', check_name, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                ready = True
                break
            time.sleep(1)
        if not ready:
            raise BackupError('Temporary PostgreSQL did not become ready.')
        with (staging / 'database.dump').open('rb') as data, (staging / 'restore.log').open('wb') as log:
            run(['docker', 'exec', '-i', check_name, 'pg_restore', '--exit-on-error',
                 '--no-owner', '--no-privileges', '-h', '127.0.0.1', '-U', 'postgres', '-d', 'postgres'],
                stdin=data, stdout=log, stderr=subprocess.STDOUT)
        for filename in volumes:
            temp_volume = 'onyx-meetings-verify-' + uuid.uuid4().hex
            run(['docker', 'volume', 'create', '--label', label, temp_volume], stdout=subprocess.DEVNULL)
            temporary_volumes.append(temp_volume)
            name = 'onyx-meetings-extract-' + uuid.uuid4().hex
            temporary_containers.append(name)
            with (staging / filename).open('rb') as data:
                run(['docker', 'run', '--rm', '-i', '--name', name, '--label', label,
                     '--network', 'none', '--user', '0', '--entrypoint', 'tar',
                     '--mount', f'type=volume,src={temp_volume},dst=/restore', api['Image'],
                     '-C', '/restore', '-xzf', '-'], stdin=data)
        checksums = {p.name: digest(p) for p in staging.iterdir() if p.is_file()}
        (staging / 'sha256.json').write_text(json.dumps(checksums, indent=2), encoding='utf-8')
        (staging / 'VERIFIED.txt').write_text(
            'Database restored successfully in disposable PostgreSQL (ownership/ACL excluded from rehearsal).\n'
            'File volumes extracted successfully into disposable volumes. Archive checksums recorded.\n'
            'Application login, GPU inference and owner/ACL restoration were not tested.\n', encoding='utf-8')
        final = destination / stamp
        staging.rename(final)
        finalized = True
        print(f'BACKUP VERIFIED: {final}')
    except BaseException as error:
        failure = error
    finally:
        # Remove only resources carrying this run's random ownership label.
        for name in temporary_containers:
            try:
                objects = json.loads(output(['docker', 'inspect', name]))
                if objects[0]['Config']['Labels'].get('onyx.meetings.backup.check') == token:
                    run(['docker', 'rm', '-f', '-v', name], stdout=subprocess.DEVNULL)
            except Exception as error:
                # Auto-removed helper containers no longer exist; that is normal.
                probe = subprocess.run(['docker', 'inspect', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if probe.returncode == 0:
                    print(f'Cleanup incomplete for temporary container {name}', file=sys.stderr)
                    failure = failure or error
        for name in temporary_volumes:
            try:
                obj = json.loads(output(['docker', 'volume', 'inspect', name]))[0]
                if obj['Labels'].get('onyx.meetings.backup.check') == token:
                    run(['docker', 'volume', 'rm', name], stdout=subprocess.DEVNULL)
            except Exception as error:
                print(f'Cleanup incomplete for temporary volume {name}', file=sys.stderr)
                failure = failure or error
        # Restore only containers that were running before this backup.
        if resume:
            print('Restoring previous portal service state...')
            for service in ['api_server', 'web_server', 'nginx', *WORKERS]:
                cid = services[service]['Id'] if service in services else ''
                if cid in resume:
                    try:
                        print(f'Starting {service}...', flush=True)
                        run(['docker', 'start', cid], timeout=45, stdout=subprocess.DEVNULL)
                    except Exception as error:
                        print(f'Could not restart {service}; run docker compose start for it.', file=sys.stderr)
                        failure = failure or error
        if lock:
            lock.close()
    if failure:
        if not finalized:
            print(f'Incomplete backup retained for diagnosis: {staging}', file=sys.stderr)
        detail = str(failure) if isinstance(failure, BackupError) else type(failure).__name__
        raise BackupError(f'Backup/resume did not fully complete: {detail}. Check messages and local logs.') from failure
    # Health readiness after restart, rather than claiming readiness from docker start.
    for _ in range(90):
        current = json.loads(output(['docker', 'inspect', api['Id']]))[0]
        if current['State'].get('Health', {}).get('Status') == 'healthy':
            break
        time.sleep(1)
    else:
        raise BackupError('Backup verified, but API has not become healthy. Check service logs.')
    if nodes:
        run(dc + ['exec', '-T', 'api_server', 'python', '-c', code, 'ready', *nodes])
    print('SUCCESS: backup verified and prior portal service state restored. Ollama was not changed.')


if __name__ == '__main__':
    try:
        main()
    except (BackupError, OSError, subprocess.SubprocessError) as error:
        print(f'STOPPED: {error}', file=sys.stderr)
        sys.exit(1)

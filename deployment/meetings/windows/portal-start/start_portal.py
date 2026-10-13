import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

SERVICES = ['relational_db', 'cache', 'api_server', 'web_server', 'ollama-relay', 'nginx', 'meeting_transcribe_0', 'meeting_transcribe_1', 'meeting_diarize', 'meeting_analyze']

def run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=40)

def inspect(service):
    r = run(['docker', 'inspect', os.environ['MEETINGS_PROJECT'] + '-' + service + '-1'])
    if r.returncode:
        raise RuntimeError('Container missing/unavailable: ' + service)
    return json.loads(r.stdout)[0]

def start_existing(service):
    c = inspect(service)
    if c['State']['Status'] not in ('running', 'exited', 'created'):
        raise RuntimeError(service + ': unexpected state ' + c['State']['Status'])
    if not c['State']['Running']:
        print('Starting ' + service, flush=True)
        r = run(['docker', 'start', c['Id']])
        if r.returncode:
            raise RuntimeError('Cannot start ' + service + ': ' + r.stderr.strip())
    else:
        print('Already running: ' + service, flush=True)

def main():
    deadline = time.monotonic() + 600
    print('Waiting for Docker Desktop...', flush=True)
    while True:
        r = run(['docker', 'info', '--format', '{{.ServerVersion}}'])
        if r.returncode == 0:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('Docker Desktop unavailable after 10 minutes')
        time.sleep(10)
    # Verify every container before starting any of them. Never recreate or pull.
    for s in SERVICES:
        inspect(s)
    for s in SERVICES:
        start_existing(s)
        if s in ('relational_db', 'api_server'):
            for attempt in range(90):
                if inspect(s)['State'].get('Health', {}).get('Status') == 'healthy':
                    break
                time.sleep(2)
            else:
                raise RuntimeError(s + ' is not healthy')
    prefixes = ['meeting-transcribe-0', 'meeting-transcribe-1', 'meeting-diarize', 'meeting-analyze']
    nodes = [prefix + '@' + inspect(s)['Config']['Hostname'] for prefix, s in zip(prefixes, SERVICES[-4:])]
    check = 'import sys; from onyx.background.celery.apps.meetings import celery_app; n=sys.argv[1:]; r=celery_app.control.inspect(destination=n,timeout=5).ping() or {}; sys.exit(0 if all(r.get(x,{}).get("ok")=="pong" for x in n) else 1)'
    for attempt in range(30):
        r = run(['docker', 'exec', os.environ['MEETINGS_PROJECT'] + '-api_server-1', 'python', '-c', check, *nodes])
        if r.returncode == 0:
            break
        time.sleep(3)
    else:
        raise RuntimeError('Meeting workers did not answer')
    check = 'import os,urllib.request; u=os.environ["MEETINGS_OLLAMA_URL"]+"/api/tags"; r=urllib.request.build_opener(urllib.request.ProxyHandler({})).open(u,timeout=10); assert r.status==200'
    for attempt in range(30):
        r = run(['docker', 'exec', os.environ['MEETINGS_PROJECT'] + '-meeting_analyze-1', 'python', '-c', check])
        if r.returncode == 0:
            print('SUCCESS: API healthy, workers ready, Ollama relay HTTP 200. GPU allocation unchanged.', flush=True)
            return
        time.sleep(5)
    raise RuntimeError('Portal started but Ollama relay is unavailable; existing Ollama was not changed')

if __name__ == '__main__':
    import fcntl
    os.umask(0o077)
    logs = Path(os.environ['MEETINGS_BACKUPS']) / 'startup-logs'
    logs.mkdir(parents=True, exist_ok=True)
    backups = Path(os.environ['MEETINGS_BACKUPS'])
    backups.mkdir(parents=True, exist_ok=True)
    log = logs / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.log')
    with log.open('w', buffering=1) as stream, (backups / '.backup.lock').open('a') as lock:
        sys.stdout = sys.stderr = stream
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('SKIPPED: backup is running; no services changed')
            sys.exit(0)
        try:
            main()
        except Exception as e:
            print('FAILED: ' + str(e), flush=True)
            sys.exit(1)

import datetime
import fcntl
import os
from pathlib import Path
import subprocess
import sys

os.umask(0o077)
root = Path(os.environ['MEETINGS_BACKUPS'])
logs = root / 'logs'
logs.mkdir(parents=True, exist_ok=True)
with (root / '.scheduled.lock').open('a') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('SKIPPED: scheduled backup already running')
        sys.exit(0)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    log = logs / (stamp + '.log')
    with log.open('w') as stream:
        result = subprocess.run([sys.executable, '-u', str(Path(__file__).with_name('backup.py')), '--scheduled'], stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        stream.write('\nExit code: ' + str(result.returncode) + '\n')
    (logs / 'latest.txt').write_text(str(log) + '\nExit code: ' + str(result.returncode) + '\n')
    print('Log:', log)
    sys.exit(result.returncode)

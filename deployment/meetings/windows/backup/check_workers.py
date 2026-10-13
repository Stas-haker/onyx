"""Read-only Celery checks; never print task arguments or broker credentials."""
import sys
import time

from onyx.background.celery.apps.meetings import celery_app

class BusyError(RuntimeError):
    pass

stage = "initialization"


def check_idle(nodes, allow_queued=False):
    global stage
    if nodes:
        inspector = celery_app.control.inspect(destination=nodes, timeout=5)
        for method in ("active", "reserved", "scheduled"):
            stage = "worker_" + method
            replies = getattr(inspector, method)() or {}
            if not set(nodes).issubset(replies):
                raise RuntimeError("A worker did not respond. Switching refused.")
            if any(replies[node] for node in nodes):
                raise BusyError("Meeting work is still in progress. Wait for completion.")
    if not allow_queued:
        stage = "redis_connection"
        with celery_app.connection_for_read() as connection:
            if connection.transport.driver_type != "redis":
                raise RuntimeError("This deployment check requires the Redis broker.")
            with connection.channel() as channel:
                for queue in ("meetings_transcribe", "meetings_diarize", "meetings_analyze"):
                    stage = "queue_length:" + queue
                    # Redis deletes empty lists. Passive declaration can raise
                    # NOT_FOUND for a healthy empty queue. Kombu's Redis _size
                    # only issues LLEN, across configured priority lists and
                    # using the broker's configured database/key prefix.
                    count = channel._size(queue)
                    if not isinstance(count, int) or count < 0:
                        raise RuntimeError("Invalid queue length; switching refused.")
                    print(f"{queue}: {count} pending", flush=True)
                    if count:
                        raise BusyError("Meeting queue is not empty. Finish pending meetings first.")


def check_ready(nodes):
    global stage
    stage = "worker_ping"
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        replies = celery_app.control.inspect(destination=nodes, timeout=5).ping() or {}
        if all(replies.get(node, {}).get("ok") == "pong" for node in nodes):
            return
        time.sleep(2)
    raise RuntimeError("Workers did not become ready within 90 seconds.")


if __name__ == "__main__":
    try:
        action, *nodes = sys.argv[1:]
        if action == "ready":
            if len(nodes) != 4:
                raise RuntimeError("Expected four running meeting workers.")
            check_ready(nodes)
        elif action in ("idle", "resume"):
            check_idle(nodes, allow_queued=action == "resume" and not nodes)
        else:
            raise RuntimeError("Unknown check.")
        print("Worker check OK.")
    except Exception as error:
        # Do not expose exception messages from broker libraries.
        detail = str(error) if isinstance(error, RuntimeError) else "Service check failed"
        print(f"{detail} [stage={stage}; type={type(error).__name__}]", file=sys.stderr)
        sys.exit(75 if isinstance(error, BusyError) else 1)

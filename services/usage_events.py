"""Lossy, bounded telemetry. Never call a core service or retry failed writes."""
import asyncio
import logging
import time
from contextlib import suppress
from datetime import datetime, timezone

import httpx

from services.config import get_secret
from services.supabase_auth import supabase_headers

log = logging.getLogger('ailab.analytics')


class UsageCollector:
    def __init__(self):
        self.queue = None
        self.task = None
        self.cooldown = 0.0

    async def start(self):
        # Dedicated credentials are optional; never use ZIPON_SUPABASE_*.
        self.url = get_secret('ANALYTICS_SUPABASE_URL') or get_secret('SUPABASE_URL')
        self.key = (get_secret('ANALYTICS_SUPABASE_SERVICE_ROLE_KEY')
                    if get_secret('ANALYTICS_SUPABASE_URL') else get_secret('SUPABASE_SERVICE_ROLE_KEY'))
        if not self.url or not self.key:
            return
        self.queue = asyncio.Queue(maxsize=256)
        self.task = asyncio.create_task(self._run())

    def offer(self, event):
        """Only bounded in-memory work on the request path; drop on overload."""
        try:
            if self.queue is None or time.monotonic() < self.cooldown:
                return
            self.queue.put_nowait({**event, 'created_at': datetime.now(timezone.utc).isoformat()})
        except Exception:
            pass

    async def _run(self):
        try:
            headers = supabase_headers(self.key, prefer='return=minimal')
            async with httpx.AsyncClient(timeout=0.8, follow_redirects=False,
                                         limits=httpx.Limits(max_connections=1)) as client:
                while True:
                    first = await self.queue.get()
                    batch = [first]
                    while len(batch) < 20 and not self.queue.empty():
                        batch.append(self.queue.get_nowait())
                    try:
                        response = await asyncio.wait_for(client.post(
                            self.url.rstrip('/') + '/rest/v1/usage_events',
                            headers=headers, json=batch), timeout=1.0)
                        response.raise_for_status()
                    except Exception:
                        # No exception text/URL/credentials/payloads in logs. One per cooldown.
                        log.warning('analytics write dropped; collection paused for 60s')
                        self.cooldown = time.monotonic() + 60
                        while not self.queue.empty():
                            self.queue.get_nowait()
                            self.queue.task_done()
                    finally:
                        for _ in batch:
                            self.queue.task_done()
        except Exception:
            self.queue = None
            log.warning('analytics disabled: writer unavailable')

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        self.task = None
        self.queue = None


collector = UsageCollector()

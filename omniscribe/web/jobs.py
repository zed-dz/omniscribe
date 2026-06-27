"""A tiny in-memory background-job manager.

Long operations (multi-page OCR, transcription, model downloads) run in a worker thread
so the HTTP request returns instantly with a job id. The frontend polls ``/api/job/{id}``
for live progress. Heavy work (Tesseract, ffmpeg, Vosk) is native and releases the GIL,
so threads give real concurrency here.
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued | running | done | error
    progress: float = 0.0  # 0..1
    message: str = ""
    result: Any = None
    error: str | None = None
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 3),
            "message": self.message,
            "result": self.result if self.status == "done" else None,
            "error": self.error,
        }


class JobManager:
    def __init__(self, max_workers: int = 2):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="omniscribe-job")

    def create(self, kind: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def submit(self, kind: str, work: Callable[[Callable[[float, str], None]], Any]) -> Job:
        """Run ``work(progress_cb)`` in the pool; return the Job immediately."""
        job = self.create(kind)

        def progress(p: float, msg: str = ""):
            job.progress = max(0.0, min(1.0, float(p)))
            if msg:
                job.message = msg
            job.updated = time.time()

        def runner():
            job.status = "running"
            job.updated = time.time()
            try:
                job.result = work(progress)
                job.progress = 1.0
                job.status = "done"
                if not job.message:
                    job.message = "Completed"
            except Exception as exc:  # surface the full traceback for debugging
                job.status = "error"
                job.error = f"{type(exc).__name__}: {exc}"
                job.message = job.error
                job.result = {"traceback": traceback.format_exc()}
            finally:
                job.updated = time.time()

        self.cleanup()  # opportunistically drop old finished jobs to bound memory
        self._pool.submit(runner)
        return job

    def cleanup(self, max_age: float = 3600):
        now = time.time()
        with self._lock:
            stale = [jid for jid, j in self._jobs.items()
                     if now - j.updated > max_age and j.status in ("done", "error")]
            for jid in stale:
                del self._jobs[jid]


manager = JobManager()

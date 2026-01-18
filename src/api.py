"""FastAPI service for Discord Object Store."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiofiles
import discord
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .cli import _upload_backup_to_discord
from .config import Config
from .database import (
    DEFAULT_DB_PATH,
    delete_batch,
    get_batch,
    get_chunks,
    get_storage_stats,
    init_database,
    list_batches,
)
from .discord_client import download_chunks_concurrent, setup_bot
from .downloader import download
from .file_processor import calculate_file_hash
from .syncer import sync_from_discord
from .uploader import upload
from .utils import StorageBotError


BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"
TEMP_UPLOADS_DIR = BASE_DIR / "temp_uploads"


@dataclass
class Job:
    id: str
    job_type: str
    status: str = "queued"
    progress: int = 0
    logs: List[str] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


JOBS: Dict[str, Job] = {}
JOB_LOCK = asyncio.Lock()
DISCORD_LOCK = asyncio.Lock()


class DownloadRequest(BaseModel):
    batch_id: str
    destination_path: Optional[str] = None


class VerifyRequest(BaseModel):
    batch_id: str


class DeleteRequest(BaseModel):
    batch_id: str
    delete_remote: bool = False


class SyncRequest(BaseModel):
    reset: bool = False


class BackupRequest(BaseModel):
    upload_to_discord: bool = False


app = FastAPI(title="Discord Object Store API")


def _job_snapshot(job: Job) -> Dict[str, Any]:
    return {
        "id": job.id,
        "type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "logs": job.logs,
        "result": job.result,
        "error": job.error,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


async def _log(job_id: str, message: str) -> None:
    async with JOB_LOCK:
        job = JOBS[job_id]
        job.logs.append(message)


async def _set_status(job_id: str, status: str, progress: int | None = None) -> None:
    async with JOB_LOCK:
        job = JOBS[job_id]
        job.status = status
        if progress is not None:
            job.progress = progress


async def _complete_job(job_id: str, result: Dict[str, Any]) -> None:
    async with JOB_LOCK:
        job = JOBS[job_id]
        job.status = "complete"
        job.progress = 100
        job.result = result
        job.finished_at = datetime.utcnow().isoformat() + "Z"


async def _fail_job(job_id: str, error: str) -> None:
    async with JOB_LOCK:
        job = JOBS[job_id]
        job.status = "failed"
        job.error = error
        job.finished_at = datetime.utcnow().isoformat() + "Z"


def _create_job(job_type: str) -> Job:
    job_id = uuid4().hex
    job = Job(id=job_id, job_type=job_type, started_at=datetime.utcnow().isoformat() + "Z")
    JOBS[job_id] = job
    return job


async def _run_job(job_id: str, work: Any) -> None:
    try:
        await _set_status(job_id, "running", progress=5)
        result = await work
        await _complete_job(job_id, result)
    except StorageBotError as exc:
        await _fail_job(job_id, str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        await _fail_job(job_id, f"Unexpected error: {exc}")


async def _delete_from_discord(batch_id: str) -> None:
    batch = get_batch(batch_id)
    if not batch:
        raise StorageBotError("Batch not found.")
    config = Config.get_instance()
    client = setup_bot(config.discord_bot_token)
    done: asyncio.Future[None] = asyncio.Future()

    @client.event
    async def on_ready() -> None:
        try:
            if not client.guilds:
                raise StorageBotError("Bot is not connected to any guild.")
            guild = client.guilds[0]
            index_channel = discord.utils.get(
                guild.text_channels, name=config.batch_index_channel_name
            )
            thread_id = int(batch["thread_id"]) if batch.get("thread_id") else None
            message_id = (
                int(batch["archive_message_id"]) if batch.get("archive_message_id") else None
            )

            if thread_id:
                try:
                    thread = client.get_channel(thread_id) or await client.fetch_channel(thread_id)
                    if isinstance(thread, discord.Thread):
                        await thread.delete()
                except discord.NotFound:
                    pass
            if index_channel and message_id:
                try:
                    message = await index_channel.fetch_message(message_id)
                    await message.delete()
                except discord.NotFound:
                    pass

            done.set_result(None)
        except Exception as exc:
            done.set_exception(exc)
        finally:
            await client.close()

    await client.start(config.discord_bot_token)
    await done


async def _verify_batch(batch_id: str) -> None:
    batch = get_batch(batch_id)
    if not batch:
        raise StorageBotError("Batch not found.")
    chunks = get_chunks(batch_id)
    if not chunks:
        raise StorageBotError("No chunks found for batch.")

    temp_dir = BASE_DIR / f"temp_verify_{batch_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        await download_chunks_concurrent(
            chunks,
            temp_dir,
            max_concurrency=Config.get_instance().concurrent_downloads,
            progress_callback=None,
        )
        for chunk in chunks:
            path = temp_dir / f"chunk_{chunk['chunk_index']}.bin"
            digest = await calculate_file_hash(path)
            if digest != chunk["file_hash"]:
                raise StorageBotError(
                    f"Integrity check failed for chunk {chunk['chunk_index']}"
                )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.on_event("startup")
async def _startup() -> None:
    init_database()
    TEMP_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
async def root() -> FileResponse:
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Web UI not found.")
    return FileResponse(index_path)


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/batches")
async def api_list_batches() -> List[Dict[str, Any]]:
    return list_batches()


@app.get("/api/batches/{batch_id}")
async def api_get_batch(batch_id: str) -> Dict[str, Any]:
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return batch


@app.get("/api/stats")
async def api_stats() -> Dict[str, Any]:
    return get_storage_stats()


@app.post("/api/jobs/upload")
async def api_upload(
    files: List[UploadFile] = File(...),
    title: str = Form(""),
    tags: str = Form(""),
    description: str = Form(""),
    confirm: bool = Form(False),
) -> Dict[str, str]:
    job = _create_job("upload")
    meta = {"title": title, "tags": tags, "description": description}
    upload_root = TEMP_UPLOADS_DIR / job.id
    upload_root.mkdir(parents=True, exist_ok=True)
    uploaded_paths: List[Path] = []

    try:
        await _log(job.id, "Receiving upload...")
        for upload_file in files:
            relative_name = upload_file.filename.replace("\\", "/")
            target_path = upload_root / relative_name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(target_path, "wb") as outfile:
                while True:
                    chunk = await upload_file.read(1024 * 1024)
                    if not chunk:
                        break
                    await outfile.write(chunk)
            await upload_file.close()
            uploaded_paths.append(target_path)
        await _log(job.id, f"Saved {len(uploaded_paths)} file(s).")
    except Exception as exc:
        await _fail_job(job.id, f"Failed to save upload: {exc}")
        return {"job_id": job.id}

    async def _work() -> Dict[str, Any]:
        await _log(job.id, "Starting Discord upload...")
        async with DISCORD_LOCK:
            source_path = uploaded_paths[0] if len(uploaded_paths) == 1 else upload_root
            batch_id = await upload(str(source_path), confirm=confirm, metadata=meta)
        await _log(job.id, f"Upload complete. Batch ID: {batch_id}")
        shutil.rmtree(upload_root, ignore_errors=True)
        return {"batch_id": batch_id}

    asyncio.create_task(_run_job(job.id, _work()))
    return {"job_id": job.id}


@app.post("/api/jobs/download")
async def api_download(payload: DownloadRequest) -> Dict[str, str]:
    job = _create_job("download")
    destination = payload.destination_path or str(BASE_DIR / "downloads")

    async def _work() -> Dict[str, Any]:
        await _log(job.id, f"Restoring batch to {destination}...")
        async with DISCORD_LOCK:
            restored_path = await download(payload.batch_id, destination)
        return {"restored_path": str(restored_path)}

    asyncio.create_task(_run_job(job.id, _work()))
    return {"job_id": job.id}


@app.post("/api/jobs/verify")
async def api_verify(payload: VerifyRequest) -> Dict[str, str]:
    job = _create_job("verify")

    async def _work() -> Dict[str, Any]:
        await _log(job.id, "Downloading and verifying chunks...")
        async with DISCORD_LOCK:
            await _verify_batch(payload.batch_id)
        return {"batch_id": payload.batch_id, "status": "verified"}

    asyncio.create_task(_run_job(job.id, _work()))
    return {"job_id": job.id}


@app.post("/api/jobs/delete")
async def api_delete(payload: DeleteRequest) -> Dict[str, str]:
    job = _create_job("delete")

    async def _work() -> Dict[str, Any]:
        if payload.delete_remote:
            await _log(job.id, "Deleting remote Discord artifacts...")
            async with DISCORD_LOCK:
                await _delete_from_discord(payload.batch_id)
        delete_batch(payload.batch_id)
        await _log(job.id, "Deleted local metadata.")
        return {"batch_id": payload.batch_id}

    asyncio.create_task(_run_job(job.id, _work()))
    return {"job_id": job.id}


@app.post("/api/jobs/sync")
async def api_sync(payload: SyncRequest) -> Dict[str, str]:
    job = _create_job("sync")

    async def _work() -> Dict[str, Any]:
        await _log(job.id, "Syncing from Discord...")
        async with DISCORD_LOCK:
            synced = await sync_from_discord(reset_db=payload.reset)
        return {"synced": synced}

    asyncio.create_task(_run_job(job.id, _work()))
    return {"job_id": job.id}


@app.post("/api/jobs/backup")
async def api_backup(payload: BackupRequest) -> Dict[str, str]:
    job = _create_job("backup")

    async def _work() -> Dict[str, Any]:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = DEFAULT_DB_PATH.with_name(f"storage_backup_{timestamp}.db")
        shutil.copy2(DEFAULT_DB_PATH, backup_path)
        await _log(job.id, f"Backup created at {backup_path}")
        if payload.upload_to_discord:
            await _log(job.id, "Uploading backup to Discord...")
            async with DISCORD_LOCK:
                await _upload_backup_to_discord(backup_path)
        return {"backup_path": str(backup_path)}

    asyncio.create_task(_run_job(job.id, _work()))
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
async def api_job_status(job_id: str) -> Dict[str, Any]:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _job_snapshot(job)

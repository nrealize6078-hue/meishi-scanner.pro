"""FastAPI 本体。名刺画像/PDFをアップロード→Claudeで抽出→スプレッドシート書き込み。

バグ対策(設計方針):
- 1ファイルずつ独立処理。1件の失敗が他に波及しない(try/exceptで隔離)。
- 処理はバックグラウンドジョブ。GASの6分制限のような時間上限が無い。
- OCR/書き込みは自動リトライ。失敗してもローカルへ必ず退避(データ損失なし)。
- 大きい/壊れたファイルはエラー扱いで記録し、処理は止めずに次へ進む。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, ocr, sheets, storage

config.ensure_dirs()

app = FastAPI(title="名刺スキャナー (Claude Vision)")

# ジョブ進捗を保持するインメモリのストア(プロセス内)。
JOBS: dict[str, dict] = {}

ALLOWED_MEDIA = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "application/pdf": ".pdf",
}


def _process_one(job_id: str, filename: str, media_type: str, data: bytes) -> None:
    """1ファイルを処理。失敗しても例外を外に出さない(ジョブ全体を止めない)。"""
    job = JOBS[job_id]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cards = ocr.extract_cards(data, media_type)
        if not cards:
            job["errors"].append({"file": filename, "error": "名刺を検出できませんでした"})
            job["done"] += 1
            return

        rows = [c.to_sheet_row(filename, now) for c in cards]

        # まずローカルに必ず保存(データ損失防止)
        for c in cards:
            storage.save_result(
                {"file": filename, "processed_at": now, "card": c.model_dump()}
            )

        # スプレッドシート書き込み(設定がある場合のみ)。失敗してもローカルには残る。
        if config.sheets_enabled():
            try:
                sheets.append_rows(rows)
                job["written"] += len(rows)
            except Exception as e:  # noqa: BLE001
                job["errors"].append(
                    {"file": filename, "error": f"Sheets書き込み失敗(ローカル保存済): {e}"}
                )
        job["cards"] += len(cards)
        job["done"] += 1
    except Exception as e:  # noqa: BLE001
        job["errors"].append({"file": filename, "error": f"OCR失敗: {e}"})
        job["done"] += 1


def _run_job(job_id: str, files: list[tuple[str, str, bytes]]) -> None:
    for filename, media_type, data in files:
        _process_one(job_id, filename, media_type, data)
    JOBS[job_id]["status"] = "completed"


@app.post("/api/upload")
async def upload(background: BackgroundTasks, files: list[UploadFile] = File(...)):
    """複数ファイルを受け取りバックグラウンド処理を開始。ジョブIDを返す。"""
    job_id = uuid.uuid4().hex[:12]
    accepted: list[tuple[str, str, bytes]] = []
    rejected: list[dict] = []

    for uf in files:
        data = await uf.read()
        media_type = uf.content_type or ""
        if media_type not in ALLOWED_MEDIA:
            rejected.append({"file": uf.filename, "error": f"非対応の形式: {media_type}"})
            continue
        if len(data) > config.MAX_FILE_MB * 1024 * 1024:
            rejected.append(
                {"file": uf.filename, "error": f"{config.MAX_FILE_MB}MB超過のためスキップ"}
            )
            continue
        accepted.append((uf.filename or "unnamed", media_type, data))

    JOBS[job_id] = {
        "status": "processing",
        "total": len(accepted),
        "done": 0,
        "cards": 0,
        "written": 0,
        "errors": rejected.copy(),
        "sheets_enabled": config.sheets_enabled(),
    }

    background.add_task(_run_job, job_id, accepted)
    return {"job_id": job_id, "accepted": len(accepted), "rejected": rejected}


@app.get("/api/status/{job_id}")
async def status(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        return JSONResponse({"error": "ジョブが見つかりません"}, status_code=404)
    return job


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "model": config.GEMINI_MODEL,
        "gemini_key_set": bool(config.GEMINI_API_KEY),
        "sheets_enabled": config.sheets_enabled(),
    }


_static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")

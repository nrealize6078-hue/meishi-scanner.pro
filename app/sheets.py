"""Googleスプレッドシートへの書き込み。

- サービスアカウント認証(鍵JSON)を使用
- ヘッダー行が無ければ自動作成
- 書き込みは指数バックオフでリトライ
- 失敗してもデータは storage.py がローカルに退避する(呼び出し側で対応)
"""

from __future__ import annotations

import time
from typing import List

from . import config

_service = None


def _get_service():
    global _service
    if _service is not None:
        return _service

    import json

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    # クラウド(Render等): JSON全文を環境変数から渡す方式を優先
    if config.GOOGLE_SERVICE_ACCOUNT_JSON:
        info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=scopes
        )
    else:
        # ローカル開発: 鍵JSONファイルのパスから読み込む
        creds = service_account.Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=scopes,
        )

    _service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return _service


def _ensure_header(svc) -> None:
    """シート1行目にヘッダーが無ければ書き込む。"""
    from .schema import BusinessCard

    rng = f"{config.SHEET_NAME}!A1:M1"
    resp = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=config.SPREADSHEET_ID, range=rng)
        .execute()
    )
    values = resp.get("values", [])
    if not values or not values[0]:
        svc.spreadsheets().values().update(
            spreadsheetId=config.SPREADSHEET_ID,
            range=rng,
            valueInputOption="RAW",
            body={"values": [BusinessCard.sheet_header()]},
        ).execute()


def append_rows(rows: List[List[str]]) -> None:
    """複数行をシート末尾に追記する。失敗時は例外を投げる(呼び出し側でバックアップ)。"""
    if not rows:
        return

    last_err: Exception | None = None
    for attempt in range(config.MAX_RETRIES):
        try:
            svc = _get_service()
            _ensure_header(svc)
            svc.spreadsheets().values().append(
                spreadsheetId=config.SPREADSHEET_ID,
                range=f"{config.SHEET_NAME}!A:M",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": rows},
            ).execute()
            return
        except Exception as e:  # noqa: BLE001 - 全例外をリトライ対象に
            last_err = e
            # 指数バックオフ: 1s, 2s, 4s...
            time.sleep(2 ** attempt)

    assert last_err is not None
    raise last_err

"""ローカルへの永続化(バックアップ)。

Sheets書き込みが失敗しても、抽出結果を必ずローカルに残すことで
データ損失を防ぐ。後から再送(再書き込み)も可能にする。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from . import config


def save_result(record: dict[str, Any]) -> None:
    """1件の処理結果を JSONL で追記保存する(常に成功させる)。"""
    config.ensure_dirs()
    record = {**record, "_saved_at": datetime.now().isoformat(timespec="seconds")}
    with open(config.BACKUP_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_all() -> list[dict[str, Any]]:
    """保存済みの全レコードを読み込む。"""
    if not config.BACKUP_FILE.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(config.BACKUP_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out

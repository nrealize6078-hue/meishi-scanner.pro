"""設定の読み込み。APIキーや認証情報は環境変数(.env)から取得し、
コードには絶対に直書きしない。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# プロジェクト直下の .env を読み込む
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# --- Google Gemini (無料枠) ---
# https://aistudio.google.com/apikey で無料取得(クレカ不要)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# 無料枠で使えるモデル。flash-lite は無料枠が大きく(15RPM/1000RPD)名刺向き
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# --- Google Sheets ---
# 認証方法は2通り(どちらか一方でOK):
#  (1) ローカル開発: 鍵JSONファイルへのパスを GOOGLE_SERVICE_ACCOUNT_FILE に
#  (2) クラウド(Render等): 鍵JSONの中身そのものを GOOGLE_SERVICE_ACCOUNT_JSON に
#      ※ファイルを置けないクラウド環境向け。JSON全文を環境変数に貼り付ける。
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SHEET_NAME = os.getenv("SHEET_NAME", "名刺データ")

# --- ローカルバックアップ ---
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
BACKUP_FILE = DATA_DIR / "backup.jsonl"  # Sheets書き込み失敗時の退避先

# --- 処理上限/挙動 ---
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "30"))  # 1ファイルあたり上限
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))   # OCR/書き込みの自動リトライ回数


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def sheets_enabled() -> bool:
    # 鍵(ファイル or JSON文字列)のどちらかとスプレッドシートIDが揃えば有効
    has_creds = bool(GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON)
    return bool(has_creds and SPREADSHEET_ID)

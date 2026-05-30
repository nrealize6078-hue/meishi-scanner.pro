"""Google Gemini(無料枠)による名刺OCR。

- 画像(JPEG/PNG/WebP)とPDFの両方に対応
- 構造化出力(response_schema)でスキーマ通りのJSONを保証
- レート/一時エラーは指数バックオフでリトライ
"""

from __future__ import annotations

import re
import time
from typing import List

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from . import config
from .schema import BusinessCard


def _retry_delay_seconds(err: Exception) -> float | None:
    """429エラーの本文から、Geminiが指示する待機秒数を取り出す。

    例: "'retryDelay': '32s'" や "Please retry in 32.6s" から 32.x を得る。
    取り出せなければ None。
    """
    text = str(err)
    m = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s", text)
    if not m:
        m = re.search(r"retry in (\d+(?:\.\d+)?)s", text)
    if m:
        # 指示秒数 + 1秒の安全マージン
        return float(m.group(1)) + 1.0
    return None


def _is_rate_limit(err: Exception) -> bool:
    text = str(err)
    return "429" in text or "RESOURCE_EXHAUSTED" in text

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY が未設定です。.env に設定してください。"
            )
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


class CardList(BaseModel):
    """PDF等、1ファイルに複数枚含まれる場合の入れ物。"""

    cards: List[BusinessCard] = Field(
        default_factory=list,
        description="検出した名刺ごとの抽出結果。1枚なら要素1つ。",
    )


SYSTEM_PROMPT = """\
あなたは日本の名刺を読み取る高精度OCRの専門家です。
渡された画像またはPDFから、名刺に記載された情報を正確に抽出してください。

厳守事項:
- 記載されている文字をそのまま正確に書き写す。推測で創作しない。
- 読み取れない・記載が無い項目は空文字 "" にする(でっち上げない)。
- 電話/FAX/携帯は形式を保ったまま(ハイフン含む)抽出する。
  「TEL」「FAX」「携帯」「Mobile」等のラベルで種別を判断する。
- 郵便番号は「〒」を除き「100-0001」の形式にする。
- メールは小文字化せず記載のまま。URLも記載のまま。
- 氏名カナ(ふりがな)は記載がある場合のみ抽出。無ければ空。
- 部署と役職は分けて抽出する。判別が難しければ役職側に入れ、notesに理由を書く。
- 文字がかすれる/見切れる/手書き等で自信が無い場合は confidence を下げ、
  needs_review を true にして notes に状況を書く。
- 1枚の画像/1ページに複数の名刺が写っている場合は、それぞれ別要素として返す。
"""


def extract_cards(file_bytes: bytes, media_type: str) -> List[BusinessCard]:
    """1ファイルから名刺リストを抽出する。

    media_type 例: image/jpeg, image/png, image/webp, application/pdf
    """
    client = get_client()
    part = types.Part.from_bytes(data=file_bytes, mime_type=media_type)

    # レート制限は無料枠で頻発するため、通常エラーより多めに粘る
    max_attempts = max(config.MAX_RETRIES, 6)
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=[part, "この名刺の情報をすべて抽出してください。"],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=CardList,
                    temperature=0.0,
                ),
            )
            parsed = response.parsed
            if parsed is None:
                return []
            return parsed.cards
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt == max_attempts - 1:
                break
            if _is_rate_limit(e):
                # Geminiの指示時間ぶん待つ(無ければ既定で待機)。無料枠の上限解放待ち。
                wait = _retry_delay_seconds(e) or 35.0
                wait = min(wait, 65.0)  # 上限65秒で頭打ち
            else:
                wait = 2 ** attempt  # その他の一時エラーは指数バックオフ
            time.sleep(wait)

    assert last_err is not None
    raise last_err

"""名刺の抽出項目を定義するPydanticスキーマ。

Claude の構造化出力(client.messages.parse)に渡すことで、
モデルの応答が必ずこの形に従うことを保証する。
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# 電話/メール等の先頭に付きやすいラベルを除去するための正規表現
_LABEL_RE = re.compile(
    r"^\s*(?:TEL|Tel|tel|電話|PHONE|Phone|phone|FAX|Fax|fax|"
    r"携帯|MOBILE|Mobile|mobile|Cell|MAIL|Mail|mail|E-?mail|e-?mail|"
    r"メール|URL|Url|url|HP|ＴＥＬ|ＦＡＸ)\s*[:：.]?\s*",
    re.IGNORECASE,
)


class BusinessCard(BaseModel):
    """名刺1枚から抽出するフィールド。

    読み取れなかった項目は None ではなく空文字 "" を返す。
    （スプレッドシートのセルをそのまま空欄にできるようにするため）
    """

    company: str = Field(default="", description="会社名・組織名")
    department: str = Field(default="", description="部署名")
    title: str = Field(default="", description="役職")
    name: str = Field(default="", description="氏名（漢字・英字など名刺記載のまま）")
    name_kana: str = Field(default="", description="氏名のふりがな（カナ）。記載が無ければ空")
    postal_code: str = Field(default="", description="郵便番号（例: 100-0001）")
    address: str = Field(default="", description="住所（都道府県から建物名まで）")
    phone: str = Field(default="", description="固定電話番号")
    mobile: str = Field(default="", description="携帯電話番号")
    fax: str = Field(default="", description="FAX番号")
    email: str = Field(default="", description="メールアドレス")
    website: str = Field(default="", description="WebサイトURL")

    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="全体の読み取り確信度(0.0〜1.0)。文字がかすれる・隠れる等で自信が無い場合は下げる。",
    )
    needs_review: bool = Field(
        default=False,
        description="人による確認が必要なら true。読み取れない項目が多い/確信度が低い場合に true。",
    )
    notes: str = Field(
        default="",
        description="読み取りで迷った点・複数候補があった点などの補足メモ。無ければ空。",
    )

    @field_validator(
        "phone", "mobile", "fax", "email", "website", mode="before"
    )
    @classmethod
    def _strip_labels(cls, v):
        """先頭のラベル(TEL:/Mobile:/Mail: 等)を除去し、前後空白を整える。"""
        if not isinstance(v, str):
            return v
        s = v.strip()
        # ラベルが複数回付くケースに備えて数回適用
        for _ in range(3):
            new = _LABEL_RE.sub("", s)
            if new == s:
                break
            s = new.strip()
        return s

    @field_validator("postal_code", mode="before")
    @classmethod
    def _clean_postal(cls, v):
        """郵便番号から 〒 と余分な空白を除去する。"""
        if not isinstance(v, str):
            return v
        return v.replace("〒", "").replace("〒", "").strip()

    # スプレッドシートの列順（main.py 側で参照）
    @staticmethod
    def sheet_header() -> list[str]:
        return [
            "会社名",
            "部署",
            "役職",
            "氏名",
            "氏名カナ",
            "郵便番号",
            "住所",
            "電話",
            "携帯",
            "FAX",
            "メール",
            "URL",
            "確信度",
            "要確認",
            "備考",
            "ファイル名",
            "処理日時",
        ]

    def to_sheet_row(self, filename: str, processed_at: str) -> list[str]:
        return [
            self.company,
            self.department,
            self.title,
            self.name,
            self.name_kana,
            self.postal_code,
            self.address,
            self.phone,
            self.mobile,
            self.fax,
            self.email,
            self.website,
            f"{self.confidence:.2f}",
            "要確認" if self.needs_review else "",
            self.notes,
            filename,
            processed_at,
        ]

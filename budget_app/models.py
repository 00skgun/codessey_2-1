"""애플리케이션 데이터 모델과 입력 검증."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


class AppError(Exception):
    """사용자에게 원인과 해결 방법을 보여 줄 수 있는 오류."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


def validate_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise AppError(
            f"날짜 형식이 올바르지 않습니다: {value}",
            "YYYY-MM-DD 형식의 실제 날짜를 입력하세요. 예: 2026-07-29",
        ) from exc


def validate_month(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise AppError(
            f"월 형식이 올바르지 않습니다: {value}",
            "YYYY-MM 형식으로 입력하세요. 예: 2026-07",
        ) from exc
    return parsed.strftime("%Y-%m")


def validate_amount(value: Any) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError) as exc:
        raise AppError("금액은 정수여야 합니다.", "예: 15000") from exc
    if amount <= 0:
        raise AppError("금액은 0보다 커야 합니다.", "양수 정수를 입력하세요.")
    return amount


def validate_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"income", "expense"}:
        raise AppError(
            f"허용되지 않은 거래 타입입니다: {value}",
            "income 또는 expense 중 하나를 입력하세요.",
        )
    return normalized


def normalize_tags(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    raw_tags = value if isinstance(value, list) else value.split(",")
    return list(dict.fromkeys(tag.strip() for tag in raw_tags if tag.strip()))


@dataclass(slots=True)
class Transaction:
    id: str
    type: str
    date: str
    amount: int
    category: str
    memo: str = ""
    tags: list[str] | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise AppError("거래 id가 비어 있습니다.")
        self.type = validate_type(self.type)
        self.date = validate_date(self.date)
        self.amount = validate_amount(self.amount)
        self.category = self.category.strip()
        if not self.category:
            raise AppError("카테고리는 비워 둘 수 없습니다.")
        self.memo = self.memo.strip()
        self.tags = normalize_tags(self.tags)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            date=str(data["date"]),
            amount=data["amount"],
            category=str(data["category"]),
            memo=str(data.get("memo", "")),
            tags=data.get("tags", []),
        )


@dataclass(slots=True)
class SearchCriteria:
    date_from: str | None = None
    date_to: str | None = None
    category: str | None = None
    transaction_type: str | None = None
    query: str | None = None
    tag: str | None = None

    def __post_init__(self) -> None:
        if self.date_from:
            self.date_from = validate_date(self.date_from)
        if self.date_to:
            self.date_to = validate_date(self.date_to)
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise AppError(
                "검색 시작일이 종료일보다 늦습니다.",
                "--from 날짜가 --to 날짜보다 빠르거나 같아야 합니다.",
            )
        if self.transaction_type:
            self.transaction_type = validate_type(self.transaction_type)

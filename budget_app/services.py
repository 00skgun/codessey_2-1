"""업무 규칙과 검색·요약·가져오기·내보내기 서비스."""

from __future__ import annotations

import csv
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Iterator

from .models import (
    AppError,
    SearchCriteria,
    Transaction,
    normalize_tags,
    validate_amount,
    validate_date,
    validate_month,
    validate_type,
)
from .repositories import BudgetStore, CategoryStore, TransactionRepository


class BudgetService:
    def __init__(
        self,
        transactions: TransactionRepository,
        categories: CategoryStore,
        budgets: BudgetStore,
    ) -> None:
        self.transactions = transactions
        self.categories = categories
        self.budgets = budgets

    def add_transaction(
        self,
        *,
        date_value: str,
        transaction_type: str,
        category: str,
        amount: int | str,
        memo: str = "",
        tags: str | list[str] | None = None,
    ) -> Transaction:
        self._require_category(category)
        transaction = Transaction(
            id=f"TX-{uuid.uuid4().hex[:12].upper()}",
            type=transaction_type,
            date=date_value,
            amount=validate_amount(amount),
            category=category,
            memo=memo,
            tags=normalize_tags(tags),
        )
        self.transactions.save(transaction)
        return transaction

    def list_transactions(self, limit: int) -> Iterator[Transaction]:
        if limit <= 0:
            raise AppError("--limit은 1 이상이어야 합니다.")
        for index, transaction in enumerate(
            self.transactions.iter_all(newest_first=True)
        ):
            if index >= limit:
                break
            yield transaction

    def search(self, criteria: SearchCriteria) -> Iterator[Transaction]:
        for item in self.transactions.iter_all(newest_first=True):
            if criteria.date_from and item.date < criteria.date_from:
                continue
            if criteria.date_to and item.date > criteria.date_to:
                continue
            if criteria.category and item.category != criteria.category:
                continue
            if (
                criteria.transaction_type
                and item.type != criteria.transaction_type
            ):
                continue
            if criteria.query and criteria.query.casefold() not in item.memo.casefold():
                continue
            if criteria.tag and criteria.tag not in (item.tags or []):
                continue
            yield item

    def update_transaction(
        self, transaction_id: str, changes: dict[str, object]
    ) -> Transaction:
        current = self.transactions.find(transaction_id)
        if current is None:
            raise AppError(
                f"거래를 찾을 수 없습니다: {transaction_id}",
                "list 또는 search 명령으로 id를 확인하세요.",
            )
        data = current.to_dict()
        for key, value in changes.items():
            if value is not None:
                data[key] = value
        if "category" in changes and changes["category"] is not None:
            self._require_category(str(changes["category"]))
        updated = Transaction.from_dict(data)
        self.transactions.replace(updated)
        return updated

    def delete_transaction(self, transaction_id: str) -> None:
        if not self.transactions.delete(transaction_id):
            raise AppError(
                f"거래를 찾을 수 없습니다: {transaction_id}",
                "list 또는 search 명령으로 id를 확인하세요.",
            )

    def monthly_summary(self, month: str, top: int) -> dict[str, object]:
        validated_month = validate_month(month)
        if top <= 0:
            raise AppError("--top은 1 이상이어야 합니다.")
        income = 0
        expense = 0
        count = 0
        by_category: dict[str, int] = defaultdict(int)
        for item in self.transactions.iter_all():
            if item.date.startswith(validated_month):
                count += 1
                if item.type == "income":
                    income += item.amount
                else:
                    expense += item.amount
                    by_category[item.category] += item.amount
        ranking = sorted(by_category.items(), key=lambda pair: (-pair[1], pair[0]))[
            :top
        ]
        budget = self.budgets.get(validated_month)
        return {
            "month": validated_month,
            "count": count,
            "income": income,
            "expense": expense,
            "balance": income - expense,
            "ranking": ranking,
            "budget": budget,
            "usage": (expense / budget * 100) if budget else None,
            "over": budget is not None and expense > budget,
        }

    def set_budget(self, month: str, amount: int | str) -> tuple[str, int]:
        validated_month = validate_month(month)
        validated_amount = validate_amount(amount)
        self.budgets.set(validated_month, validated_amount)
        return validated_month, validated_amount

    def add_category(self, name: str) -> bool:
        return self.categories.add(name)

    def remove_category(self, name: str) -> bool:
        if self.transactions.contains_category(name):
            raise AppError(
                f"사용 중인 카테고리는 삭제할 수 없습니다: {name}",
                "해당 거래를 다른 카테고리로 수정한 뒤 다시 시도하세요.",
            )
        return self.categories.remove(name)

    def import_csv(self, source: Path) -> tuple[int, int]:
        if not source.is_file():
            raise AppError(
                f"가져올 파일이 없습니다: {source}",
                "--from 경로를 확인하세요.",
            )
        imported = 0
        skipped = 0
        required = {"date", "type", "category", "amount"}
        with source.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise AppError(
                    "CSV 필수 헤더가 누락되었습니다.",
                    "date,type,category,amount 헤더를 포함하세요.",
                )
            for row in reader:
                try:
                    self.add_transaction(
                        date_value=row["date"],
                        transaction_type=row["type"],
                        category=row["category"],
                        amount=row["amount"],
                        memo=row.get("memo", ""),
                        tags=row.get("tags", ""),
                    )
                    imported += 1
                except AppError:
                    skipped += 1
        return imported, skipped

    def export_csv(
        self, output: Path, criteria: SearchCriteria, month: str | None
    ) -> int:
        if month:
            validated_month = validate_month(month)
            criteria.date_from = f"{validated_month}-01"
            year, month_number = map(int, validated_month.split("-"))
            next_month = month_number % 12 + 1
            next_year = year + (1 if month_number == 12 else 0)
            from datetime import date, timedelta

            criteria.date_to = (
                date(next_year, next_month, 1) - timedelta(days=1)
            ).isoformat()
        output.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with output.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["date", "type", "category", "amount", "memo", "tags"],
            )
            writer.writeheader()
            for item in self.search(criteria):
                writer.writerow(
                    {
                        "date": item.date,
                        "type": item.type,
                        "category": item.category,
                        "amount": item.amount,
                        "memo": item.memo,
                        "tags": ",".join(item.tags or []),
                    }
                )
                count += 1
        return count

    def _require_category(self, name: str) -> None:
        if not self.categories.exists(name):
            raise AppError(
                f"등록되지 않은 카테고리입니다: {name}",
                f"category add {name} 명령으로 먼저 등록하세요.",
            )

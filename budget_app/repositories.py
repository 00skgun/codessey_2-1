"""JSONL 영구 저장소. 읽기는 제너레이터, 쓰기는 원자적 교체를 사용한다."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from .models import AppError, Transaction


def _iter_lines_reverse(path: Path, chunk_size: int = 8192) -> Iterator[str]:
    """파일을 메모리에 한꺼번에 올리지 않고 마지막 줄부터 읽는다."""
    with path.open("rb") as file:
        file.seek(0, os.SEEK_END)
        position = file.tell()
        remainder = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            file.seek(position)
            block = file.read(read_size) + remainder
            lines = block.split(b"\n")
            remainder = lines[0]
            for line in reversed(lines[1:]):
                if line.strip():
                    yield line.decode("utf-8")
        if remainder.strip():
            yield remainder.decode("utf-8")


def _iter_lines_forward(path: Path) -> Iterator[str]:
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                yield line


def _atomic_write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


class TransactionRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def iter_all(self, newest_first: bool = False) -> Iterator[Transaction]:
        """한 줄씩 yield한다. 파일은 날짜 오름차순으로 유지된다."""
        if newest_first:
            line_iterator = _iter_lines_reverse(self.path)
        else:
            line_iterator = _iter_lines_forward(self.path)
        try:
            for line in line_iterator:
                try:
                    yield Transaction.from_dict(json.loads(line))
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise AppError(
                        f"저장 파일에 손상된 거래 데이터가 있습니다: {self.path}",
                        "문제가 있는 JSONL 행을 수정하거나 백업에서 복구하세요.",
                    ) from exc
        finally:
            close = getattr(line_iterator, "close", None)
            if close:
                close()

    def find(self, transaction_id: str) -> Transaction | None:
        return next(
            (item for item in self.iter_all() if item.id == transaction_id), None
        )

    def save(self, transaction: Transaction) -> None:
        items = list(self.iter_all())
        items.append(transaction)
        self._rewrite(items)

    def replace(self, transaction: Transaction) -> bool:
        found = False
        items: list[Transaction] = []
        for item in self.iter_all():
            if item.id == transaction.id:
                items.append(transaction)
                found = True
            else:
                items.append(item)
        if found:
            self._rewrite(items)
        return found

    def delete(self, transaction_id: str) -> bool:
        found = False
        items: list[Transaction] = []
        for item in self.iter_all():
            if item.id == transaction_id:
                found = True
            else:
                items.append(item)
        if found:
            self._rewrite(items)
        return found

    def contains_category(self, category: str) -> bool:
        return any(item.category == category for item in self.iter_all())

    def _rewrite(self, items: Sequence[Transaction]) -> None:
        ordered = sorted(items, key=lambda item: (item.date, item.id))
        _atomic_write_jsonl(self.path, [item.to_dict() for item in ordered])


class CategoryStore:
    DEFAULTS = ("food", "transport", "housing", "salary", "etc")

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            _atomic_write_jsonl(
                self.path, [{"name": category} for category in self.DEFAULTS]
            )

    def list(self) -> list[str]:
        categories: list[str] = []
        try:
            with self.path.open("r", encoding="utf-8") as file:
                for line in file:
                    if line.strip():
                        categories.append(str(json.loads(line)["name"]))
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AppError(
                f"카테고리 파일이 손상되었습니다: {self.path}",
                "JSONL 형식을 확인하세요.",
            ) from exc
        return sorted(set(categories))

    def exists(self, name: str) -> bool:
        return name in self.list()

    def add(self, name: str) -> bool:
        normalized = name.strip()
        if not normalized:
            raise AppError("카테고리 이름은 비워 둘 수 없습니다.")
        categories = self.list()
        if normalized in categories:
            return False
        categories.append(normalized)
        _atomic_write_jsonl(self.path, [{"name": item} for item in sorted(categories)])
        return True

    def remove(self, name: str) -> bool:
        categories = self.list()
        if name not in categories:
            return False
        categories.remove(name)
        _atomic_write_jsonl(self.path, [{"name": item} for item in categories])
        return True


class BudgetStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _read(self) -> dict[str, int]:
        budgets: dict[str, int] = {}
        try:
            with self.path.open("r", encoding="utf-8") as file:
                for line in file:
                    if line.strip():
                        row = json.loads(line)
                        budgets[str(row["month"])] = int(row["amount"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AppError(
                f"예산 파일이 손상되었습니다: {self.path}",
                "JSONL 형식을 확인하세요.",
            ) from exc
        return budgets

    def set(self, month: str, amount: int) -> None:
        budgets = self._read()
        budgets[month] = amount
        _atomic_write_jsonl(
            self.path,
            [
                {"month": key, "amount": budgets[key]}
                for key in sorted(budgets.keys())
            ],
        )

    def get(self, month: str) -> int | None:
        return self._read().get(month)

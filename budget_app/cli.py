"""argparse 기반 명령행 인터페이스."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Callable, Sequence, TypeVar

from .decorators import log_execution
from .models import (
    AppError,
    SearchCriteria,
    validate_amount,
    validate_date,
    validate_type,
)
from .repositories import BudgetStore, CategoryStore, TransactionRepository
from .services import BudgetService

T = TypeVar("T")


class FriendlyArgumentParser(argparse.ArgumentParser):
    """명령 문법 오류를 과제 형식의 오류와 힌트로 출력한다."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(
            f"[오류] 명령어 또는 옵션이 올바르지 않습니다: {message}",
            file=sys.stderr,
        )
        print(
            "[힌트] 명령에는 하이픈을 붙이지 않습니다. "
            "예: python -m budget_app add",
            file=sys.stderr,
        )
        print(
            "[힌트] 전체 사용법: python -m budget_app --help",
            file=sys.stderr,
        )
        self.exit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = FriendlyArgumentParser(
        prog="python -m budget_app",
        description="JSONL 파일 기반 용돈 기입장",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="저장 폴더 (기본값: ./data, 하위 명령보다 앞에 지정)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("add", help="대화형으로 거래 추가")

    list_parser = sub.add_parser("list", help="최신순 거래 목록")
    list_parser.add_argument("--limit", type=int, default=10)

    search = sub.add_parser("search", help="조건별 거래 검색")
    add_search_arguments(search)

    summary = sub.add_parser("summary", help="월별 요약")
    summary.add_argument("--month", required=True)
    summary.add_argument("--top", type=int, default=3)

    budget = sub.add_parser("budget", help="월 예산 관리")
    budget_sub = budget.add_subparsers(dest="budget_command", required=True)
    budget_set = budget_sub.add_parser("set", help="예산 설정")
    budget_set.add_argument("--month", required=True)
    budget_set.add_argument("--amount", required=True, type=int)
    budget_get = budget_sub.add_parser("get", help="예산 조회")
    budget_get.add_argument("--month", required=True)

    category = sub.add_parser("category", help="카테고리 관리")
    category_sub = category.add_subparsers(dest="category_command", required=True)
    category_add = category_sub.add_parser("add", help="카테고리 추가")
    category_add.add_argument("name", nargs="?")
    category_sub.add_parser("list", help="카테고리 목록")
    category_remove = category_sub.add_parser("remove", help="카테고리 삭제")
    category_remove.add_argument("name")

    update = sub.add_parser("update", help="옵션 기반 거래 수정")
    update.add_argument("--id", required=True)
    update.add_argument("--date")
    update.add_argument("--type", dest="transaction_type")
    update.add_argument("--category")
    update.add_argument("--amount", type=int)
    update.add_argument("--memo")
    update.add_argument("--tags")

    delete = sub.add_parser("delete", help="거래 삭제")
    delete.add_argument("--id", required=True)

    importer = sub.add_parser("import", help="CSV 거래 가져오기")
    importer.add_argument("--from", dest="source", required=True, type=Path)

    exporter = sub.add_parser("export", help="CSV 거래 내보내기")
    exporter.add_argument("--out", required=True, type=Path)
    exporter.add_argument("--month")
    exporter.add_argument("--from", dest="date_from")
    exporter.add_argument("--to", dest="date_to")

    return parser


def add_search_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="date_from")
    parser.add_argument("--to", dest="date_to")
    parser.add_argument("--category")
    parser.add_argument("--type", dest="transaction_type")
    parser.add_argument("--q")
    parser.add_argument("--tag")


def make_service(data_dir: Path) -> BudgetService:
    return BudgetService(
        TransactionRepository(data_dir / "transactions.jsonl"),
        CategoryStore(data_dir / "categories.jsonl"),
        BudgetStore(data_dir / "budgets.jsonl"),
    )


def format_transaction(item: object) -> str:
    transaction = item
    tags = ",".join(transaction.tags or [])
    return (
        f"{transaction.id} | {transaction.date} | {transaction.type:<7} | "
        f"{transaction.category:<12} | {transaction.amount:>10,}원 | "
        f"{transaction.memo} | {tags}"
    )


def prompt_validated(prompt: str, validator: Callable[[str], T]) -> T:
    """대화형 입력이 유효할 때까지 오류와 힌트를 출력하며 다시 묻는다."""
    while True:
        try:
            return validator(input(prompt).strip())
        except AppError as exc:
            print(f"[오류] {exc.message}", file=sys.stderr)
            if exc.hint:
                print(f"[힌트] {exc.hint}", file=sys.stderr)
            print("[안내] 다시 입력해 주세요.", file=sys.stderr)
        except EOFError as exc:
            raise AppError(
                "입력이 끝나 거래 추가를 완료할 수 없습니다.",
                "대화형 터미널에서 다시 실행하세요.",
            ) from exc


def prompt_text(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError as exc:
        raise AppError(
            "입력이 끝나 거래 추가를 완료할 수 없습니다.",
            "대화형 터미널에서 다시 실행하세요.",
        ) from exc


def validate_category_input(service: BudgetService, value: str) -> str:
    if not service.categories.exists(value):
        raise AppError(
            f"등록되지 않은 카테고리입니다: {value}",
            "category list로 목록을 확인하거나 category add로 먼저 등록하세요.",
        )
    return value


@log_execution
def dispatch(args: argparse.Namespace, service: BudgetService) -> None:
    command = args.command
    if command == "add":
        item = service.add_transaction(
            date_value=prompt_validated(
                "날짜 (YYYY-MM-DD): ", validate_date
            ),
            transaction_type=prompt_validated(
                "타입 (income/expense): ", validate_type
            ),
            category=prompt_validated(
                "카테고리: ",
                lambda value: validate_category_input(service, value),
            ),
            amount=prompt_validated("금액 (양수 정수): ", validate_amount),
            memo=prompt_text("메모 (선택): "),
            tags=prompt_text("태그 (쉼표 구분, 선택): "),
        )
        print(f"[저장 완료] id={item.id}")
    elif command == "list":
        print_items(service.list_transactions(args.limit))
    elif command == "search":
        print_items(service.search(criteria_from_args(args)))
    elif command == "summary":
        print_summary(service.monthly_summary(args.month, args.top), args.top)
    elif command == "budget":
        if args.budget_command == "set":
            month, amount = service.set_budget(args.month, args.amount)
            print(f"[저장 완료] {month} 예산 {amount:,}원")
        else:
            summary = service.monthly_summary(args.month, 1)
            budget = summary["budget"]
            print(
                f"{summary['month']} 예산: "
                + (f"{budget:,}원" if budget is not None else "설정되지 않음")
            )
    elif command == "category":
        if args.category_command == "list":
            for category in service.categories.list():
                print(f"- {category}")
        elif args.category_command == "add":
            name = args.name or input("카테고리명: ").strip()
            created = service.add_category(name)
            print(
                f"[저장 완료] category={name}"
                if created
                else f"[안내] 이미 존재하는 카테고리입니다: {name}"
            )
        else:
            removed = service.remove_category(args.name)
            print(
                f"[삭제 완료] category={args.name}"
                if removed
                else f"[안내] 없는 카테고리입니다: {args.name}"
            )
    elif command == "update":
        changes = {
            "date": args.date,
            "type": args.transaction_type,
            "category": args.category,
            "amount": args.amount,
            "memo": args.memo,
            "tags": args.tags,
        }
        if not any(value is not None for value in changes.values()):
            raise AppError(
                "수정할 항목이 없습니다.",
                "--date, --type, --category, --amount, --memo, --tags 중 하나를 지정하세요.",
            )
        updated = service.update_transaction(args.id, changes)
        print(f"[수정 완료] id={updated.id}")
    elif command == "delete":
        service.delete_transaction(args.id)
        print(f"[삭제 완료] id={args.id}")
    elif command == "import":
        imported, skipped = service.import_csv(args.source)
        print(f"[완료] imported={imported}, skipped={skipped}")
    elif command == "export":
        if not args.month and not (args.date_from and args.date_to):
            raise AppError(
                "내보내기 검색 조건이 없습니다.",
                "--month 또는 --from과 --to를 함께 지정하세요.",
            )
        count = service.export_csv(
            args.out,
            SearchCriteria(date_from=args.date_from, date_to=args.date_to),
            args.month,
        )
        print(f"[완료] {args.out} ({count} records)")


def criteria_from_args(args: argparse.Namespace) -> SearchCriteria:
    return SearchCriteria(
        date_from=args.date_from,
        date_to=args.date_to,
        category=args.category,
        transaction_type=args.transaction_type,
        query=args.q,
        tag=args.tag,
    )


def print_items(items: object) -> None:
    count = 0
    for item in items:
        print(format_transaction(item))
        count += 1
    if count == 0:
        print("[안내] 조건에 맞는 데이터가 없습니다.")


def print_summary(summary: dict[str, object], top: int) -> None:
    if summary["count"] == 0:
        print(f"[안내] {summary['month']} 데이터 없음")
    print(f"총 수입: {summary['income']:,}원")
    print(f"총 지출: {summary['expense']:,}원")
    print(f"잔액: {summary['balance']:,}원")
    budget = summary["budget"]
    if budget is not None:
        print(f"예산: {budget:,}원 (사용률 {summary['usage']:.1f}%)")
        if summary["over"]:
            print("[경고] 월 예산을 초과했습니다!")
    print(f"지출 TOP {top}")
    ranking = summary["ranking"]
    if not ranking:
        print("- 지출 데이터 없음")
    for index, (category, amount) in enumerate(ranking, 1):
        print(f"{index}) {category}: {amount:,}원")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.data_dir = Path(args.data_dir)
    try:
        dispatch(args, make_service(args.data_dir))
    except AppError as exc:
        print(f"[오류] {exc.message}", file=sys.stderr)
        if exc.hint:
            print(f"[힌트] {exc.hint}", file=sys.stderr)
        return 2
    except (OSError, csv.Error) as exc:
        print(f"[오류] 파일 처리에 실패했습니다: {exc}", file=sys.stderr)
        print("[힌트] 경로와 파일 접근 권한을 확인하세요.", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\n[안내] 사용자 요청으로 취소했습니다.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"[오류] 예상하지 못한 문제가 발생했습니다: {exc}", file=sys.stderr)
        print(
            "[힌트] 입력과 data 폴더의 파일 형식을 확인한 뒤 다시 시도하세요.",
            file=sys.stderr,
        )
        return 1
    return 0

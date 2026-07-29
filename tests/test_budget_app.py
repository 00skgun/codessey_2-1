from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from budget_app.models import AppError, SearchCriteria
from budget_app.repositories import BudgetStore, CategoryStore, TransactionRepository
from budget_app.services import BudgetService


class BudgetServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data_dir = Path.cwd() / f".test-data-{uuid.uuid4().hex}"
        self.data_dir.mkdir()
        self.service = BudgetService(
            TransactionRepository(self.data_dir / "transactions.jsonl"),
            CategoryStore(self.data_dir / "categories.jsonl"),
            BudgetStore(self.data_dir / "budgets.jsonl"),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def add_sample(self, date_value: str = "2026-07-10", amount: int = 15000):
        return self.service.add_transaction(
            date_value=date_value,
            transaction_type="expense",
            category="food",
            amount=amount,
            memo="점심",
            tags="meal,work",
        )

    def test_initializes_three_storage_files(self) -> None:
        self.assertTrue((self.data_dir / "transactions.jsonl").exists())
        self.assertTrue((self.data_dir / "categories.jsonl").exists())
        self.assertTrue((self.data_dir / "budgets.jsonl").exists())

    def test_add_list_search_update_delete(self) -> None:
        old = self.add_sample("2026-07-01", 1000)
        newest = self.add_sample("2026-07-20", 2000)
        self.assertEqual(
            [item.id for item in self.service.list_transactions(2)],
            [newest.id, old.id],
        )
        result = list(
            self.service.search(SearchCriteria(query="점심", tag="work"))
        )
        self.assertEqual(len(result), 2)

        updated = self.service.update_transaction(
            old.id, {"amount": 3000, "memo": "수정"}
        )
        self.assertEqual(updated.amount, 3000)
        self.service.delete_transaction(newest.id)
        self.assertIsNone(self.service.transactions.find(newest.id))

    def test_summary_and_budget_warning(self) -> None:
        self.add_sample(amount=15000)
        self.service.set_budget("2026-07", 10000)
        summary = self.service.monthly_summary("2026-07", 3)
        self.assertEqual(summary["expense"], 15000)
        self.assertEqual(summary["usage"], 150.0)
        self.assertTrue(summary["over"])

    def test_category_in_use_cannot_be_removed(self) -> None:
        self.add_sample()
        with self.assertRaises(AppError):
            self.service.remove_category("food")

    def test_invalid_input_is_rejected(self) -> None:
        with self.assertRaises(AppError):
            self.service.add_transaction(
                date_value="2026-13-40",
                transaction_type="expense",
                category="food",
                amount=-1,
            )

    def test_import_export_csv(self) -> None:
        source = self.data_dir / "input.csv"
        with source.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["date", "type", "category", "amount", "memo", "tags"])
            writer.writerow(["2026-07-03", "expense", "food", "12000", "저녁", "meal"])
            writer.writerow(["bad-date", "expense", "food", "1", "", ""])
        imported, skipped = self.service.import_csv(source)
        self.assertEqual((imported, skipped), (1, 1))

        output = self.data_dir / "output.csv"
        count = self.service.export_csv(
            output, SearchCriteria(), month="2026-07"
        )
        self.assertEqual(count, 1)
        with output.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(rows[0]["memo"], "저녁")

    def test_jsonl_is_sorted_and_readable(self) -> None:
        self.add_sample("2026-07-20", 2000)
        self.add_sample("2026-07-01", 1000)
        lines = (self.data_dir / "transactions.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        dates = [json.loads(line)["date"] for line in lines]
        self.assertEqual(dates, sorted(dates))


class CliTest(unittest.TestCase):
    def test_error_has_nonzero_exit_code_without_traceback(self) -> None:
        temp = Path.cwd() / f".test-cli-{uuid.uuid4().hex}"
        temp.mkdir()
        try:
            environment = os.environ.copy()
            environment["PYTHONUTF8"] = "1"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "budget_app",
                    "--data-dir",
                    str(temp),
                    "delete",
                    "--id",
                    "NO-ID",
                ],
                text=True,
                capture_output=True,
                encoding="utf-8",
                env=environment,
                check=False,
            )
        finally:
            shutil.rmtree(temp, ignore_errors=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[오류]", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()

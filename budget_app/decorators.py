"""CLI 공통 관심사를 분리하는 데코레이터."""

from __future__ import annotations

import functools
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def log_execution(
    function: Callable[P, R],
) -> Callable[P, R]:
    """실행 성공/실패와 실행 시간을 app.log에 기록한다."""

    @functools.wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        started = time.perf_counter()
        status = "SUCCESS"
        try:
            return function(*args, **kwargs)
        except Exception:
            status = "ERROR"
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            data_dir = Path(getattr(args[0], "data_dir", "data")) if args else Path("data")
            data_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().isoformat(timespec="seconds")
            with (data_dir / "app.log").open("a", encoding="utf-8") as file:
                file.write(
                    f"{timestamp}\t{function.__name__}\t{status}\t{elapsed_ms:.2f}ms\n"
                )

    return wrapper

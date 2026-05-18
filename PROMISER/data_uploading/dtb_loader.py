"""
Загрузка помесячного DTB из логкатового Excel-файла (`logcats_DTB_2025.xlsx`).

В файле — daily DTB по каждому отдельному логкату за весь 2025 год
(колонки = логкаты, строки = даты, первый столбец `date`). Здесь мы:

  * агрегируем daily → monthly суммированием;
  * для запрошенного «комбо-разреза» (несколько логкатов через запятую)
    суммируем колонки и возвращаем единый dict {month: dtb}.

Tonkost: некоторые логкаты появились не с начала года (например
`Gigs.Retail` — с конца февраля, `Services.TransportationAndDelivery`
содержит лишь несколько ненулевых дней). Sum просто суммирует то, что
есть, нули остаются нулями — пайплайн от этого не ломается, но месяцы
без данных будут давать заниженный/нулевой base_dtb для разрезов,
сильно завязанных на эти логкаты. Это ожидаемое поведение, MILP-
оптимизатор сам отбросит заведомо невыгодные сочетания.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from PROMISER.configurations import config


def _split_logcats(key: str | list[str] | tuple[str, ...] | set[str]) -> list[str]:
    """'A, B,C' либо ['A','B'] → ['A', 'B', 'C']."""
    if isinstance(key, (list, tuple, set)):
        return [str(s).strip() for s in key if str(s).strip()]
    return [s.strip() for s in str(key).split(",") if s.strip()]


@lru_cache(maxsize=4)
def load_monthly_dtb_table(path: str | None = None) -> pd.DataFrame:
    """Возвращает DataFrame с месячной суммой DTB по каждому логкату.

    Index = month (1..12), columns = logcat. Значения int.
    Кэшируется (lru_cache) — Excel читается один раз за процесс.
    """
    p = Path(path) if path else config.DTB_EXCEL_PATH
    df = pd.read_excel(p)
    if "date" not in df.columns:
        raise ValueError(f"В {p} нет колонки `date`")
    df["date"] = pd.to_datetime(df["date"])
    df["_month"] = df["date"].dt.month
    monthly = (
        df.drop(columns=["date"])
        .groupby("_month")
        .sum()
        .astype("int64")
        .sort_index()
    )
    monthly.index.name = "month"
    return monthly


def build_per_logcat_dtb_dict(
    monthly: pd.DataFrame | None = None,
) -> dict[str, dict[int, int]]:
    """{logcat: {month: dtb}} по каждому индивидуальному логкату из Excel.

    Удобно для отладки и точечных лукапов. Для комбо-ключей лучше
    использовать `dtb_for_logcats(...)` — он суммирует ровно то, что
    запрошено.
    """
    monthly = load_monthly_dtb_table() if monthly is None else monthly
    return {
        col: {int(m): int(monthly.at[m, col]) for m in monthly.index}
        for col in monthly.columns
    }


def dtb_for_logcats(
    logcats: str | list[str],
    monthly: pd.DataFrame | None = None,
) -> dict[int, int]:
    """Сумма помесячного DTB по списку логкатов.

    Если какого-то логката в файле нет (опечатка / ещё не учтён) —
    предупреждаем print'ом и пропускаем его (как нулевой). Возвращаем
    {1..12: int}.
    """
    monthly = load_monthly_dtb_table() if monthly is None else monthly
    parts = _split_logcats(logcats)
    if not parts:
        raise ValueError(f"Пустой ключ logcats: {logcats!r}")

    missing = [p for p in parts if p not in monthly.columns]
    if missing:
        print(
            f"[dtb_loader] WARN: в Excel нет логкатов {missing} "
            f"(они будут считаться нулевыми)."
        )
    cols = [p for p in parts if p in monthly.columns]
    if not cols:
        raise KeyError(
            f"Ни один из логкатов {parts} не найден в DTB-Excel "
            f"({list(monthly.columns)[:3]}...)"
        )
    summed = monthly[cols].sum(axis=1).astype("int64")
    return {int(m): int(summed.at[m]) for m in summed.index}

"""
Загрузка исторических данных и кривых TRP→Reach из Google Sheets.

Никакой математики и предсказаний — только парсинг + типизация.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from PROMISER.configurations import config
from PROMISER.data_uploading.table_parser import GoogleSheetsParser


# ---------------------------------------------------------------------------
# Историческая таблица флайтов
# ---------------------------------------------------------------------------
def load_history_df(parser: GoogleSheetsParser) -> pd.DataFrame:
    """Возвращает таблицу с фактом по историческим РК.

    Слитая таблица из двух листов:
      * `data Nat TV` (TRP / SOV / бюджет факт) — config.CAMPAIGNS_SHEET_ID
      * `results`     (метрики, OPM, consideration и т.д.) — config.METRICS_SHEET_ID

    Колонки приведены к числу там, где это нужно для предсказателя:
      flight, TRP, SOV, budget actual Net,
      base_dtb, metric_uplift, metric_mde, cross_effect,
      metric_abs_analytics, mde_abs, OPM, consideration, vertical, ...
    """
    df_campaigns = parser.read_sheet(config.CAMPAIGNS_SHEET_ID, "data Nat TV")
    df_metrics = parser.read_sheet(config.METRICS_SHEET_ID, "results")

    # Колонки факта: SOV в долях (входит как "12.3%"), TRP — сетка по 250.
    df_campaigns["SOV\nAll 18-54"] = df_campaigns["SOV\nAll 18-54"].apply(
        lambda x: float(x[:-1]) / 100
    )
    df_campaigns["TRPs TA actual"] = df_campaigns["TRPs TA actual"].apply(
        lambda x: (int(x.replace("\xa0", "")) // 250) * 250
    )
    df_campaigns = df_campaigns[
        ["Campaign", "TRPs TA actual", "SOV\nAll 18-54", "budget actual, Net"]
    ]
    df_campaigns.columns = ["flight", "TRP", "SOV", "budget actual, Net"]

    df = df_campaigns.merge(df_metrics, on="flight", how="inner", suffixes=("", "_drop"))
    df = df[[c for c in df.columns if not c.endswith("_drop")]]

    for col in ("base_dtb", "metric_uplift", "metric_mde", "cross_effect"):
        df[col] = pd.to_numeric(df[col].replace(",", ".", regex=True), errors="coerce")

    df["budget actual, Net"] = (
        df["budget actual, Net"]
        .astype(str)
        .str.replace("\xa0", "", regex=False)
        .str.replace(" ", "")
        .str.replace(",", ".")
        .astype(float)
    )

    df["metric_abs_analytics"] = df["base_dtb"] * df["metric_uplift"]
    df["mde_abs"] = df["base_dtb"] * (df["metric_mde"] * 0.01)
    return df


# ---------------------------------------------------------------------------
# Кривые TRP→Reach по каждому флайту
# ---------------------------------------------------------------------------
def load_reach_curves(
    parser: GoogleSheetsParser,
    flights: list[str],
    sheet_id: str = config.CAMPAIGNS_SHEET_ID,
) -> dict[str, pd.DataFrame]:
    """Для каждого флайта читает отдельный лист (имя == flight) с кривой TRP→Reach.

    Лист устроен так: первый столбец — TRP, остальные — охваты "n+" (например
    `1+`, `2+`, ...). Возвращает словарь flight → DataFrame, проиндексированный
    по TRP, с колонками-числами (1, 2, 3, ...).
    """
    curves: dict[str, pd.DataFrame] = {}
    for flight in flights:
        raw = parser.read_sheet(sheet_id, flight)
        if raw.empty or len(raw.columns) == 0:
            raise RuntimeError(f"Лист с кривой пуст для flight {flight!r}")

        raw = raw.copy()
        raw.columns = ["TRP"] + raw.columns[1:].tolist()

        raw["TRP"] = raw["TRP"].replace(",", ".", regex=True)
        raw["TRP"] = pd.to_numeric(raw["TRP"], errors="coerce")
        raw = raw.dropna(subset=["TRP"])
        raw["TRP"] = raw["TRP"].astype(int)

        for col in raw.columns[1:]:
            raw[col] = raw[col].replace(",", ".", regex=True).astype(float)

        # "1+", "2+" → 1, 2
        new_cols = ["TRP"] + [int(c[:-1]) for c in raw.columns[1:]]
        raw.columns = new_cols
        raw = raw.set_index("TRP", drop=False)
        curves[flight] = raw
    return curves


# ---------------------------------------------------------------------------
# Кривая "охват → запомнившие"
# ---------------------------------------------------------------------------
def load_seen_curve(question: str, path: Path = config.SEEN_CURVES_PATH) -> np.ndarray:
    """Возвращает массив seen_metric для конкретного вопроса анкеты."""
    with open(path, "rb") as f:
        curves = pickle.load(f)
    if question not in curves:
        raise KeyError(
            f"Вопрос {question!r} не найден в {path}. Доступно: {list(curves)}"
        )
    return curves[question]

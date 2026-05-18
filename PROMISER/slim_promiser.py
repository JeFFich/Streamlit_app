"""
Slim promiser — урезанный вариант предсказателя для **новых кастомных
разрезов без истории флайтов**.

Задача
------
Готовит lookup-словарь в том же формате, что и
`promiser_for_matrexa.MatrixBuilder.build(...)`, но без шага калибровки
по фактическим флайтам — вместо этого пользователь явно передаёт
ROMI на якорной точке (min_TRP, min_SOV) для каждого разреза.

Входные данные
--------------
Список / DataFrame / list[dict] записей `CustomCutInput`:

    [
        {
            "name":     "MyCustomCut",          # человекочитаемое имя
            "logcats":  ["Goods.Furniture",     # список логкатов разреза
                         "Goods.HomeAndGarden"],
            "min_TRP":  1500,                   # якорная TRP (целое)
            "min_SOV":  0.25,                   # якорный SOV (доля 0..1)
            "ROMI":     0.8,                    # известный ROMI в этой точке
        },
        ...
    ]

Выход
-----
`dict[str, pd.DataFrame]` с ключами вида `"{name}_{month}"` и колонками
`MATRIX_COLUMNS` (TRP, DTB_pred, SOV, budget, revenue, ROMI, logcats,
category, low, high) — пригодно к pickle.dump и подаче в матрехин
оптимизатор как нулевой шаг.

Кратко: **как использовать**
----------------------------
    from promiser_clean_v2 import SlimPromiser, slim_build_and_save

    inputs = [
        {"name": "Mebel-Stroy", "logcats": ["Goods.Furniture", "Goods.ConstructionRenovation"],
         "min_TRP": 1500, "min_SOV": 0.25, "ROMI": 0.7},
        {"name": "Cargo",       "logcats": ["Services.TransportationAndDelivery", "Gigs.Retail"],
         "min_TRP": 2000, "min_SOV": 0.3,  "ROMI": 0.5},
    ]

    # Самый короткий путь — сразу в pickle:
    slim_build_and_save(inputs, output_path="custom_cuts.pkl")

    # Или вручную, если хочется приклеить к матрехиному пайплайну:
    promiser = SlimPromiser()
    custom_matrix = promiser.build(inputs)            # dict[name_month -> DataFrame]
    matrix.update(custom_matrix)                      # вливаем в общий lookup

Что под капотом
---------------
* Кривую охвата для нового разреза наследуем от **первого** reference-
  флайта той вертикали, к которой относится первый логкат разреза
  (см. `references.VERTICAL_REFERENCE_FLIGHTS`). Gigs.* отнесены к
  Vacancies&Gigs (вертикаль Jobs).
* Формы DTB_pred(TRP) считаются как нормированный профиль
  predicted_metric_at_trp по этой кривой; масштаб подбирается так,
  чтобы revenue(min_TRP) / budget(min_TRP) − 1 == ROMI.
* DTB-Excel и lookup-фоллбэки используются автоматически: SOV/TRP-cost
  падают на 'Default' если для разреза нет специфичных данных, value
  берётся по вертикали с YoY²-поправкой, CE — тоже по вертикали.
* CI (`low`/`high`) — placeholder ±20% от `DTB_pred`. Slim-вариант
  не имеет MDE; точные доверительные интервалы требовали бы хотя бы
  одного флайта-калибровки (тогда — обычный матрехин промисер).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import pickle
from pathlib import Path

# Конфиг-файлы
from PROMISER.configurations import config
from PROMISER.configurations.references import VERTICAL_REFERENCE_FLIGHTS
from PROMISER.configurations.dictionaries import (
    CE_dict,
    dtb_value_yoy_dict,
    trp_cost_dict,
    value_dict,
)

# Аполудеры
from PROMISER.data_uploading import lookups
from PROMISER.data_uploading.data_loader import load_reach_curves, load_seen_curve
from PROMISER.data_uploading.table_parser import GoogleSheetsParser

# Базовый промисер
from PROMISER.promiser_for_matrexa import MATRIX_COLUMNS, MatrixBuilder, _logcat_set


# ---------------------------------------------------------------------------
# Структура входа
# ---------------------------------------------------------------------------
@dataclass
class CustomCutInput:
    name: str
    logcats: list[str]
    min_TRP: int
    min_SOV: float
    ROMI: float

    @classmethod
    def coerce(cls, item) -> "CustomCutInput":
        """Принимает dict / dataclass / pd.Series и нормализует."""
        if isinstance(item, cls):
            return item
        if isinstance(item, pd.Series):
            item = item.to_dict()
        if not isinstance(item, dict):
            raise TypeError(f"Не понимаю вход типа {type(item).__name__}: {item!r}")

        logcats = item.get("logcats", item.get("logical_category"))
        if isinstance(logcats, str):
            logcats = [s.strip() for s in logcats.split(",") if s.strip()]
        if not logcats:
            raise ValueError(f"У входа {item.get('name')!r} пустой logcats")

        return cls(
            name=str(item["name"]),
            logcats=list(logcats),
            min_TRP=int(item["min_TRP"]),
            min_SOV=float(item["min_SOV"]),
            ROMI=float(item["ROMI"]),
        )


# ---------------------------------------------------------------------------
# Slim promiser
# ---------------------------------------------------------------------------
class SlimPromiser:
    """Промисер для разрезов, у которых нет ни одного исторического флайта.

    Пользуется тем же reach-engine'ом, что и matrexa-MatrixBuilder, но
    калибруется не на исторический metric_abs, а на пользовательский
    ROMI в якорной точке.
    """

    def __init__(
        self,
        parser: GoogleSheetsParser | None = None,
        question: str = config.DEFAULT_QUESTION,
        long_term_effect: float = config.LONG_TERM_EFFECT,
        ci_band: float = 0.20,
    ) -> None:
        self._parser = parser
        self.question = question
        self.long_term_effect = long_term_effect
        self.ci_band = ci_band

        # Заведём «инструментальный» MatrixBuilder с пустым data_to_predict,
        # чтобы переиспользовать его _apply_sov_trp_geometry / _predict_metric_at_trp.
        empty_input = pd.DataFrame(
            columns=["flight", "category", "logical_category", "vertical", "date_start"]
        )
        empty_input["date_start"] = pd.to_datetime(empty_input["date_start"])
        self._builder = MatrixBuilder(
            data_to_predict=empty_input, parser=parser, long_term_effect=long_term_effect
        )

        self._reach_loaded = False

    # ---- инициализация: только нужные кривые охвата --------------------
    @property
    def parser(self) -> GoogleSheetsParser:
        if self._parser is None:
            self._parser = GoogleSheetsParser(
                token_path=config.TOKEN_PATH,
                credentials_path=config.CREDENTIALS_PATH,
            )
            self._builder._parser = self._parser
        return self._parser

    def _ensure_reach(self, needed_flights: Iterable[str]) -> None:
        """Догружает в self._builder.reach_curves все нужные reference-флайты."""
        missing = [f for f in needed_flights if f not in self._builder.reach_curves]
        if missing:
            curves = load_reach_curves(self.parser, missing)
            self._builder.reach_curves.update(curves)
        if self._builder.seen_curve is None:
            self._builder.seen_curve = load_seen_curve(self.question)
        self._reach_loaded = True

    # ---- выбор reference-флайта ---------------------------------------
    @staticmethod
    def _reference_flight(logcats: Sequence[str]) -> str:
        """Берём вертикаль первого логката и из неё первый reference-флайт.

        Можно усложнить (по дате старта, по самому свежему); сейчас намеренно
        проще — slim-вариант наследует одну стабильную кривую.
        """
        vertical = lookups.vertical_for(",".join(logcats))
        candidates = VERTICAL_REFERENCE_FLIGHTS.get(vertical)
        if not candidates:
            raise KeyError(f"В VERTICAL_REFERENCE_FLIGHTS нет вертикали {vertical!r}")
        return candidates[0]

    @staticmethod
    def _vertical_for_geometry(logcats: Sequence[str]) -> str:
        """Для SOV-TRP-геометрии в _apply_sov_trp_geometry достаточно знать,
        Goods это или нет (используется при выборе sov_bounds_*).
        """
        prefix = logcats[0].split(".", 1)[0]
        return "Goods" if prefix == "Goods" else prefix

    # ---- основной расчёт по одному (cut, month) -----------------------
    def _build_one(self, cut: CustomCutInput, month: int) -> pd.DataFrame:
        ref_flight = self._reference_flight(cut.logcats)

        # 1) Геометрия SOV-TRP в той же логике, что и в матрехе.
        self._builder._apply_sov_trp_geometry(
            flight=ref_flight,
            trp=cut.min_TRP,
            sov=cut.min_SOV,
            vertical=self._vertical_for_geometry(cut.logcats),
        )
        df_curve = self._builder.reach_curves[ref_flight].copy()
        trps = sorted(df_curve["TRP"].astype(int).unique())

        # 2) Нормированный профиль DTB-shape: predicted_metric_at_trp / max.
        shape = np.array(
            [self._builder._predict_metric_at_trp(ref_flight, t) for t in trps]
        )
        shape = shape / shape.max()

        # Добавим в сетку min_TRP, если его там нет (нужен якорь).
        anchor_trp = int(cut.min_TRP)
        if anchor_trp not in trps:
            shape_anchor = float(np.interp(anchor_trp, trps, shape))
            insert_at = int(np.searchsorted(trps, anchor_trp))
            trps = list(trps[:insert_at]) + [anchor_trp] + list(trps[insert_at:])
            shape = np.concatenate([shape[:insert_at], [shape_anchor], shape[insert_at:]])

        # 3) Финансовые поправки (lookup-ы с фоллбэками).
        slice_key = ", ".join(cut.logcats)
        value = lookups.value_for(slice_key, month, value_dict, dtb_value_yoy_dict)
        ce = lookups.ce_for(slice_key, CE_dict)
        trp_cost = lookups.trp_cost_for(slice_key, month, trp_cost_dict)

        # 4) Якорь: revenue(min_TRP) / budget(min_TRP) − 1 == ROMI.
        anchor_idx = trps.index(anchor_trp)
        anchor_shape = float(shape[anchor_idx])
        anchor_budget = anchor_trp * trp_cost * 1000.0
        anchor_revenue = anchor_budget * (1.0 + cut.ROMI)
        anchor_dtb = anchor_revenue / (value * ce * self.long_term_effect)

        # 5) Масштабирование DTB_pred по форме shape.
        scale = anchor_dtb / anchor_shape if anchor_shape > 0 else 0.0
        dtb_pred = shape * scale

        # 6) Сборка DataFrame в matrix-схеме.
        sov_series = df_curve.set_index("TRP")["SOV"].reindex(trps).interpolate(
            method="linear", limit_direction="both"
        )
        budget = np.array(trps, dtype=float) * trp_cost * 1000.0
        revenue = dtb_pred * value * ce * self.long_term_effect
        with np.errstate(divide="ignore", invalid="ignore"):
            romi = np.where(budget > 0, revenue / budget - 1.0, np.nan)

        df = pd.DataFrame(
            {
                "TRP": trps,
                "DTB_pred": dtb_pred,
                "SOV": sov_series.values,
                "budget": budget,
                "revenue": revenue,
                "ROMI": romi,
                "logcats": [_logcat_set(slice_key)] * len(trps),
                "category": [cut.name] * len(trps),
                "low": dtb_pred * (1.0 - self.ci_band),
                "high": dtb_pred * (1.0 + self.ci_band),
            }
        )
        df.index = df["TRP"]
        df.index.name = "TRP"
        return df[MATRIX_COLUMNS]

    # ---- публичный API ------------------------------------------------
    def build(
        self,
        inputs: Iterable,
        months: Iterable[int] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Главная точка: строит lookup для всех (cut, month).

        inputs: list[dict|CustomCutInput|pd.Series] | pd.DataFrame
        months: список месяцев (1..12). По умолчанию config.MONTHS.
        """
        if isinstance(inputs, pd.DataFrame):
            inputs = inputs.to_dict(orient="records")
        cuts = [CustomCutInput.coerce(it) for it in inputs]
        if not cuts:
            return {}

        months = list(months) if months is not None else list(config.MONTHS)

        # Догрузим только те reference-кривые, что реально пригодятся.
        needed = {self._reference_flight(c.logcats) for c in cuts}
        self._ensure_reach(needed)

        out: dict[str, pd.DataFrame] = {}
        for cut in cuts:
            for month in months:
                out[f"{cut.name}_{month}"] = self._build_one(cut, month)
        return out


# ---------------------------------------------------------------------------
# CLI / utility
# ---------------------------------------------------------------------------
def slim_build_and_save(
    inputs,
    output_path="CE_prediction_dict_slim.pkl",
    parser: GoogleSheetsParser | None = None,
):
    """Удобная обёртка: собрал → pickle.dump → отдал путь."""
    out_path = Path(output_path)
    promiser = SlimPromiser(parser=parser)
    matrix = promiser.build(inputs)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        pickle.dump(matrix, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[slim_promiser] записал {len(matrix)} ключей в {out_path}")
    return out_path

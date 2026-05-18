"""
pROMIser-matrix: единственная задача — построить lookup-словарь
(flight_month → DataFrame) для MILP-оптимизатора.

Шаги пайплайна:
  1. load_history()      — забрать данные исторических флайтов
                            (TRP, SOV, базы, метрики, OPM, consideration)
  2. load_reach_curves() — забрать кривые TRP→Reach по каждому
                            историческому флайту
  3. attach_new_flights()— к новым флайтам прицепить кривую TRP→Reach
                            ближайшей по дате старой РК той же категории
  4. build_dtb_matrix()  — для каждого (flight, месяц 1..12) посчитать
                            DTB_pred(TRP) и привязать budget/revenue/ROMI
  5. build_ci_matrix()   — Bootstrap-доверительные интервалы (low/high)
                            для DTB_pred

Снаружи доступен класс MatrixBuilder, который держит общее состояние
(`history_df`, `reach_curves`, `data_to_predict`) и собирает финальную
матрицу за один вызов `.build(...)`.
"""
from __future__ import annotations

import re
from typing import Iterable

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from PROMISER.configurations import config
from PROMISER.configurations.references import CLOSEST_START_RK
from PROMISER.configurations.dictionaries import dtb_value_yoy_dict as _default_yoy

from PROMISER.data_uploading import lookups
from PROMISER.data_uploading.data_loader import (
    load_history_df,
    load_reach_curves,
    load_seen_curve,
)
from PROMISER.data_uploading.table_parser import GoogleSheetsParser


# Нужные колонки в выходной матрице (то, что ждёт MILP-оптимизатор).
MATRIX_COLUMNS = [
    "TRP", "DTB_pred", "SOV", "budget", "revenue",
    "ROMI", "logcats", "category", "low", "high",
]


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------
def _logcat_set(value: str) -> set[str]:
    """'A, B,C' → {'A', 'B', 'C'}."""
    return {item.strip() for item in str(value).split(",") if item.strip()}


def _equalize(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Дотягивает b до длины a, повторяя последний элемент."""
    if len(b) < len(a):
        b = np.array(list(b) + [b[-1]] * (len(a) - len(b)))
    return a, b


# ---------------------------------------------------------------------------
# Класс
# ---------------------------------------------------------------------------
class MatrixBuilder:
    """Строит lookup-словарь для MILP-оптимизатора.

    Использование:
        builder = MatrixBuilder(data_to_predict=df_new)
        matrix  = builder.build(
            DTB_dict, SOV_dict, value_dict, trp_cost_dict, CE_dict,
            n_bootstrap=200,
        )
    """

    def __init__(
        self,
        data_to_predict: pd.DataFrame,
        question: str = config.DEFAULT_QUESTION,
        real_seen_coeff: float = config.REAL_SEEN_COEFF,
        sov_bounds_goods: tuple[float, float] = config.SOV_BOUNDS_GOODS,
        sov_bounds_other: tuple[float, float] = config.SOV_BOUNDS_OTHER,
        sov_coeff_start: float = config.SOV_COEFF_START,
        sov_coeff_end: float = config.SOV_COEFF_END,
        avg_creative_coeff: float = config.AVG_CREATIVE_COEFF,
        long_term_effect: float = config.LONG_TERM_EFFECT,
        trp_anchor: int = config.DISCRETE_TRP_ANCHOR,
        parser: GoogleSheetsParser | None = None,
    ) -> None:
        self.data_to_predict = self._normalize_input(data_to_predict)

        # Параметры модели
        self.question = question
        self.real_seen_coeff = real_seen_coeff
        self.sov_bounds_goods = sov_bounds_goods
        self.sov_bounds_other = sov_bounds_other
        self.sov_coeff_start = sov_coeff_start
        self.sov_coeff_end = sov_coeff_end
        self.avg_creative_coeff = avg_creative_coeff
        self.long_term_effect = long_term_effect
        self.trp_anchor = trp_anchor

        # Парсер Google Sheets — либо передан снаружи (для тестов / повторного использования),
        # либо инициализируется лениво при первом вызове.
        self._parser = parser

        # Состояние пайплайна (заполняется по мере)
        self.history_df: pd.DataFrame | None = None
        self.reach_curves: dict[str, pd.DataFrame] = {}
        self.seen_curve: np.ndarray | None = None

    # ---- input ----------------------------------------------------------
    @staticmethod
    def _normalize_input(data: pd.DataFrame) -> pd.DataFrame:
        """Чтобы аналитик не путался, принимаем оба варианта названия колонки.

        В макет-таблице она называется `main_log_cats`, в исторической — `logical_category`.
        Внутри пайплайна используем `logical_category`.
        """
        df = data.copy()
        if "logical_category" not in df.columns and "main_log_cats" in df.columns:
            df = df.rename(columns={"main_log_cats": "logical_category"})
        required = {"flight", "category", "logical_category", "vertical", "date_start"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"В data_to_predict не хватает обязательных колонок: {sorted(missing)}"
            )
        df["date_start"] = pd.to_datetime(df["date_start"])
        return df

    # ---- parser lazy init ----------------------------------------------
    @property
    def parser(self) -> GoogleSheetsParser:
        if self._parser is None:
            self._parser = GoogleSheetsParser(
                token_path=config.TOKEN_PATH,
                credentials_path=config.CREDENTIALS_PATH,
            )
        return self._parser

    # ---- 1. подготовка данных -------------------------------------------
    def prepare(self) -> None:
        """Шаги 1-3: грузим исторические данные, кривые охвата и привязываем к новым флайтам."""
        if self.history_df is None:
            self.history_df = load_history_df(self.parser)

        if not self.reach_curves:
            self.reach_curves = load_reach_curves(
                self.parser, list(self.history_df["flight"])
            )

        if self.seen_curve is None:
            self.seen_curve = load_seen_curve(self.question)

        self._attach_new_flights()

    def _attach_new_flights(self) -> None:
        """К новому флайту прицепляем кривую TRP→Reach ближайшей по дате старой РК той же категории."""
        assert self.history_df is not None
        history = self.history_df.copy()
        history["date_start"] = pd.to_datetime(history["date_start"])

        for _, row in self.data_to_predict.iterrows():
            new_flight = row["flight"]
            cat = row["category"]
            new_ds = row["date_start"]

            old_cat = history[history["category"] == cat]
            if old_cat.empty:
                raise ValueError(
                    f"В категории '{cat}' нет старых кампаний — "
                    f"нечем наследовать кривую для flight {new_flight!r}."
                )
            nearest_idx = (old_cat["date_start"] - new_ds).abs().idxmin()
            nearest = old_cat.loc[nearest_idx, "flight"]
            if nearest not in self.reach_curves:
                raise KeyError(f"У {nearest!r} нет кривой в reach_curves")

            self.reach_curves[new_flight] = self.reach_curves[nearest].copy()

    # ---- 2. геометрия SOV-TRP -------------------------------------------
    def _bounds_for(self, vertical: str) -> tuple[float, float]:
        return self.sov_bounds_goods if vertical == "Goods" else self.sov_bounds_other

    def _apply_sov_trp_geometry(
        self,
        flight: str,
        trp: float,
        sov: float,
        vertical: str,
    ) -> None:
        """Заливает в reach_curves[flight] две колонки: 'coeffs' и 'SOV'.

        coeffs(t):
              start_coeff * t / start_TRP                         если t < start_TRP
              линейно от start_coeff до end_coeff                 если start_TRP <= t < end_TRP
              end_coeff                                           иначе
        SOV(t):  t / (trp + competitors_TRP), но не больше 1.
        """
        min_sov, max_sov = self._bounds_for(vertical)
        competitors_trp = trp / sov - trp

        start_trp = min_sov * competitors_trp / (1 - min_sov)
        end_trp = max_sov * competitors_trp / (1 - max_sov)
        start_coeff = self.sov_coeff_start
        end_coeff = self.sov_coeff_end

        coeffs: dict[int, float] = {}
        sov_values: dict[int, float] = {}
        for t in sorted(self.reach_curves[flight]["TRP"]):
            if t < start_trp:
                c = start_coeff * t / start_trp
            elif t < end_trp:
                c = start_coeff + (end_coeff - start_coeff) * (t - start_trp) / (end_trp - start_trp)
            else:
                c = end_coeff
            coeffs[t] = c
            sov_v = t / (trp + competitors_trp)
            sov_values[t] = min(sov_v, 1.0)

        df = self.reach_curves[flight]
        df["coeffs"] = df["TRP"].map(coeffs)
        df["SOV"] = df["TRP"].map(sov_values)

    # ---- 3. охват и DTB-метрика ------------------------------------------
    def _build_reach_array(self, flight: str, trp: int) -> np.ndarray:
        """Формирует массив "доля аудитории, увидевшей рекламу N раз"
        для конкретного TRP, с поправкой на real_seen_coeff."""
        df = self.reach_curves[flight]
        reach_freqs = [int(c) for c in df.columns if str(c).isdigit()]

        row = df[df["TRP"] == trp]
        if row.empty:
            raise ValueError(f"TRP {trp} нет в кривой flight {flight!r}")
        reaches = row[reach_freqs].values.flatten()

        # Поправка: люди видят меньше, чем считает kantar (real_seen_coeff)
        corrected_freqs = np.ceil(np.array(reach_freqs) * self.real_seen_coeff)
        merged = (
            pd.DataFrame([corrected_freqs, reaches])
            .T.groupby(0)[1]
            .max()
            .reset_index()
        )
        corrected_freqs = np.array(merged[0]).astype(int)
        corrected_reaches = np.array(merged[1])

        out = np.zeros(corrected_freqs.max() + 1)
        for i in range(len(corrected_freqs) - 1):
            slope = (corrected_reaches[i] - corrected_reaches[i + 1]) / (
                corrected_freqs[i + 1] - corrected_freqs[i]
            )
            for j in range(corrected_freqs[i], corrected_freqs[i + 1]):
                out[j] = slope
        out[-1] = corrected_reaches[-1]
        return out

    def _predict_metric_at_trp(self, flight: str, trp: int) -> float:
        sov_coeff = self.reach_curves[flight]["coeffs"]
        reach = self._build_reach_array(flight, trp)
        seen = self.seen_curve
        reach, seen = _equalize(reach, seen)
        metric = sum((p / 100.0) * v for p, v in zip(reach, seen))
        return metric * sov_coeff[trp]

    # ---- 4. калибровка коэффициента ------------------------------------
    def _creative_coeff(self, flight: str) -> float:
        """OPM * consideration / avg, либо 1.0 при отсутствии данных."""
        df = self.history_df
        df["OPM"] = pd.to_numeric(df["OPM"].replace(",", ".", regex=True), errors="coerce")
        df["consideration"] = pd.to_numeric(
            df["consideration"].replace(",", ".", regex=True), errors="coerce"
        )
        opm = df.loc[df["flight"] == flight, "OPM"].values[0]
        cons = df.loc[df["flight"] == flight, "consideration"].values[0]
        if pd.isna(opm) or pd.isna(cons):
            return 1.0
        return (opm * cons) / self.avg_creative_coeff

    def _compute_calibration_grid(self, flight: str, flight_params, coeff: float | None):
        """Считает сетку (TRP, predicted_metric) для одного флайта.

        Семантика двух режимов (важно для совпадения со старым поведением):

        * coeff=None — режим калибровки на исторический флайт.
          Нормализуем сетку, чтобы trp_y(TRP_факт) == metric_abs / creative_coeff,
          то есть "коэффициент" в свою очередь делим на качество креатива
          (чтобы потом это качество не уносить в new-flight, где OPM/consideration
          могут отсутствовать).

        * coeff задан — режим расчёта DTB_pred для new-flight (матрица для MILP).
          Просто масштабируем сетку на coeff. creative_coeff здесь НЕ применяется,
          т.к. (а) для new-flight его в history_df нет, (б) он уже был "выкручен"
          из коэффициента на этапе калибровки.
        """
        trp, _, metric_abs, _ = flight_params

        trp_x: list[int] = []
        trp_y: list[float] = []
        for t in sorted(self.reach_curves[flight]["TRP"].astype(int)):
            trp_x.append(t)
            trp_y.append(self._predict_metric_at_trp(flight, t))

        if trp_x[-1] < trp:
            trp_x.append(trp)
            trp_y.append(trp_y[-1])

        trp_y = np.array(trp_y) / np.max(trp_y)
        trp_x = np.array(trp_x)

        if coeff is None:
            start_val = trp_y[trp_x == trp]
            coeff_used = (metric_abs / start_val) / self._creative_coeff(flight)
            trp_y = trp_y * coeff_used
        else:
            trp_y = trp_y * coeff
            start_val = trp_y[trp_x == trp]
            coeff_used = start_val
        return trp_x, trp_y, coeff_used

    def _final_coeff(
        self,
        reference_flights: Iterable[str],
        randomize: bool = False,
    ) -> float:
        """Медиана коэффициентов калибровки по reference-флайтам.

        randomize=True — для bootstrap; metric_abs_analytics сэмплируется
        как N(mean, mde/1.96).
        """
        coeffs: list[float] = []
        for flight in reference_flights:
            try:
                row = self.history_df[self.history_df["flight"] == flight].iloc[0]
            except IndexError:
                print(f"[promiser] предупреждение: flight {flight!r} нет в history_df")
                continue

            metric_mean = float(row["metric_abs_analytics"])
            mde = float(row["mde_abs"])

            if randomize:
                metric_mean = max(metric_mean, 10.0) if metric_mean == 0 else metric_mean
                sigma = mde / 1.96
                sample = np.random.normal(loc=metric_mean, scale=sigma)
                metric_abs = sample if sample != 0 else 10.0
            else:
                metric_abs = 1e-6 if metric_mean == 0 else metric_mean

            flight_params = (int(row["TRP"]), float(row["SOV"]), metric_abs, mde)
            self._apply_sov_trp_geometry(
                flight, trp=flight_params[0], sov=flight_params[1], vertical=row["vertical"]
            )
            _, _, coeff_used = self._compute_calibration_grid(flight, flight_params, coeff=None)

            base = float(row["base_dtb"])
            max_c = float(coeff_used) * (metric_abs + mde) / metric_abs / base
            min_c = float(coeff_used) * (metric_abs - mde) / metric_abs / base
            coeffs.extend(np.linspace(min_c, max_c, 1000))

        if not coeffs:
            raise RuntimeError("Не удалось посчитать ни один calibration coeff")
        return float(np.median(coeffs))

    # ---- 5. построение DTB-матрицы --------------------------------------
    def _reference_flights_for(self, flight: str) -> list[str]:
        cat = self.data_to_predict.loc[
            self.data_to_predict["flight"] == flight, "category"
        ].iat[0]
        if cat not in CLOSEST_START_RK:
            raise KeyError(
                f"Категория {cat!r} отсутствует в CLOSEST_START_RK "
                f"(см. references.py)"
            )
        return CLOSEST_START_RK[cat]

    def _store_dtb_curve(
        self,
        source_flight: str,
        target_key: str,
        trp_x: np.ndarray,
        trp_y: np.ndarray,
    ) -> None:
        """Кладёт в reach_curves[target_key] копию профиля + DTB_pred."""
        src = self.reach_curves[source_flight].copy()
        if "DTB_pred" in src.columns:
            src.drop(columns=["DTB_pred"], inplace=True)
        df_dtb = pd.DataFrame({"TRP": trp_x, "DTB_pred": trp_y})
        merged = pd.merge(src, df_dtb, left_index=True, right_on="TRP", how="left")
        if "TRP_x" in merged.columns and "TRP_y" in merged.columns:
            merged.drop(columns=["TRP_x", "TRP_y"], inplace=True)
        merged.set_index("TRP", drop=False, inplace=True)
        self.reach_curves[target_key] = merged

    def _build_dtb_for_flight_month(
        self,
        flight: str,
        month: int,
        DTB_dict: dict,
        SOV_dict: dict,
    ) -> None:
        row = self.data_to_predict.loc[self.data_to_predict["flight"] == flight].iloc[0]
        logcat = row["logical_category"]
        sov = lookups.sov_for(logcat, month, SOV_dict)
        base = lookups.dtb_for(logcat, month, DTB_dict)

        flight_params = (self.trp_anchor, sov, 0.0, 0.0)
        self._apply_sov_trp_geometry(flight, trp=self.trp_anchor, sov=sov, vertical=row["vertical"])
        fin_coeff = self._final_coeff(self._reference_flights_for(flight))

        trp_x, trp_y, _ = self._compute_calibration_grid(
            flight, flight_params, coeff=fin_coeff * base
        )
        self._store_dtb_curve(flight, f"{flight}_{month}", trp_x, trp_y)

    def _annotate_dollars(
        self,
        data: pd.DataFrame,
        flight_month: str,
        value_dict: dict,
        trp_cost_dict: dict,
        CE_dict: dict,
        yoy_dict: dict | None = None,
    ) -> None:
        m = re.match(r"^(.*)_(\d{1,2})$", flight_month)
        base, month = (m.group(1), int(m.group(2))) if m else (flight_month, None)

        logcat = data.loc[data["flight"] == base, "logical_category"].values[0]
        category = data.loc[data["flight"] == base, "category"].values[0]

        # YoY-поправка применяется внутри value_for (yoy^2, всегда).
        yoy = yoy_dict if yoy_dict is not None else _default_yoy

        cross_effect = lookups.ce_for(logcat, CE_dict)
        dtb_value = lookups.value_for(logcat, month, value_dict, yoy)
        trp_cost = lookups.trp_cost_for(logcat, month, trp_cost_dict)

        df = self.reach_curves[flight_month]
        df["budget"] = df["TRP"] * trp_cost * 1000
        df["revenue"] = df["DTB_pred"] * dtb_value * cross_effect * self.long_term_effect
        df["ROMI"] = df["revenue"] / df["budget"] - 1
        df["logcats"] = [_logcat_set(logcat)] * len(df)
        df["category"] = [category] * len(df)

    def build_dtb_matrix(
        self,
        DTB_dict: dict,
        SOV_dict: dict,
        value_dict: dict,
        trp_cost_dict: dict,
        CE_dict: dict,
    ) -> dict[str, pd.DataFrame]:
        """Шаг 4: собирает (flight, month) → DataFrame с DTB_pred / budget / revenue / ROMI."""
        flights = list(np.unique(self.data_to_predict["flight"]))
        for flight in flights:
            for month in config.MONTHS:
                self._build_dtb_for_flight_month(flight, month, DTB_dict, SOV_dict)

        flight_months = [f"{f}_{m}" for f in flights for m in config.MONTHS]
        for fm in flight_months:
            self._annotate_dollars(self.data_to_predict, fm, value_dict, trp_cost_dict, CE_dict)
        return {fm: self.reach_curves[fm] for fm in flight_months}

    # ---- 6. CI bootstrap ------------------------------------------------
    def build_ci_matrix(
        self,
        DTB_dict: dict,
        SOV_dict: dict,
        n_bootstrap: int = config.DEFAULT_N_BOOTSTRAP,
    ) -> dict[str, pd.DataFrame]:
        """Шаг 5: для каждой пары (flight, month) считает 95% CI по DTB_pred.

        Алгоритм: на каждой итерации пересчитываем fin_coeff с
        сэмплированной metric_abs_analytics; накопленные DTB_pred(TRP)
        перетряхиваются в перцентили 2.5% и 97.5%.
        """
        # Берём только записи вида flight_month, остальные не нужны.
        snapshots = {
            fm: df.copy()
            for fm, df in self.reach_curves.items()
            if fm.rsplit("_", 1)[-1].isdigit()
        }

        accum: dict[str, dict[int, list[float]]] = {
            fm: {int(t): [] for t in df.index.astype(int)} for fm, df in snapshots.items()
        }

        for i in tqdm(range(n_bootstrap), desc="bootstrap"):
            for fm in snapshots:
                base_flight, month_str = fm.rsplit("_", 1)
                month = int(month_str)
                row = self.data_to_predict.loc[
                    self.data_to_predict["flight"] == base_flight
                ].iloc[0]
                logcat = row["logical_category"]
                sov = lookups.sov_for(logcat, month, SOV_dict)
                base = lookups.dtb_for(logcat, month, DTB_dict)

                flight_params = (self.trp_anchor, sov, 0.0, 0.0)
                self._apply_sov_trp_geometry(
                    fm, trp=self.trp_anchor, sov=sov, vertical=row["vertical"]
                )
                fin_coeff = self._final_coeff(
                    self._reference_flights_for(base_flight), randomize=True
                )

                trp_x, trp_y, _ = self._compute_calibration_grid(
                    fm, flight_params, coeff=fin_coeff * base
                )
                self._store_dtb_curve(fm, f"{fm}_{i}", trp_x, trp_y)

                df_pred = self.reach_curves[f"{fm}_{i}"]
                for trp_level in df_pred.index.astype(int):
                    accum[fm][trp_level].append(df_pred.at[trp_level, "DTB_pred"])

                # очищаем bootstrap-побочные ключи, чтобы не раздувать память
                del self.reach_curves[f"{fm}_{i}"]

        result: dict[str, pd.DataFrame] = {}
        for fm, by_trp in accum.items():
            trps = sorted(by_trp)
            lows = [np.percentile(by_trp[t], 2.5) for t in trps]
            highs = [np.percentile(by_trp[t], 97.5) for t in trps]
            df_ci = pd.DataFrame({"low": lows, "high": highs}, index=trps)
            df_ci.index.name = "TRP"
            result[fm] = snapshots[fm].join(df_ci, how="left")
        return result

    # ---- 7. конечная сборка матрицы -------------------------------------
    def build(
        self,
        DTB_dict: dict,
        SOV_dict: dict,
        value_dict: dict,
        trp_cost_dict: dict,
        CE_dict: dict,
        n_bootstrap: int = config.DEFAULT_N_BOOTSTRAP,
    ) -> dict[str, pd.DataFrame]:
        """Полный пайплайн: prepare → build_dtb_matrix → build_ci_matrix.

        Возвращает словарь, готовый к pickle и подаче в MILP-оптимизатор.
        Каждое значение — DataFrame с колонками MATRIX_COLUMNS.
        """
        self.prepare()
        self.build_dtb_matrix(DTB_dict, SOV_dict, value_dict, trp_cost_dict, CE_dict)
        matrix = self.build_ci_matrix(DTB_dict, SOV_dict, n_bootstrap=n_bootstrap)
        # Финальная фильтрация колонок для MILP-оптимизатора.
        return {fm: df[MATRIX_COLUMNS] for fm, df in matrix.items()}

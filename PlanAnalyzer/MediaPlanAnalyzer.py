"""
Модуль обсчёта медиаплана из Excel-флоучарта.

Зависимости:
    pip install openpyxl pandas numpy
"""

import pandas as pd
import numpy as np
from PlanAnalyzer.ExcelWorker import ExcelWorker
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict


class MediaPlanAnalyzer:
    """
    Класс для анализа медиаплана, заданного в Excel-флоучарте.

    Парсит Excel-файл с флоучартами по вертикалям (листы формата
    "TV Flow charts {Название вертикали}"), определяет отдельные РК
    по цветам ячеек, рассчитывает бюджет с учётом формата (20s vs другой),
    интерполирует прогнозы DTB/выручки и формирует итоговую таблицу.
    """

    # Множитель стоимости для отличающегося формата (не 20s)
    COST_MULT_SHORT = 0.58    # разность TRP - TRP_20s > 0 (формат 10s)
    COST_MULT_LONG = 1.9    # разность TRP - TRP_20s < 0 (формат 40s)

    def __init__(
        self,
        categories: Dict[str, Dict],
        verticals: Dict[str, Dict],
        forecasts: Dict[str, Dict[int, pd.DataFrame]],
        competitors: Dict[str, Dict[int, float]],
        costs: Dict[str, Dict[int, float]]
    ):
        """
        :param categories: Словарь категорий планирования.
            Ключ: название категории.
            Значение: dict с полями vertical, competitor_category, и др.

        :param verticals: Словарь вертикалей планирования.

        :param forecasts: Прогнозы DTB и выручки.
            Ключ: название категории.
            Значение: {месяц: DataFrame с колонками TRP, DTB_pred, revenue}.

        :param competitors: TRP конкурентов.
            Ключ: ключ категории конкурентов.
            Значение: {месяц: суммарный TRP конкурентов}.

        :param costs: Стоимость 1 TRP (базовая, формат 20s).
            Ключ: название категории.
            Значение: {месяц: стоимость}.
        """
        self.categories = categories
        self.verticals = verticals
        self.forecasts = forecasts
        self.competitors = competitors
        self.costs = costs
        
        self.ExcelWorker = ExcelWorker()

    def analyze(self, file_obj) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Основной метод: парсит Excel-флоучарт и возвращает таблицу с обсчётом всех РК + сводку по вертикалям и тотал.

        :param file_obj: Файловый объект с Excel-файлом (может быть как путь, так и готовый объект)
        
        :return: Набор табличек с информацией по РК из плана + проверок ограничений
                 
        :raises ValueError: Если обнаружен отрицательный месячный TRP.
        """
        # Шаг 1: Парсим Excel — извлекаем РК по вертикалям
        try:
            all_campaigns = self.ExcelWorker.parse_excel(file_obj)
        except:
            raise ValueError("Возникли проблемы при обработке флоучарта, проверьте его формат!")

        # Шаг 2: Для каждой РК рассчитываем показатели
        results = []
        for campaign in all_campaigns:
            result = self._compute_campaign_metrics(campaign)
            results.append(result)

        if not results:
            detail_df = pd.DataFrame(columns=[
                "category", "vertical", "month_start", "month_end",
                "TRP", "budget", "SOV", "DTB_pred", "Revenue_pred", "ROMI_pred"
            ])
        else:
            detail_df = pd.DataFrame(results)
            
        # Шаг 3: Сводная таблица по вертикалям
        summary_df = self._compute_vertical_summary(detail_df)
        
        # Шаг 4: Таблица с проверками по категориям
        check_categories_df = self._check_category_constraints(detail_df)
        
        # Шаг 5: Таблица с проверками по вертикалям
        check_verticals_df = self._check_vertical_constraints(summary_df)

        return detail_df, summary_df, check_categories_df, check_verticals_df
    
    # =========================================================================
    # РАСЧЁТ МЕТРИК РК
    # =========================================================================

    def _compute_campaign_metrics(self, campaign: Dict) -> Dict[str, Any]:
        """
        Рассчитывает все метрики для одной РК.

        :param campaign: Словарь с данными РК:
            {"category", "vertical", "months": {month: {"trp_total", "trp_20s"}}}
        :return: Словарь с рассчитанными метриками.
        """
        category = campaign["category"]
        if category not in self.categories:
            raise ValueError(f"Категории {category} нет в параметрах!")
        
        vertical = campaign["vertical"]
        if vertical not in self.verticals:
            raise ValueError(f"Вертикаль {vertical} либо не имеет заполненных категорий, либо отсутсвует совсем!")
        
        months_data = campaign["months"]
        
        sorted_months = sorted(months_data.keys())
        month_start = sorted_months[0]
        month_end = sorted_months[-1]

        # Суммарные показатели
        total_trp = 0.0
        total_budget = 0.0
        total_dtb = 0.0
        total_revenue = 0.0
        total_comp_trp = 0.0

        for month in sorted_months:
            m_data = months_data[month]
            trp_total = m_data["trp_total"]
            trp_20s = m_data["trp_20s"]

            # --- TRP ---
            total_trp += trp_total

            # --- Бюджет с учётом формата ---
            month_budget = self._compute_month_budget(
                category, month, trp_total, trp_20s
            )
            total_budget += month_budget

            # --- Прогноз DTB (с интерполяцией) ---
            dtb = self._interpolate_forecast(category, month, trp_total, "DTB_pred")
            total_dtb += dtb

            # --- Прогноз выручки (с интерполяцией) ---
            revenue = self._interpolate_forecast(category, month, trp_total, "revenue")
            total_revenue += revenue

            # --- TRP конкурентов ---
            comp_key = self.categories.get(category, {}).get("competitor_category", "")
            comp_trp = self.competitors.get(comp_key, {}).get(month, 0.0)
            total_comp_trp += comp_trp

        # --- SOV ---
        if total_trp + total_comp_trp > 0:
            sov = total_trp / (total_trp + total_comp_trp)
        else:
            sov = 0.0

        # --- ROMI ---
        romi = (total_revenue / total_budget - 1) if total_budget > 0 else 0.0

        return {
            "category": category,
            "vertical": vertical,
            "month_start": month_start,
            "month_end": month_end,
            "TRP": round(total_trp),
            "budget": round(total_budget),
            "SOV": round(sov, 2),
            "DTB_pred": round(total_dtb),
            "Revenue_pred": round(total_revenue),
            "ROMI_pred": round(romi, 2)
        }

    def _compute_month_budget(
        self,
        category: str,
        month: int,
        trp_total: float,
        trp_20s: float
    ) -> float:
        """
        Рассчитывает бюджет за один месяц с учётом формата (20s vs другой).

        Алгоритм:
        1. diff = trp_total - trp_20s
        2. Если diff > 0: trp_other = diff * 2, cost_mult = 0.58
           Если diff < 0: trp_other = abs(diff) * 2, cost_mult = 1.9
           Если diff = 0: весь TRP в формате 20s
        3. trp_20s_actual = trp_total - abs(trp_other)
        4. budget = trp_20s_actual * base_cost + abs(trp_other) * base_cost * cost_mult
        """
    
        base_cost = self.costs.get(category, {}).get(month, 0.0)

        diff = trp_total - trp_20s

        if abs(diff) < 1e-6:
            # Весь TRP в формате 20s
            return trp_total * base_cost

        if diff > 0:
            # Формат 20/10s
            trp_other = diff * 2
            cost_mult = self.COST_MULT_SHORT
        else:
            # Формат 40/20s
            trp_other = abs(diff) * 2
            cost_mult = self.COST_MULT_LONG

        trp_20s_actual = trp_total - trp_other

        budget = trp_20s_actual * base_cost + trp_other * base_cost * cost_mult

        return budget

    def _interpolate_forecast(
        self,
        category: str,
        month: int,
        trp: float,
        column: str
    ) -> float:
        """
        Линейная интерполяция прогноза (DTB или выручки) для произвольного уровня TRP.

        Прогнозы заданы в дискретной сетке с шагом 250. Если TRP попадает между
        узлами — линейная интерполяция. Если TRP больше максимального узла —
        экстраполяция с шагом между последним и предпоследним узлами.

        :param category: Название категории.
        :param month: Номер месяца.
        :param trp: Фактический уровень TRP (может быть не кратен 250).
        :param column: Название колонки прогноза ("DTB_pred" или "revenue").
        :return: Интерполированное/экстраполированное значение прогноза.
        """
        if trp <= 0:
            return 0.0

        # Получаем таблицу прогнозов
        if category not in self.forecasts or month not in self.forecasts[category]:
            return 0.0

        df = self.forecasts[category][month].reset_index(drop=True)

        if column not in df.columns or "TRP" not in df.columns:
            return 0.0

        # Сортируем по TRP
        trp_values = df["TRP"].values.astype(float)
        forecast_values = df[column].values.astype(float)

        if len(trp_values) == 0:
            return 0.0

        # Точное совпадение
        mask = np.isclose(trp_values, trp, atol=0.5)
        if mask.any():
            return float(forecast_values[mask][0])

        # TRP меньше минимального узла — интерполяция от (0, 0) до первого узла
        if trp < trp_values[0]:
            if trp_values[0] == 0:
                return 0.0
            return float(forecast_values[0]) * trp / float(trp_values[0])

        # TRP больше максимального узла — экстраполяция по шагу последних двух узлов
        if trp > trp_values[-1]:
            if len(trp_values) >= 2:
                # Шаг по TRP и по прогнозу между двумя последними узлами
                trp_step = trp_values[-1] - trp_values[-2]
                val_step = forecast_values[-1] - forecast_values[-2]

                if trp_step > 0:
                    # Экстраполяция: сколько шагов нужно
                    extra_trp = trp - trp_values[-1]
                    slope = val_step / trp_step
                    return float(forecast_values[-1] + slope * extra_trp)
                else:
                    return float(forecast_values[-1])
            else:
                return float(forecast_values[-1])

        # Между узлами — линейная интерполяция
        idx_upper = int(np.searchsorted(trp_values, trp, side='left'))
        idx_lower = idx_upper - 1

        trp_low = float(trp_values[idx_lower])
        trp_high = float(trp_values[idx_upper])
        val_low = float(forecast_values[idx_lower])
        val_high = float(forecast_values[idx_upper])

        if trp_high == trp_low:
            return val_low

        alpha = (trp - trp_low) / (trp_high - trp_low)
        return val_low + alpha * (val_high - val_low)
    
    def _compute_vertical_summary(self, detail_df: pd.DataFrame) -> pd.DataFrame:
        """
        Формирует сводную таблицу по вертикалям с итоговой строкой.

        Столбцы:
            - vertical: название вертикали
            - num_campaigns: количество РК
            - total_trp: суммарный TRP
            - weighted_sov: средневзвешенный SOV (по TRP)
            - total_budget: суммарный бюджет
            - total_dtb: суммарный DTB
            - total_revenue: суммарная выручка
            - romi: ROMI на суммах (выручка / бюджет - 1)

        :param detail_df: Детальная таблица по РК.
        :return: Сводная таблица по вертикалям с итоговой строкой.
        """
        if detail_df.empty:
            return pd.DataFrame(columns=[
                "vertical", "num_campaigns", "total_trp", "weighted_sov",
                "total_budget", "total_dtb", "total_revenue", "romi"
            ])

        # Агрегация по вертикалям
        vert_summary = detail_df.groupby("vertical").apply(
            lambda g: pd.Series({
                "num_campaigns": len(g),
                "total_trp": g["TRP"].sum(),
                "weighted_sov": (
                    (g["SOV"] * g["TRP"]).sum() / g["TRP"].sum()
                    if g["TRP"].sum() > 0 else 0
                ),
                "total_budget": g["budget"].sum(),
                "total_dtb": g["DTB_pred"].sum(),
                "total_revenue": g["Revenue_pred"].sum(),
            })
        ).reset_index()

        # ROMI
        vert_summary["romi"] = vert_summary.apply(
            lambda row: (row["total_revenue"] / row["total_budget"] - 1)
            if row["total_budget"] > 0 else 0.0,
            axis=1
        )

        # Итоговая строка
        total_trp = detail_df["TRP"].sum()
        total_budget = detail_df["budget"].sum()
        total_revenue = detail_df["Revenue_pred"].sum()

        total_row = pd.DataFrame([{
            "vertical": "ИТОГО",
            "num_campaigns": len(detail_df),
            "total_trp": total_trp,
            "weighted_sov": (
                (detail_df["SOV"] * detail_df["TRP"]).sum() / total_trp
                if total_trp > 0 else 0
            ),
            "total_budget": total_budget,
            "total_dtb": detail_df["DTB_pred"].sum(),
            "total_revenue": total_revenue,
            "romi": (total_revenue / total_budget - 1) if total_budget > 0 else 0.0
        }])

        summary_df = pd.concat([vert_summary, total_row], ignore_index=True)

        # Округление
        summary_df["total_trp"] = summary_df["total_trp"].astype(int)
        summary_df["weighted_sov"] = summary_df["weighted_sov"].round(4)
        summary_df["total_budget"] = summary_df["total_budget"].round(0).astype(int)
        summary_df["total_dtb"] = summary_df["total_dtb"].round(0).astype(int)
        summary_df["total_revenue"] = summary_df["total_revenue"].round(0).astype(int)
        summary_df["romi"] = summary_df["romi"].round(4)
        summary_df["num_campaigns"] = summary_df["num_campaigns"].astype(int)

        return summary_df
    
    # =========================================================================
    # ПРОВЕРКА ВСЕХ ОГРАНИЧЕНИЙ
    # =========================================================================
    
    def _build_overlap_map(self, categories: Dict[str, Dict]) -> Dict[str, set]:
        """
        Внутрення функция для получения пересекающихся категорий
        """
        
        overlap_map = {}
        cat_names = list(categories.keys())
        
        for c in cat_names:
            overlap_map[c] = set()
            splits_c = set(categories[c].get("logical_category", []))
            
            for c2 in cat_names:
                if c2 == c:
                    continue
                splits_c2 = set(categories[c2].get("logical_category", []))
                if splits_c & splits_c2:
                    overlap_map[c].add(c2)
                    
        return overlap_map
        
    def _check_category_constraints(
        self,
        detail_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Проверяет выполнение бизнес-ограничений по каждой категории.

        :param detail_df: Детальная таблица РК (из analyze()).

        :return: DataFrame (строки = категории, столбцы = ограничения, значения = True/False)
        """
        # Строим карту пересечений по логическим разрезам
        overlap_map = self._build_overlap_map(self.categories)
        cat_checks = []

        for cat_name, cat_info in self.categories.items():
            cat_campaigns = detail_df[detail_df["category"] == cat_name]
            num_campaigns = len(cat_campaigns)
            total_budget = cat_campaigns["budget"].sum() if not cat_campaigns.empty else 0

            # --- 1. Число РК в диапазоне ---
            min_camps = cat_info.get("min_campaigns", 0)
            max_camps = cat_info.get("max_campaigns", 999)
            check_num_campaigns = min_camps <= num_campaigns <= max_camps

            # --- 2. Длительность каждой РК ---
            min_dur = cat_info.get("min_duration", 1)
            max_dur = cat_info.get("max_duration", 12)
            check_duration = True
            for _, row in cat_campaigns.iterrows():
                duration = row["month_end"] - row["month_start"] + 1
                if duration < min_dur or duration > max_dur:
                    check_duration = False
                    break

            # --- 3. Бюджет категории ---
            min_budget = cat_info.get("min_budget", 0)
            max_budget = cat_info.get("max_budget", float("inf"))
            check_budget = min_budget <= total_budget <= max_budget

            # --- 4. Мин. TRP на каждую РК ---
            min_trp = cat_info.get("min_trp", 0)
            check_min_trp = True
            for _, row in cat_campaigns.iterrows():
                if row["TRP"] < min_trp:
                    check_min_trp = False
                    break

            # --- 5. Мин. SOV на каждую РК ---
            min_sov = cat_info.get("min_sov", 0)
            check_sov = True
            for _, row in cat_campaigns.iterrows():
                if row["SOV"] < min_sov - 1e-6:
                    check_sov = False
                    break

            # --- 6. Обязательные месяцы проведения ---
            mandatory_months = cat_info.get("start_months", [])
            check_mandatory = True
            if mandatory_months:
                for m in mandatory_months:
                    active_in_month = any(
                        row["month_start"] <= m <= row["month_end"]
                        for _, row in cat_campaigns.iterrows()
                    )
                    if not active_in_month:
                        check_mandatory = False
                        break

            # --- 7. Строгий старт в обязательные месяцы ---
            strict_start = cat_info.get("strict_start", False)
            check_strict = True
            if strict_start and mandatory_months:
                for _, row in cat_campaigns.iterrows():
                    if row["month_start"] not in mandatory_months:
                        check_strict = False
                        break

            # --- 8. Нет пересечений со смежными категориями по месяцам ---
            check_no_overlap = True
            overlap_cats = overlap_map[cat_name]
            if overlap_cats:
                for _, row in cat_campaigns.iterrows():
                    for month in range(int(row["month_start"]), int(row["month_end"]) + 1):
                        # Проверяем, активна ли какая-то пересекающаяся категория в этом месяце
                        for c_prime in overlap_cats:
                            c_prime_campaigns = detail_df[detail_df["category"] == c_prime]
                            for _, row_prime in c_prime_campaigns.iterrows():
                                if row_prime["month_start"] <= month <= row_prime["month_end"]:
                                    check_no_overlap = False
                                    break
                            if not check_no_overlap:
                                break
                        if not check_no_overlap:
                            break
                    if not check_no_overlap:
                        break

            # --- 11. Анализируемость: есть хотя бы 1свободный месяц до старта РК ---
            check_analyzability = True
            if overlap_cats:
                for _, row in cat_campaigns.iterrows():
                    start_m = int(row["month_start"])
                    if start_m <= 3:
                        continue  # Автоматически выполнено

                    # Проверяем месяцы m-3, m-2, m-1
                    found_clean_month = False
                    for check_month in range(start_m - 3, start_m):
                        if check_month < 1:
                            found_clean_month = True
                            break

                        # Проверяем: есть ли в этом месяце РК из пересекающихся категорий
                        month_is_clean = True
                        for c_prime in overlap_cats:
                            c_prime_campaigns = detail_df[detail_df["category"] == c_prime]
                            for _, row_prime in c_prime_campaigns.iterrows():
                                if row_prime["month_start"] <= check_month <= row_prime["month_end"]:
                                    month_is_clean = False
                                    break
                            if not month_is_clean:
                                break

                        if month_is_clean:
                            found_clean_month = True
                            break

                    if not found_clean_month:
                        check_analyzability = False
                        break

            cat_checks.append({
                "Категория": cat_name,
                "Число РК": check_num_campaigns,
                "Длит. РК": check_duration,
                "Cумм. бюджет": check_budget,
                "Мин. TRP": check_min_trp,
                "Мин. SOV": check_sov,
                "Обязат. месяцы проведения": check_mandatory,
                "Обязат. месяцы старта": check_strict,
                "Корр. атрибуция": check_no_overlap,
                "Корр. анализ": check_analyzability,
            })        

        return pd.DataFrame(cat_checks).set_index("Категория")

    def _check_vertical_constraints(
        self,
        summary_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Проверяет выполнение бизнес-ограничений по каждой вертикали.

        :param summary_df: Сводка по вертикалям (из analyze()).

        :return: DataFrame (строки = вертикали, столбцы = ограничения, значения = True/False)
        """
        vert_checks = []

        for vert_name, vert_info in self.verticals.items():
            vert_agg_info = summary_df[summary_df["vertical"] == vert_name].squeeze()
            
            # Обработка пустого (у вертикали есть параметры категорий, но ее нет во флоучарте)
            if isinstance(vert_agg_info, pd.DataFrame):
                vert_agg_info = pd.Series(None, index=vert_agg_info.columns)

            # --- 1. Число РК в вертикали ---
            min_camps = vert_info.get("min_campaigns", 0)
            max_camps = vert_info.get("max_campaigns", 100)
            check_num_campaigns = min_camps <= vert_agg_info["num_campaigns"] <= max_camps

            # --- 2. Макс. бюджет вертикали ---
            max_budget = vert_info.get("max_budget", float("inf"))
            check_budget = vert_agg_info["total_budget"] <= max_budget

            # --- 3. Мин. суммарный TRP вертикали ---
            min_total_trp = vert_info.get("min_total_trp", 0)
            check_min_trp = vert_agg_info["total_trp"] >= min_total_trp

            vert_checks.append({
                "Вертикаль": vert_name,
                "Число РК": check_num_campaigns,
                "Макс. бюджет": check_budget,
                "Мин. TRP": check_min_trp,
            })

        return pd.DataFrame(vert_checks).set_index("Вертикаль")

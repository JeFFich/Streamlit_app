"""
Главный класс оптимизатора медиаплана на базе CP-SAT (Google OR-Tools).
"""

import pandas as pd
from ortools.sat.python import cp_model
from typing import Dict, List, Tuple, Any

from OptimizerNew.variables import (
    create_variables, add_linking_constraints,
    add_cumulative_trp_constraints, add_dynamic_cost_constraints
)
from OptimizerNew.constraints import add_logical_constraints
from OptimizerNew.objectives import add_objective
from OptimizerNew.process_data import (
    _compute_overlap_map, _get_competitor_trp,
    _get_dtb, _get_revenue, _get_cost_multipliers
)


class MediaPlanOptimizer:
    """
    Оптимизатор медиаплана на базе CP-SAT.
    Основной метод: optimize() — принимает входные данные, возвращает DataFrame с планом.
    """

    def __init__(self,
                 trp_levels: List[int] = list(range(250, 5501, 250)),
                 months: List[int] = list(range(1, 13)),
                 max_total_trp_per_campaign: int = 5500,
                 penalty_alpha: float = 0.5,
                 coverage_penalty_weight = 0.1,
                 season_penalty = 1,
                 solver_time_limit: int = 600,
                 solver_threads: int = 4):
        """
        :param trp_levels: Допустимые уровни TRP.
        :param months: Месяцы планирования.
        :param max_total_trp_per_campaign: Макс. суммарный TRP на одну непрерывную РК.
        :param penalty_alpha: Штраф за нарушение анализируемости (0..1).
        :param coverage_penalty_weight: Штраф за неравномерность плана
        :param season_penalty: Степень учета коэффициентов сезонности
        :param solver_time_limit: Лимит времени (секунды).
        :param solver_threads: Число потоков.
        """
        self.trp_levels = trp_levels
        self.months = months
        self.max_total_trp = max_total_trp_per_campaign
        self.penalty_alpha = penalty_alpha
        self.coverage_penalty_weight = coverage_penalty_weight
        self.season_penalty_weight = season_penalty
        self.solver_time_limit = solver_time_limit
        self.solver_threads = solver_threads

        # Заполняются при optimize()
        self.model = None
        self.v = {}
        self.categories = {}
        self.verticals = {}
        self.forecasts = {}
        self.competitors = {}
        self.costs = {}
        self.overlap_map = {}
        self.solver = None
        self.status = None

    def optimize(
        self,
        categories: Dict[str, Dict],
        verticals: Dict[str, Dict],
        forecasts: Dict[str, Dict],
        competitors: Dict[str, Dict],
        costs: Dict[str, Dict]
    ) -> pd.DataFrame:
        """Основной метод. Строит и решает CP-SAT задачу."""
        self.categories = categories
        self.verticals = verticals
        self.forecasts = forecasts
        self.competitors = competitors
        self.costs = costs
        self.overlap_map = _compute_overlap_map(categories)

        # Создаём модель
        self.model = cp_model.CpModel()

        # Переменные
        self.v = create_variables(self.model, categories, self.months, self.trp_levels)

        # Связующие ограничения
        add_linking_constraints(self.model, categories, self.months, self.trp_levels, self.v)

        # Кумулятивный TRP
        add_cumulative_trp_constraints(
            self.model, categories, self.months, self.trp_levels, self.v, competitors
        )

        # Динамическая стоимость
        add_dynamic_cost_constraints(
            self.model, categories, self.months, self.trp_levels, costs, self.v
        )

        # Содержательные ограничения
        add_logical_constraints(
            self.model, categories, verticals, self.months, self.trp_levels,
            costs, self.v, self.overlap_map, self.max_total_trp
        )

        # Целевая функция
        add_objective(
            self.model, categories, verticals, forecasts, self.months, self.trp_levels,
            self.v, self.penalty_alpha, self.coverage_penalty_weight
        )

        # Решаем
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = self.solver_time_limit
        self.solver.parameters.num_workers = self.solver_threads
        self.status = self.solver.Solve(self.model)

        # Если не нашли оптимума, то проводим диагностику
        if self.status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            self._diagnose_infeasibility()

        # Если все ок, то извлекаем план
        return self._extract_plan()

    def _diagnose_infeasibility(self):
        """Диагностика при отсутствии решения."""
        status_name = self.solver.StatusName(self.status)
        msg = f"Допустимого плана не существует. Статус: {status_name}.\n"
        msg += "Возможные причины:\n"

        issues = []
        for c, info in self.categories.items():
            if info["min_budget"] > info["max_budget"]:
                issues.append(f"  - Категория '{c}': min_budget > max_budget")
            if info["min_campaigns"] > info["max_campaigns"]:
                issues.append(f"  - Категория '{c}': min_campaigns > max_campaigns")
            if info["min_duration"] > info["max_duration"]:
                issues.append(f"  - Категория '{c}': min_duration > max_duration")

        for v_name, v_info in self.verticals.items():
            if v_info["min_campaigns"] > v_info["max_campaigns"]:
                issues.append(f"  - Вертикаль '{v_name}': min_campaigns > max_campaigns")

        for c in self.categories:
            mandatory = set(self.categories[c].get("start_months", []))
            for c_prime in self.overlap_map[c]:
                conflict = mandatory & set(self.categories[c_prime].get("start_months", []))
                if conflict:
                    issues.append(f"  - '{c}' и '{c_prime}': общие обязательные месяцы {conflict}")

        if issues:
            msg += "\n".join(issues)
        else:
            msg += " Явных противоречий не найдено. Ослабьте ограничения на бюджеты/TRP или уменьшите кол-во категорий планирования."

        raise ValueError(msg)

    def _extract_plan(self) -> pd.DataFrame:
        """Извлекает оптимальный план из решения CP-SAT."""
        campaigns = []

        for c in self.categories:
            # Определяем TRP по месяцам
            trp_by_month = {}
            for m in self.months:
                if self.solver.Value(self.v["y"][c][m]) == 1:
                    for t in self.trp_levels:
                        if self.solver.Value(self.v["x"][c][m][t]) == 1:
                            trp_by_month[m] = t
                            break

            # Разбиваем на РК по стартам и концам
            campaign_periods = self._split_into_campaigns_by_se(c)

            for start, end in campaign_periods:
                campaigns.append(self._compute_campaign_info(c, start, end, trp_by_month))

        if not campaigns:
            return pd.DataFrame(columns=[
                "vertical", "category", "logical_category", "start_month",
                "end_month", "total_trp", "competitor_category", "sov",
                "budget", "dtb", "revenue", "romi"
            ])

        return pd.DataFrame(campaigns)

    def _split_into_campaigns_by_se(self, category: str) -> List[Tuple[int, int]]:
        """
        Разбивает активные месяцы на отдельные РК, используя переменные s (старт) и e (конец).
        Корректно обрабатывает две РК подряд без перерыва.

        :param category: Название категории.
        :return: Список кортежей (start_month, end_month).
        """
        campaigns = []
        current_start = None

        for m in self.months:
            # Если в этом месяце старт — начинаем новую РК
            if self.solver.Value(self.v["s"][category][m]) == 1:
                current_start = m

            # Если в этом месяце конец — фиксируем РК
            if self.solver.Value(self.v["e"][category][m]) == 1:
                if current_start is not None:
                    campaigns.append((current_start, m))
                    current_start = None

        return campaigns

    def _compute_exact_budget(self, category: str, start_month: int, end_month: int,
                              trp_dict: Dict[int, int]) -> int:
        """Точный post-hoc расчёт бюджета с динамическими множителями."""
        mults = _get_cost_multipliers(self.categories[category])
        total = 0.0
        duration = end_month - start_month + 1
        for i, m in enumerate(range(start_month, end_month + 1)):
            trp = trp_dict.get(m, 0)
            base_cost = self.costs[category][m]
            if duration == 1:
                mult = mults["single"]
            elif i == 0:
                mult = mults["multi_first"]
            else:
                mult = mults["multi_cont"]
            total += base_cost * mult * trp
        return int(total)

    def _compute_campaign_info(self, category: str, start_month: int, end_month: int,
                               trp_dict: Dict[int, int]) -> Dict[str, Any]:
        info = self.categories[category]
        total_trp = sum(trp_dict.get(m, 0) for m in range(start_month, end_month + 1))
        total_comp = sum(
            _get_competitor_trp(self.categories, self.competitors, category, m)
            for m in range(start_month, end_month + 1)
        )
        sov = total_trp / (total_trp + total_comp) if (total_trp + total_comp) > 0 else 0.0
        budget = self._compute_exact_budget(category, start_month, end_month, trp_dict)
        dtb = sum(_get_dtb(self.forecasts, category, m, trp_dict.get(m, 0))
                  for m in range(start_month, end_month + 1))
        revenue = sum(_get_revenue(self.forecasts, category, m, trp_dict.get(m, 0))
                      for m in range(start_month, end_month + 1))
        romi = (revenue / budget - 1) if budget > 0 else 0.0

        return {
            "vertical": info["vertical"],
            "category": category,
            "logical_category": info["logical_category"],
            "start_month": start_month,
            "end_month": end_month,
            "total_trp": total_trp,
            "competitor_category": info["competitor_category"],
            "sov": round(sov, 2),
            "budget": round(budget),
            "dtb": round(dtb),
            "revenue": round(revenue),
            "romi": round(romi, 2)
        }
        
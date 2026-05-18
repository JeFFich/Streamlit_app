import pandas as pd
import pulp
from typing import Dict, List, Tuple, Any

from Optimizer.variables import create_variables, add_linking_constraints, add_cumulative_trp_constraints, add_dynamic_cost_constraints
from Optimizer.constraints import add_logical_constraints, _get_cost
from Optimizer.objectives import add_objective
from Optimizer.process_data import _compute_overlap_map, _get_competitor_trp, _get_cost, _get_dtb, _get_revenue

class MediaPlanOptimizer:
    """
    Класс для построения оптимального медиаплана методом целочисленного
    линейного программирования.

    Основной метод: optimize() — принимает все входные данные и возвращает
    DataFrame с оптимальным планом.
    """
    
    def __init__(self,
                 trp_levels: List = list(range(250, 5501, 250)),
                 months: List = list(range(1, 13, 1)),
                 max_total_trp_per_campaign: int = 5500,
                 penalty_alpha: float = 0.5,
                 solver_time_limit: int = 1200,
                 solver_gap: float = 0.01,
                 solver_threads: int = 4,
                 big_M: int = 1e5):
        """
        :param trp_levels: Список допустимых уровней TRP для РК
        :param months: Список месяцев планирования
        :param max_total_trp_per_campaign: Максимальный суммарный TRP на одну непрерывную РК.
        :param penalty_alpha: Коэффициент штрафа за нарушение анализируемости.
        :param solver_time_limit: Лимит времени на решение (в секундах).
        :param solver_gap: Допустимый разрыв оптимальности (в процентах).
        :param solver_threads: Число потоков для солвера (для ускорения расчетов)
        :param big_M: Большая константа для вырубания ряда ограничений в задаче оптимизации
        """
        
        # Исходные настройки
        self.trp_levels = trp_levels
        self.months = months
        self.max_total_trp = max_total_trp_per_campaign
        self.penalty_alpha = penalty_alpha
        self.solver_time_limit = solver_time_limit
        self.solver_gap = solver_gap
        self.solver_threads = solver_threads
        self.big_M = big_M

        # Внутренние структуры — заполняются при вызове optimize()
        self.prob = None
        self.vars = {}
        self.categories = {}
        self.verticals = {}
        self.forecasts = {}
        self.competitors = {}
        self.costs = {}
        self.overlap_map = {}
        
        # Статус оптимизатора
        self.status = None
        
    # =========================================================================
    # РЕШЕНИЕ И ДИАГНОСТИКА
    # =========================================================================
        
    def _solve(self) -> int:
        """
        Внутренняя функция для запуска солвера с возвращением статуса решения
        
        :return: Статус решения (нашелся план под заданные ограничения или нет)
        """
        
        # Выбор и настройка солвера
        solver = pulp.PULP_CBC_CMD(
            msg=False,
            timeLimit=self.solver_time_limit,
            gapRel=self.solver_gap,
            threads=self.solver_threads
        )

        self.prob.solve(solver)
        
        return self.prob.status
    
    def _diagnose_infeasibility(self):
        """
        Внутренняя функция диагностки отсутствии допустимого решения - пытаемся определить
        конфликтующие ограничения путём их последовательного ослабления.
        """
        
        status_name = pulp.LpStatus[self.prob.status]
        
        msg = f"Допустимого плана не существует. Статус: {status_name}.\n"
        msg += "Возможные причины:\n"

        # Простая диагностика: проверяем совместимость ключевых ограничений
        issues = []

        for category, category_info in self.categories.items():
            # Проверка: min_budget > max_budget
            if category_info["min_budget"] > category_info["max_budget"]:
                issues.append(f"  - Категория '{category}': мин. бюджет ({category_info['min_budget']}) > макс. бюджет ({category_info['max_budget']})")

            # Проверка: min_campaigns > max_campaigns
            if category_info["min_campaigns"] > category_info["max_campaigns"]:
                issues.append(f"  - Категория '{category}': мин. РК > макс. РК")

            # Проверка: min_duration > max_duration
            if category_info["min_duration"] > category_info["max_duration"]:
                issues.append(f"  - Категория '{category}': мин. длительность > макс. длительность")

            # Проверка: обязательных месяцев старта больше, чем max_campaigns * max_duration
            mandatory = category_info.get("start_months", [])
            if category_info.get("strict_start") and len(mandatory) > category_info["max_campaigns"]:
                issues.append(
                    f"  - Категория '{category}': обязательных стартов РК ({len(mandatory)}) > макс. РК ({category_info['max_campaigns']})"
                )

        # Проверка: min_campaigns > max_campaigns для вертикалей
        for vetical, vetical_info in self.verticals.items():
            if vetical_info["min_campaigns"] > vetical_info["max_campaigns"]:
                issues.append(f"  - Вертикаль '{vetical}': мин. РК > макс. РК")

        # Проверка overlap-конфликтов с обязательными месяцами
        for category, category_info in self.categories.items():
            mandatory = set(category_info.get("start_months", []))
            for category_prime in self.overlap_map[category]:
                mandatory_prime = set(self.categories[category_prime].get("start_months", []))
                conflict = mandatory & mandatory_prime
                
                if conflict:
                    issues.append(
                        f"  - Категории '{category}' и '{category_prime}' пересекаются по логкатам и имеют общие обязательные месяцы: {conflict}"
                    )

        if issues:
            msg += "\n".join(issues)
        else:
            msg += ("  Явных противоречий в параметрах не найдено.\n"
                    "  Рекомендуется ослабить ограничения на бюджет, TRP или число РК / уменьшить число категорий планирования.")

        raise ValueError(msg)
    
    # =========================================================================
    # ИЗВЛЕЧЕНИЕ ОПТИМАЛЬНОГО ПЛАНА
    # =========================================================================

    def _split_into_campaigns(self, active_months: List[int]) -> List[Tuple[int, int]]:
        """
        Разбивает список активных месяцев на непрерывные интервалы.

        :param active_months: Отсортированный список месяцев с активной РК.

       :return: Список кортежей (start_month, end_month).
        """
        
        if not active_months:
            return []

        campaigns = []
        start = active_months[0]
        prev = active_months[0]

        for m in active_months[1:]:
            if m == prev + 1:
                prev = m
            else:
                campaigns.append((start, prev))
                start = m
                prev = m

        campaigns.append((start, prev))
        
        return campaigns

    def _compute_campaign_info(
        self, 
        category: str, 
        start_month: int, 
        end_month: int,
        trp_dict: Dict[int, int]) -> Dict[str, Any]:
        """
        Вычисляет характеристики одной непрерывной РК в плане.

        :param category: Название категории.
        :param start_month: Месяц начала РК.
        :param end_month: Месяц окончания РК.
        :param trp_dict: Словарь c TRP по месяцам.
        
        :return: Словарь с характеристиками РК для итоговой таблицы.
        """
        
        category_info = self.categories[category]
        comp_key = category_info["competitor_category"]

        # Суммарный TRP за РК
        total_trp = sum(trp_dict.get(month, 0) for month in range(start_month, end_month + 1))

        # Суммарный TRP конкурентов за период РК
        total_comp_trp = sum(
            _get_competitor_trp(self.categories, self.competitors, category, month) for month in range(start_month, end_month + 1)
        )

        # SOV
        if total_trp + total_comp_trp > 0:
            sov = total_trp / (total_trp + total_comp_trp)
        else:
            sov = 0.0

        # Бюджет
        budget = sum(
            self.vars["budget"][category][month].varValue for month in range(start_month, end_month + 1)
        )

        # DTB и выручка
        dtb = sum(
            _get_dtb(self.forecasts, category, month, trp_dict.get(month, 0)) 
            for month in range(start_month, end_month + 1)
        )
        revenue = sum(
            _get_revenue(self.forecasts, category, month, trp_dict.get(month, 0)) 
            for month in range(start_month, end_month + 1)
        )

        # ROMI
        romi = (revenue / budget - 1) if budget > 0 else 0.0

        return {
            "vertical": category_info["vertical"],
            "category": category,
            "logical_category": category_info["logical_category"],
            "start_month": start_month,
            "end_month": end_month,
            "total_trp": total_trp,
            "competitor_category": comp_key,
            "sov": round(sov, 2),
            "budget": round(budget),
            "dtb": round(dtb),
            "revenue": round(revenue),
            "romi": round(romi, 2)
        }
        
    def _extract_plan(self) -> pd.DataFrame:
        """
        Извлекает оптимальный план из решённой задачи и формирует DataFrame.

        :return: Таблица с описанием найденного плана
        """
        
        cat_names = list(self.categories.keys())
        campaigns = []

        for c in cat_names:
            # Определяем активные месяцы
            active_months = []
            trp_by_month = {}

            for m in self.months:
                if pulp.value(self.vars["y"][c][m]) is not None and pulp.value(self.vars["y"][c][m]) > 0.5:
                    active_months.append(m)
                    # Определяем выбранный уровень TRP
                    for t in self.trp_levels:
                        if pulp.value(self.vars["x"][c][m][t]) is not None and pulp.value(self.vars["x"][c][m][t]) > 0.5:
                            trp_by_month[m] = t
                            break

            if not active_months:
                continue

            # Разбиваем на непрерывные РК
            campaign_periods = self._split_into_campaigns(active_months)

            # Собираем все характеристики РК
            for start, end in campaign_periods:
                campaign_info = self._compute_campaign_info(c, start, end, trp_by_month)
                campaigns.append(campaign_info)

        # Если собрался пустой план, то под него собираем пустую табличку
        if not campaigns:
            return pd.DataFrame(columns=[
                "vertical", "category", "logical_category", "start_month",
                "end_month", "total_trp", "competitor_category", "sov",
                "budget", "dtb", "revenue", "romi"
            ])

        return pd.DataFrame(campaigns)
        
    # =========================================================================
    # ВНЕШНИЙ ДОСТУП
    # =========================================================================
    
    def optimize(
        self,
        categories: Dict[str, Dict],
        verticals: Dict[str, Dict],
        forecasts: Dict[str, Dict[int, pd.DataFrame]],
        competitors: Dict[str, Dict[int, float]],
        costs: Dict[str, Dict[int, float]]
    ) -> pd.DataFrame:
        """
        Основной метод оптимизации. Строит и решает МILP-задачу.

        :param categories: Словарь с информацией по категориям.
                Ключ: название категории.
                Значение: словарь с полями:
                    - "vertical": str — название вертикали
                    - "logical_category": List[str] — список логических категорий
                    - "min_campaigns": int — мин. число РК в категории за год
                    - "max_campaigns": int — макс. число РК в категории за год
                    - "min_duration": int — мин. длительность одной непрерывной РК (мес.)
                    - "max_duration": int — макс. длительность одной непрерывной РК (мес.)
                    - "min_budget": float — мин. бюджет на все РК в категории
                    - "max_budget": float — макс. бюджет на все РК в категории
                    - "min_trp": int — мин. суммарный TRP для одной непрерывной РК
                    - "min_sov": float — мин. SOV (0..1) для одной непрерывной РК
                    - "competitor_category": str — ключ в словаре competitors
                    - "start_months": List[int] — обязательные месяцы старта
                    - "strict_start": bool — если True, старт возможен только в start_months

        :param verticals: Словарь c информацией по вертикалям.
                Ключ: название вертикали.
                Значение: словарь с полями:
                    - "min_campaigns": int — мин. число РК во всех категориях вертикали
                    - "max_campaigns": int — макс. число РК во всех категориях вертикали
                    - "min_total_trp": int — мин. суммарный TRP по всем РК в вертикали
                    - "max_total_budget": float — макс. суммарный бюджет на все РК в вертикали

        :param forecasts: Словарь c прогнозами выручки и DTB для категорий (из промисера).
                Ключ: название категории.
                Значение: словарь {месяц: DataFrame}, где DataFrame имеет столбцы:
                    - "trp": int (250, 500, ..., 5500)
                    - "dtb": float — прогноз DTB
                    - "revenue": float — прогноз выручки

        :param competitors: Словарь с TRP конкурентов по категориям RoRe
                Ключ: название категории конкурентов (совпадает с competitor_key в categories).
                Значение: словарь {месяц: суммарный TRP конкурентов}.

        :param costs: Словарь стоимости 1 TRP.
                Ключ: название категории.
                Значение: словарь {месяц: стоимость 1 TRP}.

        Returns:
            pd.DataFrame с оптимальным медиапланом. Столбцы:
                - vertical, 
                - category, 
                - logical_category, 
                - start_month, 
                - end_month,
                - total_trp, 
                - competitor_category, 
                - sov, 
                - budget, 
                - dtb, 
                - revenue, 
                - romi

        Raises:
            ValueError: Если задача не имеет допустимого решения
        """
        # Сохраняем входные данные
        self.categories = categories
        self.verticals = verticals
        self.forecasts = forecasts
        self.competitors = competitors
        self.costs = costs

        # Предварительная обработка
        self.overlap_map = _compute_overlap_map(self.categories)

        # Создаём задачу оптимизации
        self.prob = pulp.LpProblem("MediaPlanOptimization", pulp.LpMaximize)

        # Создаём переменные
        self.vars = create_variables(self.categories, self.months, self.trp_levels)

        # Добавляем связующие ограничения, динамический расчет бюджета и кумулятивный расчет TRP 
        self.prob = add_linking_constraints(self.prob, self.categories, self.months, self.trp_levels, self.vars)
        self.prob = add_cumulative_trp_constraints(self.prob, self.categories, self.months, self.trp_levels, self.vars, 
                                                   self.competitors, self.big_M)
        self.prob = add_dynamic_cost_constraints(self.prob, self.categories, self.months, self.trp_levels, self.costs, self.vars)

        # Добавляем содержательные ограничения
        self.prob = add_logical_constraints(self.prob, self.categories, self.verticals, self.months, self.trp_levels, 
                                            self.costs, self.vars, self.overlap_map, self.big_M, self.max_total_trp)

        # Добавляем целевую функцию
        self.prob = add_objective(self.prob, self.categories, self.forecasts, self.months, self.trp_levels, self.vars, 
                                  self.penalty_alpha)

        # Решаем
        self.status = self._solve()

        # Обрабатываем результат
        if self.status != pulp.constants.LpStatusOptimal:
            self._diagnose_infeasibility()

        # Достаем результат после обработки
        return self._extract_plan()
    
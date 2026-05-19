import pulp
from typing import Dict, List

from Optimizer.process_data import _get_cost, _get_cost_multipliers

# Суперкостыльная поправка бюджета (из-за нединамического расчета можем завышать/занижать оценку на ~2%)
BUDGET_AVG_ERROR = 0.02

def _add_vertical_campaign_count_constraints(
    model: pulp.LpProblem,
    verticals: Dict[str, Dict],
    categories: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict]) -> pulp.LpProblem:
    """
    Ограничение на число число РК в вертикали
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param verticals: Словарь с информацией по вертикалям
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    for vertical, vertical_info in verticals.items():
        # Категории в вертикали
        cats_in_v = [category for category, category_info in categories.items() if category_info["vertical"] == vertical]

        # Суммарное число РК в вертикали = sum стартов
        total_campaigns = pulp.lpSum(
            vars["s"][category][month] for category in cats_in_v for month in months
        )

        model += (
            total_campaigns >= vertical_info["min_campaigns"],
            f"Ogr1_vert_min_campaigns_{vertical}"
        )
        model += (
            total_campaigns <= vertical_info["max_campaigns"],
            f"Ogr1_vert_max_campaigns_{vertical}"
        )
        
    return model

def _add_duration_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict]) -> pulp.LpProblem:
    """
    Ограничение на продолжительность непрерывной РК в категориях
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    
    for category, category_info in categories.items():
        min_dur = category_info["min_duration"]
        max_dur = category_info["max_duration"]

        for month in months:
            # --- Минимальная продолжительность:  если старт в m, то y[c][m'] = 1 для m' = m, ..., min(m + min_dur - 1, 12) ---
            for month_prime in range(month, min(month + min_dur, 13)):
                model += (
                    vars["y"][category][month_prime] >= vars["s"][category][month],
                    f"Ogr2_min_dur_{category}_{month}_{month_prime}"
                )
                
            # --- Запрет старта, если до конца года не хватает месяцев ---
            if month + min_dur - 1 > max(months):
                model += (
                    vars["s"][category][month] == 0,
                    f"Ogr2_no_late_start_{category}_{month}"
                )

            # --- Максимальная продолжительность: сплошное окно из max_dur + 1 месяцев не может быть всё активно ---
            end_window = min(month + max_dur, 12)
            if end_window - month + 1 > max_dur:
                model += (
                    pulp.lpSum(
                        vars["y"][category][m_prime]
                        for m_prime in range(month, end_window + 1)
                    ) <= max_dur,
                    f"Ogr2_max_dur_{category}_{month}"
                )
                
    return model

def _add_vertical_budget_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    verticals: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict]) -> pulp.LpProblem:
    """
    Ограничение на максимальный бюджет в вертикали
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param verticals: Словарь с информацией по вертикалям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    
    for vetrical, vertical_info in verticals.items():
        categories_in_vertical = [category for category, category_info in categories.items() 
                                  if category_info["vertical"] == vetrical]
        
        total_budget = pulp.lpSum(
            vars["budget"][category][month]
            for category in categories_in_vertical
            for month in months
        )

        model += (
            total_budget <= vertical_info["max_budget"] * (1 + BUDGET_AVG_ERROR),
            f"Ogr3_vert_max_budget_{vetrical}"
        )
        
    return model

def _add_category_campaign_count_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict]) -> pulp.LpProblem:
    """
    Ограничение на число РК в категории
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    
    for category, category_info in categories.items():
        n_c = pulp.lpSum(vars["s"][category][month] for month in months)

        model += (
            n_c >= category_info["min_campaigns"],
            f"Ogr4_cat_min_campaigns_{category}"
        )
        model += (
            n_c <= category_info["max_campaigns"],
            f"Ogr4_cat_max_campaigns_{category}"
        )

    return model

def _add_min_trp_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict]) ->  pulp.LpProblem:
    """
    Ограничение на минимальный TRP для непрерывной РК (активно только в последнем ее месяце)

    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    
    for category, category_info in categories.items():
        min_trp = category_info["min_trp"]
        
        for month in months:
            model += (
                vars["CTRP"][category][month] >= min_trp * vars["e"][category][month],
                f"Ogr5_min_trp_{category}_{month}"
            )
            
    return model

def _add_max_trp_per_campaign_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict],
    max_trp: float) -> pulp.LpProblem:
    """
    Ограничение на максимальный суммарный TRP у непрерывной РК
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    :param max_trp: Максимальное ограничение по TRP у непрерывной РК
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    for category in categories.keys():
        for month in months:
            model += (
                vars["CTRP"][category][month] <= max_trp,
                f"Ogr6_max_trp_{category}_{month}"
            )
            
    return model

def _add_sov_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict],
    big_M: float) -> pulp.LpProblem:
    """
    Ограничение на минимальный SOV у непрерывной РК (активно только в последнем месяце)
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    :param big_M: Большая константа для ограничений

    :return: Задача оптимизации с добавленными ограничениями
    """
    
    for category, category_info in categories.items():
        sov_min = category_info["min_sov"]
        
        # Нет ограничения на SOV
        if sov_min <= 0:
            continue

        big_m_sov = sov_min * big_M

        for month in months:
            model += (
                (1 - sov_min) * vars["CTRP"][category][month]
                >= sov_min * vars["CTRP_comp"][category][month]
                - big_m_sov * (1 - vars["e"][category][month]),
                f"Ogr7_sov_{category}_{month}"
            )
            
    return model

def _add_category_budget_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict]) -> pulp.LpProblem:
    """
    Ограничение на суммарный бюджет РК в категории
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    
    for category, category_info in categories.items():
        total_budget_c = pulp.lpSum(vars["budget"][category][month] for month in months)

        model += (
            total_budget_c >= category_info["min_budget"] * (1 - BUDGET_AVG_ERROR),
            f"Ogr8_cat_min_budget_{category}"
        )
        
        model += (
            total_budget_c <= category_info["max_budget"] * (1 + BUDGET_AVG_ERROR),
            f"Ogr8_cat_max_budget_{category}"
        )
        
    return model

def _add_mandatory_start_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict]) -> pulp.LpProblem:
    """
    Ограничение на обязательные месяцы проведения РК в категории.
    Если  strict_start=True, то РК могут начинаться ТОЛЬКО в обязательные месяцы
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    
    # for category, category_info in categories.items():
    #     mandatory = category_info.get("start_months", [])
    #     strict = category_info.get("strict_start", False)
        
    #     print(f"Category: {category}")
    #     print(f"  mandatory: {mandatory}")
    #     print(f"  strict: {strict}")
    #     print(f"  months: {months}")
        
    #     for month in mandatory:
    #         print(f"  Adding y[{category}][{month}] == 1")
    #         model += (vars["y"][category][month] == 1, f"Ogr9_mandatory_{category}_{month}")

    #     if strict and mandatory:
    #         for month in months:
    #             if month not in mandatory:
    #                 print(f"  Adding s[{category}][{month}] == 0")
    #                 model += (vars["s"][category][month] == 0, f"Ogr9_strict_no_start_{category}_{month}")
    
    for category, category_info in categories.items():
        mandatory = category_info.get("start_months", [])
        strict = category_info.get("strict_start", False)

        # Обязательные месяцы: РК должна идти
        for month in mandatory:
            model += (
                vars["y"][category][month] == 1,
                f"Ogr9_mandatory_{category}_{month}"
            )

        # Строгий старт: старт разрешён только в указанные месяцы
        if strict and mandatory:
            for month in months:
                if month not in mandatory:
                    model += (
                        vars["s"][category][month] == 0,
                        f"Ogr9_strict_no_start_{category}_{month}"
                    )
                    
    return model

def _add_vertical_min_trp_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    verticals: Dict[str, Dict],
    months: List,
    trp_levels: List,
    vars: Dict[str, Dict]) -> pulp.LpProblem:
    """
    Ограничение на минимальный суммарный TRP в вертикали
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param verticals: Словарь с информацией по вертикалям
    :param months: Список месяцев планирования
    :param trp_levels: Список возможных уровней TRP
    :param vars: Словарь с переменными задачи оптимизации
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    
    for vertical, vertical_info in verticals.items():
        # Нет ограничения на TRP
        if "min_total_trp" not in vertical_info:
            continue

        categories_in_vertical = [category for category, category_info in categories.items() 
                                  if category_info["vertical"] == vertical]

        total_trp_v = pulp.lpSum(
            trp * vars["x"][category][month][trp]
            for category in categories_in_vertical
            for month in months
            for trp in trp_levels
        )

        model += (
            total_trp_v >= vertical_info["min_total_trp"],
            f"Ogr12_vert_min_trp_{vertical}"
        )
        
    return model
        
def _add_overlap_exclusion_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict],
    overlap_map: Dict[str, set]) -> pulp.LpProblem:
    """
    Ограничение на одновременное проведение РК в пересекающихся категориях
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    :param overlap_map: Словарь с пересекающимися категориями
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    
    added_pairs = set()

    for category in categories:
        for category_prime in overlap_map[category]:
            pair = tuple(sorted([category, category_prime]))
            
            # Избегаем дублирования: берём каждую пару один раз
            if pair in added_pairs:
                continue
            
            added_pairs.add(pair)

            for month in months:
                model += (
                    vars["y"][category][month] + vars["y"][category_prime][month] <= 1,
                    f"Ogr11_no_overlap_{pair[0]}_{pair[1]}_{month}"
                )
                
    return model

def _add_analyzability_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    vars: Dict[str, Dict],
    overlap_map: Dict[str, set]) -> pulp.LpProblem:
    """
    Нежесткое ограничение анализируемости: на горизонте 3 месяцев до старта должен быть хотя бы 1 «чистый» месяц.
    Если ограничение не выполняется, то накладываем штраф на целевую функцию (в размере половины от потенциальной выручки РК);
    для первых 3 месяцев планирования считаем по умолчанию выполненным

    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации
    :param overlap_map: Словарь с пересекающимися категориями
    
    :return: Задача оптимизации с добавленными ограничениями
    """
    
    category_names = list(categories.keys())

    for category in category_names:
        overlap_categories = overlap_map[category]

        # Прямые ограничения анализируемости
        for month in months:
            if month <= 3:
            # Для первых 3-х месяцев выполняется по умолчанию
                model += (
                    vars["z"][category][month] == 0,
                    f"Ogr10_z_zero_{category}_{month}"
                )
            else:
                for month_prime in range(month - 3, month):
                    for category_prime in overlap_categories:
                        model += (
                            vars["q"][category][month][month_prime] <= 1 - vars["y"][category_prime][month_prime],
                            f"Ogr10_q_clean_{category}_{month}_{month_prime}_{category_prime}"
                        )
                
                model += (
                    pulp.lpSum(
                        vars["q"][category][month][month_prime] for month_prime in range(month - 3, month) 
                    ) >= vars["s"][category][month] - vars["z"][category][month],
                    f"Ogr10_analyzability_{category}_{month}"
                )

        # Также связываем с переменными f - «размазываем» штраф на все месяцы РК
        for month in months:
            model += (
                vars["f"][category][month] <= vars["y"][category][month],
                f"Ogr10_f_ub_y_{category}_{month}"
            )

            model += (
                vars["f"][category][month] >= vars["z"][category][month],
                f"Ogr10_f_lb_z_{category}_{month}"
            )
            
            # Наследование переменных f для непрерывных РК
            if month >= 2:
                model += (
                    vars["f"][category][month] >= vars["f"][category][month - 1] - (1 - vars["y"][category][month]) - vars["s"][category][month],
                    f"Ogr10_f_inherit_{category}_{month}"
                )

                model += (
                    vars["f"][category][month] <= vars["z"][category][month] + (1 - vars["s"][category][month]) + (1 - vars["y"][category][month]),
                    f"Ogr10_f_reset_{category}_{month}"
                )

                model += (
                    vars["f"][category][month] <= vars["f"][category][month - 1] + vars["s"][category][month],
                    f"Ogr10_f_cont_{category}_{month}"
                )
                
    return model

def add_logical_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    verticals: Dict[str, Dict],
    months: List,
    trp_levels: List,
    costs: Dict[str, Dict],
    vars: Dict[str, Dict],
    overlap_map: Dict[str, set],
    big_M: float,
    max_trp: float) -> pulp.LpProblem:
    """
    Внешняя функция для заполнения всех логических ограничений для задачи оптимизации
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param verticals: Словарь с информацией по вертикалям
    :param months: Список месяцев планирования
    :param trp_levels: Список возможных уровней TRP
    :param costs: Словарь со стоимостями 1 TRP по категориям за каждый месяц
    :param vars: Словарь с переменными задачи оптимизации
    :param overlap_map: Словарь с пересекающимися категориями
    :param big_M: Большая константа для ограничений
    :param max_trp: Максимальное ограничение по TRP у непрерывной РК
    
    :return: Задача оптимизации с добавленными логическими ограничениями
    """
    
    # Ограничения на число РК
    model = _add_vertical_campaign_count_constraints(model, verticals, categories, months, vars)
    model =  _add_category_campaign_count_constraints(model, categories, months, vars)
    
    # Ограничения на длительность одной РК
    model = _add_duration_constraints(model, categories, months, vars)
    
    # Ограничения на суммарные бюджеты
    model = _add_vertical_budget_constraints(model, categories, verticals, months, vars)
    model = _add_category_budget_constraints(model, categories, months, vars)
    
    # Ограничения на TRP и SOV
    model = _add_min_trp_constraints(model, categories, months, vars)
    model = _add_max_trp_per_campaign_constraints(model, categories, months, vars, max_trp)
    model = _add_sov_constraints(model, categories, months, vars, big_M)
    model = _add_vertical_min_trp_constraints(model, categories, verticals, months, trp_levels, vars)
    
    # Ограничения на месяцы проведения/старта
    model = _add_mandatory_start_constraints(model, categories, months, vars)
    
    # Ограничения анализируемости
    model = _add_overlap_exclusion_constraints(model, categories, months, vars, overlap_map)
    model = _add_analyzability_constraints(model, categories, months, vars, overlap_map)
    
    return model

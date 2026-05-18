import pulp
from typing import Dict, List

from Optimizer.process_data import _get_competitor_trp, _get_cost_multipliers


# =========================================================================
# СОЗДАНИЕ ПЕРЕМЕННЫХ
# =========================================================================

def create_variables(
    categories: Dict[str, Dict], 
    months: List, 
    trp_levels: List) -> Dict[str, Dict]:
    """
    Cоздание всех ограничений в задаче оптимизации медиаплана
    
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param trp_levels: Список возможных уровней TRP
    
    :return: Словарь со всеми переменными задачи оптимизации
    """
    
    cat_names = list(categories.keys())
    vars = {}

    # --- x[c][m][t]: бинарная, уровень TRP t в категории c в месяце m ---
    vars["x"] = {}
    for c in cat_names:
        vars["x"][c] = {}
        for m in months:
            vars["x"][c][m] = {}
            for t in trp_levels + [0]:
                vars["x"][c][m][t] = pulp.LpVariable(
                    f"x_{c}_{m}_{t}", lowBound=0, upBound=1, cat="Binary"
                )

    # --- y[c][m]: бинарная, РК активна в категории c в месяце m ---
    vars["y"] = {}
    for c in cat_names:
        vars["y"][c] = {}
        for m in months:
            vars["y"][c][m] = pulp.LpVariable(
                f"y_{c}_{m}", lowBound=0, upBound=1, cat="Binary"
            )

    # --- s[c][m]: бинарная, старт РК в категории c в месяце m ---
    vars["s"] = {}
    for c in cat_names:
        vars["s"][c] = {}
        for m in months:
            vars["s"][c][m] = pulp.LpVariable(
                f"s_{c}_{m}", lowBound=0, upBound=1, cat="Binary"
            )

    # --- e[c][m]: бинарная, конец РК в категории c в месяце m ---
    vars["e"] = {}
    for c in cat_names:
        vars["e"][c] = {}
        for m in months:
            vars["e"][c][m] = pulp.LpVariable(
                f"e_{c}_{m}", lowBound=0, upBound=1, cat="Binary"
            )

    # --- CTRP[c][m]: непрерывная, кумулятивный TRP РК в месяце m ---
    vars["CTRP"] = {}
    for c in cat_names:
        vars["CTRP"][c] = {}
        for m in months:
            vars["CTRP"][c][m] = pulp.LpVariable(
                f"CTRP_{c}_{m}", lowBound=0, cat="Continuous"
            )

    # --- CTRP_comp[c][m]: непрерывная, кумулятивный TRP конкурентов за период РК ---
    vars["CTRP_comp"] = {}
    for c in cat_names:
        vars["CTRP_comp"][c] = {}
        for m in months:
            vars["CTRP_comp"][c][m] = pulp.LpVariable(
                f"CTRP_comp_{c}_{m}", lowBound=0, cat="Continuous"
            )

    # --- z[c][m]: бинарная, нарушение анализируемости при старте в m ---
    vars["z"] = {}
    for c in cat_names:
        vars["z"][c] = {}
        for m in months:
            vars["z"][c][m] = pulp.LpVariable(
                f"z_{c}_{m}", lowBound=0, upBound=1, cat="Binary"
            )

    # --- q[c][m][m']: бинарная, месяц m' «чист» перед стартом в m ---
    vars["q"] = {}
    for c in cat_names:
        vars["q"][c] = {}
        for m in range(4, 13):  # Только для m >= 4
            vars["q"][c][m] = {}
            for m_prime in range(m - 3, m):  # m-3, m-2, m-1
                vars["q"][c][m][m_prime] = pulp.LpVariable(
                    f"q_{c}_{m}_{m_prime}", lowBound=0, upBound=1, cat="Binary"
                )

    # --- f[c][m]: бинарная, месяц m принадлежит РК с нарушенной анализируемостью ---
    vars["f"] = {}
    for c in cat_names:
        vars["f"][c] = {}
        for m in months:
            vars["f"][c][m] = pulp.LpVariable(
                f"f_{c}_{m}", lowBound=0, upBound=1, cat="Binary"
            )

    # --- w[c][m][t]: бинарная, линеаризация x[c][m][t] * f[c][m] ---
    vars["w"] = {}
    for c in cat_names:
        vars["w"][c] = {}
        for m in months:
            vars["w"][c][m] = {}
            for t in trp_levels + [0]:
                vars["w"][c][m][t] = pulp.LpVariable(
                    f"w_{c}_{m}_{t}", lowBound=0, upBound=1, cat="Binary"
                )
                
    # --- single[c][m]: бинарная, определение одномесячных РК (для коррекции стоимостей TRP)
    vars["single"] = {}
    for c in cat_names:
        vars["single"][c] = {}
        for m in months:
            vars["single"][c][m] = pulp.LpVariable(
                f"single_{c}_{m}", lowBound=0, upBound=1, cat="Binary"
            )
                
    return vars

# =========================================================================
# СВЯЗУЮЩИЕ ОГРАНИЧЕНИЯ
# =========================================================================

def add_linking_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    trp_levels: List,
    vars: Dict[str, Dict]
) -> pulp.LpProblem:
    """
    Добавление связующих ограничений на переменные x, y, s, e, single
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param trp_levels: Список возможных уровней TRP
    :param vars: Словарь с переменными задачи оптимизации
    
    :return: Обновленная на новые ограничения задача оптимизации
    """
    cat_names = list(categories.keys())

    for category in cat_names:
        for month in months:
            # --- Ограничение №1: Ровно один уровень TRP выбран ---
            model += (
                pulp.lpSum(vars["x"][category][month][trp] for trp in trp_levels + [0]) == 1,
                f"C1_unique_trp_{category}_{month}"
            )

            # --- Ограничение №2: связь переменных y и x ---
            model += (
                pulp.lpSum(vars["x"][category][month][trp] for trp in trp_levels) == vars["y"][category][month],
                f"C2_link_xy_{category}_{month}"
            )
            
            # --- Ограничение №3: связть переменных s и y (отдельная обработка первого месяца плана)
            if month > min(months):
                model += (
                    vars["s"][category][month] >= vars["y"][category][month] - vars["y"][category][month - 1],
                    f"C3_start_lb_{category}_{month}"
                )
                
                model += (
                    vars["s"][category][month] <= vars["y"][category][month],
                    f"C3_start_ub1_{category}_{month}"
                )
                
                model += (
                    vars["s"][category][month] <= 1 - vars["y"][category][month - 1],
                    f"C3_start_ub2_{category}_{month}"
                )
            else:
                model += (
                    vars["s"][category][1] == vars["y"][category][1],
                    f"C3_start_m1_{category}"
                )
            
            # --- Ограничение №4: связь переменных e и y (отдельная обработка последнего месяца плана)
            if month < max(months):
                model += (
                    vars["e"][category][month] >= vars["y"][category][month] - vars["y"][category][month + 1],
                    f"C4_end_lb_{category}_{month}"
                )
                
                model += (
                    vars["e"][category][month] <= vars["y"][category][month],
                    f"C4_end_ub1_{category}_{month}"
                )

                model += (
                    vars["e"][category][month] <= 1 - vars["y"][category][month + 1],
                    f"C4_end_ub2_{category}_{month}"
                )
            else:
                model += (
                    vars["e"][category][month] == vars["y"][category][month],
                    f"C4_end_{category}_{month}"
                )
                
            # --- Ограничение №5: связь переменных single, s, e
            model += (
                vars["single"][category][month] >= vars["s"][category][month] + vars["e"][category][month] - 1,
                f"single_lb_{category}_{month}"
            )

            model += (
                vars["single"][category][month] <= vars["s"][category][month],
                f"single_ub_s_{category}_{month}"
            )

            model += (
                vars["single"][category][month] <= vars["e"][category][month],
                f"single_ub_e_{category}_{month}"
            )
        
    return model

# =========================================================================
# КУМУЛЯТИВНЫЙ TRP
# =========================================================================

def _tau(vars: Dict[str, Dict], trp_levels: List, category: str, month: int) -> pulp.lpSum:
    """
    Возвращает линейное выражение для фактического TRP в конкретной категории и месяце
    
    :param vars: Словарь с переменными, подвязанными с TRP (x[c][m][t])
    :param trp_levels: Список уровней TRP
    :param month: Номер интересующего месяца
    :param trp: Интересующий уровень TRP
    
    :return: Выражение для фактического TRP в категории и месяце
    """
    
    return pulp.lpSum(trp * vars["x"][category][month][trp] for trp in trp_levels + [0])

def add_cumulative_trp_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List,
    trp_levels: List,
    vars: Dict[str, Dict],
    competitors: Dict[str, Dict],
    big_M: float) -> pulp.LpProblem:
    """
    Добавляет ограничения для кумулятивного TRP (CTRP) и кумулятивного TRP конкурентов (CTRP_comp).
    Логика: CTRP накапливается внутри непрерывной РК (при старте равняется TRP первого месяца, при отсутсвии РК - 0)
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param months: Список месяцев планирования
    :param trp_levels: Список возможных уровней TRP
    :param vars: Словарь с переменными задачи оптимизации
    :param competitors: Словарь с информацией по месячным TRP конкурентов по категориям
    :param big_M: Большая константа для ограничений
    
    :return: Обновленная на новые ограничения задача оптимизации
    """
    
    cat_names = list(categories.keys())

    for category in cat_names:
        for month in months:
            tau_m =  _tau(vars, trp_levels, category, month)
            comp_trp_m = _get_competitor_trp(categories, competitors, category, month)
            
            # Отдельная обработка первого месяца планирования
            if month == min(months):
                # TRP категории
                # --- CTRP: если идет РК (y=1), то CTRP[m] = tau[m] ---
                model += (
                    vars["CTRP"][category][month] <= tau_m + big_M * (1 - vars["y"][category][month]),
                    f"CTRP_m1_ub_{category}"
                )
                
                model += (
                    vars["CTRP"][category][month] >= tau_m - big_M * (1 - vars["y"][category][month]),
                    f"CTRP_m1_lb_{category}"
                )
                
                # --- CTRP: если нет РК (y=0), то CTRP[m] = 0 ---
                model += (
                    vars["CTRP"][category][month] <= big_M * vars["y"][category][month],
                    f"CTRP_m1_zero_{category}"
                )
                
                # print(f"category={category}, month={month}")
                # print(f"comp_trp_m type: {type(comp_trp_m)}, value: {comp_trp_m}")
                # print(f"big_M type: {type(big_M)}, value: {big_M}")
                # print(f"y type: {type(vars['y'][category][month])}")
                # print(f"CTRP_comp type: {type(vars['CTRP_comp'][category][month])}")
                
                # TRP конкурентов (все аналогично)
                model += (
                    vars["CTRP_comp"][category][month] <= comp_trp_m + big_M * (1 - vars["y"][category][month]),
                    f"CTRPcomp_m1_ub_{category}"
                )
                
                model += (
                    vars["CTRP_comp"][category][month] >= comp_trp_m - big_M * (1 - vars["y"][category][month]),
                    f"CTRPcomp_m1_lb_{category}"
                )
                
                model += (
                    vars["CTRP_comp"][category][month] <= big_M * vars["y"][category][month],
                    f"CTRPcomp_m1_zero_{category}"
                )
            else:
                s_cm = vars["s"][category][month]
                y_cm = vars["y"][category][month]
                ctrp_prev = vars["CTRP"][category][month - 1]
                ctrp_cur = vars["CTRP"][category][month]
                ctrp_comp_prev = vars["CTRP_comp"][category][month - 1]
                ctrp_comp_cur = vars["CTRP_comp"][category][month]
                
                # TRP категории
                # --- CTRP: если продолжение (s=0, y=1), то CTRP[m] = CTRP[m-1] + tau[m] ---
                model += (
                    ctrp_cur <= ctrp_prev + tau_m + big_M * s_cm,
                    f"CTRP_cont_ub_{category}_{month}"
                )
                
                model += (
                    ctrp_cur >= ctrp_prev + tau_m - big_M * s_cm - big_M * (1 - y_cm),
                    f"CTRP_cont_lb_{category}_{month}"
                )
                
                # --- CTRP: если старт (s=1), то CTRP[m] = tau[m] ---
                model += (
                    ctrp_cur <= tau_m + big_M * (1 - s_cm),
                    f"CTRP_start_ub_{category}_{month}"
                )
                
                model += (
                    ctrp_cur >= tau_m - big_M * (1 - s_cm) - big_M * (1 - y_cm),
                    f"CTRP_start_lb_{category}_{month}"
                )
                
                # --- CTRP: если нет РК (y=0), то CTRP[m] = 0 ---
                model += (
                    ctrp_cur <= big_M * y_cm,
                    f"CTRP_zero_{category}_{month}"
                )
                
                # TRP конкурентов (все аналогично)
                model += (
                    ctrp_comp_cur <= ctrp_comp_prev + comp_trp_m + big_M * s_cm,
                    f"CTRPcomp_cont_ub_{category}_{month}"
                )
                
                model += (
                    ctrp_comp_cur >= ctrp_comp_prev + comp_trp_m - big_M * s_cm - big_M * (1 - y_cm),
                    f"CTRPcomp_cont_lb_{category}_{month}"
                )
                
                model += (
                    ctrp_comp_cur <= comp_trp_m + big_M * (1 - s_cm),
                    f"CTRPcomp_start_ub_{category}_{month}"
                )
                
                model += (
                    ctrp_comp_cur >= comp_trp_m - big_M * (1 - s_cm) - big_M * (1 - y_cm),
                    f"CTRPcomp_start_lb_{category}_{month}"
                )
                
                model += (
                    ctrp_comp_cur <= big_M * y_cm,
                    f"CTRPcomp_zero_{category}_{month}"
                )

    return model

# =========================================================================
# БЮДЖЕТ С УЧЕТОМ КОРРЕКЦИЙ
# =========================================================================

def add_dynamic_cost_constraints(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    months: List[int],
    trp_levels: List[int],
    costs: Dict[str, Dict[int, float]],
    vars: Dict[str, Dict]
) -> pulp.LpProblem:
    """
    Добавляет ограничения для вычисления бюджета с динамическими множителями.
    Создаёт переменную budget[c][m] и связывает её с tau и состоянием месяца.
    
    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param trp_levels: Список возможных уровней TRP
    :param costs: Словарь со стоимостями 1 TRP по категориям за каждый месяц
    :param months: Список месяцев планирования
    :param vars: Словарь с переменными задачи оптимизации

    :return: Задача оптимизации с добавленными ограничениями
    """
    
    # Большая константа для ограничений
    big_M_budget = max(trp_levels) * max(max(costs[category].values()) for category in categories) * 1.05
    
    # Создаём переменные budget[c][m]
    vars["budget"] = {}
    for category in categories:
        vars["budget"][category] = {}
        for month in months:
            vars["budget"][category][month] = pulp.LpVariable(
                f"budget_{category}_{month}", lowBound=0, cat="Continuous"
            )

    for category in categories:
        # Корректирующие множители стоимостей
        mults = _get_cost_multipliers(categories[category])

        for month in months:
            base_cost = costs[category][month]
            tau = pulp.lpSum(trp * vars["x"][category][month][trp] for trp in trp_levels + [0])

            # Три варианта итоговой стоимости TRP:
            cost_single = base_cost * mults["single"]
            cost_multi_first = base_cost * mults["multi_first"]
            cost_cont = base_cost * mults["multi_cont"]

            # tau в каждом состоянии:
            tau_expr = pulp.lpSum(trp * vars["x"][category][month][trp] for trp in trp_levels + [0])

            # Состояние 1: одномесячная РК (single = 1)
            budget_if_single = cost_single * tau_expr
            # Состояние 2: первый месяц многомесячной (s = 1, single = 0)
            budget_if_multi_first = cost_multi_first * tau_expr
            # Состояние 3: продолжение (y = 1, s = 0)
            budget_if_cont = cost_cont * tau_expr

            single = vars["single"][category][month]
            s = vars["s"][category][month]
            y = vars["y"][category][month]
            multi_first = s - single  # = 1 только при старте многомесячной РК
            cont = y - s              # = 1 только при продолжении

            # Связующие ограничения
            model += (
                vars["budget"][category][month] >= budget_if_single - big_M_budget * (1 - single),
                f"budget_single_lb_{category}_{month}"
            )
 
            model += (
                vars["budget"][category][month] <= budget_if_single + big_M_budget * (1 - single),
                f"budget_single_ub_{category}_{month}"
            )

            model += (
                vars["budget"][category][month] >= budget_if_multi_first - big_M_budget * (1 - s + single) - big_M_budget * (1 - y),
                f"budget_multi_first_lb_{category}_{month}"
            )
            
            model += (
                vars["budget"][category][month] <= budget_if_multi_first + big_M_budget * (1 - s + single),
                f"budget_multi_first_ub_{category}_{month}"
            )

            model += (
                vars["budget"][category][month] >= budget_if_cont - big_M_budget * s - big_M_budget * (1 - y),
                f"budget_cont_lb_{category}_{month}"
            )
            
            model += (
                vars["budget"][category][month] <= budget_if_cont + big_M_budget * s,
                f"budget_cont_ub_{category}_{month}"
            )

            model += (
                vars["budget"][category][month] <= big_M_budget * y,
                f"budget_zero_{category}_{month}"
            )

    return model

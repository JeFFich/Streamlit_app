"""
Создание переменных и связующих ограничений для CP-SAT модели.
"""

from ortools.sat.python import cp_model
from typing import Dict, List, Tuple

from OptimizerNew.process_data import _get_competitor_trp, _get_cost_multipliers

# Масштабирование: CP-SAT работает только с целыми числами.
# Бюджет и выручку масштабируем (делим на 1000), чтобы уместиться в int64.
BUDGET_SCALE = 1000  # budget в тысячах рублей

def create_variables(
    model: cp_model.CpModel,
    categories: Dict[str, Dict],
    months: List[int],
    trp_levels: List[int]
) -> Dict:
    """
    Создаёт все переменные CP-SAT модели.

    :return: Словарь со всеми переменными
    """
    cat_names = list(categories.keys())
    v = {}

    # --- x[c][m][t]: BoolVar, уровень TRP t выбран в категории c в месяце m ---
    v["x"] = {}
    for c in cat_names:
        v["x"][c] = {}
        for m in months:
            v["x"][c][m] = {}
            for t in trp_levels + [0]:
                v["x"][c][m][t] = model.NewBoolVar(f"x_{c}_{m}_{t}")

    # --- y[c][m]: BoolVar, РК активна ---
    v["y"] = {}
    for c in cat_names:
        v["y"][c] = {}
        for m in months:
            v["y"][c][m] = model.NewBoolVar(f"y_{c}_{m}")

    # --- s[c][m]: BoolVar, старт РК ---
    v["s"] = {}
    for c in cat_names:
        v["s"][c] = {}
        for m in months:
            v["s"][c][m] = model.NewBoolVar(f"s_{c}_{m}")

    # --- e[c][m]: BoolVar, конец РК ---
    v["e"] = {}
    for c in cat_names:
        v["e"][c] = {}
        for m in months:
            v["e"][c][m] = model.NewBoolVar(f"e_{c}_{m}")

    # --- single[c][m]: BoolVar, одномесячная РК ---
    v["single"] = {}
    for c in cat_names:
        v["single"][c] = {}
        for m in months:
            v["single"][c][m] = model.NewBoolVar(f"single_{c}_{m}")

    # --- tau[c][m]: IntVar, фактический TRP в месяце ---
    v["tau"] = {}
    for c in cat_names:
        v["tau"][c] = {}
        for m in months:
            v["tau"][c][m] = model.NewIntVar(0, max(trp_levels), f"tau_{c}_{m}")

    # --- ctrp[c][m]: IntVar, кумулятивный TRP текущей РК ---
    max_dur = max(cat["max_duration"] for cat in categories.values())
    v["ctrp"] = {}
    for c in cat_names:
        v["ctrp"][c] = {}
        for m in months:
            v["ctrp"][c][m] = model.NewIntVar(0, max_dur * max(trp_levels), f"ctrp_{c}_{m}")

    # --- ctrp_comp[c][m]: IntVar, кумулятивный TRP конкурентов за период РК ---
    v["ctrp_comp"] = {}
    for c in cat_names:
        v["ctrp_comp"][c] = {}
        max_comp = max_dur * max(
            _get_competitor_trp(categories, {}, c, m) for m in months
        ) if False else 200000  # Верхняя граница
        for m in months:
            v["ctrp_comp"][c][m] = model.NewIntVar(0, 200000, f"ctrp_comp_{c}_{m}")

    # --- budget[c][m]: IntVar, бюджет месяца (в тысячах руб.) ---
    v["budget"] = {}
    for c in cat_names:
        v["budget"][c] = {}
        for m in months:
            # Максимальный бюджет за месяц ≈ max_trp * max_cost * max_mult / SCALE
            max_budget_month = max(trp_levels) * 300000 * 2 // BUDGET_SCALE
            v["budget"][c][m] = model.NewIntVar(0, max_budget_month, f"budget_{c}_{m}")

    # --- Переменные анализируемости ---
    v["z"] = {}
    for c in cat_names:
        v["z"][c] = {}
        for m in months:
            v["z"][c][m] = model.NewBoolVar(f"z_{c}_{m}")

    v["q"] = {}
    for c in cat_names:
        v["q"][c] = {}
        for m in range(4, 13):
            v["q"][c][m] = {}
            for m_prime in range(m - 3, m):
                v["q"][c][m][m_prime] = model.NewBoolVar(f"q_{c}_{m}_{m_prime}")

    v["f"] = {}
    for c in cat_names:
        v["f"][c] = {}
        for m in months:
            v["f"][c][m] = model.NewBoolVar(f"f_{c}_{m}")

    return v

def add_linking_constraints(
    model: cp_model.CpModel,
    categories: Dict[str, Dict],
    months: List[int],
    trp_levels: List[int],
    v: Dict
) -> None:
    """
    Добавляет связующие ограничения: x↔y, y↔s, y↔e, s+e↔single, tau=sum(t*x).
    """
    cat_names = list(categories.keys())

    for c in cat_names:
        for m in months:
            # C1: Ровно один уровень TRP выбран
            model.AddExactlyOne(v["x"][c][m][t] for t in trp_levels + [0])

            # C2: y = 1 <=> выбран ненулевой TRP
            model.Add(sum(v["x"][c][m][t] for t in trp_levels) == 1).OnlyEnforceIf(v["y"][c][m])
            model.Add(v["x"][c][m][0] == 1).OnlyEnforceIf(v["y"][c][m].Not())

            # tau = sum(t * x[t])
            model.Add(
                v["tau"][c][m] == sum(t * v["x"][c][m][t] for t in trp_levels + [0])
            )

        # C3: Определение старта s
        # s[1] = y[1]
        model.Add(v["s"][c][months[0]] == v["y"][c][months[0]])
        for m in months[1:]:
            # s[m] = 1 <=> y[m]=1 AND y[m-1]=0
            model.AddBoolAnd([v["y"][c][m], v["y"][c][m - 1].Not()]).OnlyEnforceIf(v["s"][c][m])
            model.AddBoolOr([v["y"][c][m].Not(), v["y"][c][m - 1]]).OnlyEnforceIf(v["s"][c][m].Not())

        # C4: Определение конца e
        for m in months[:-1]:
            # e[m] = 1 <=> y[m]=1 AND y[m+1]=0
            model.AddBoolAnd([v["y"][c][m], v["y"][c][m + 1].Not()]).OnlyEnforceIf(v["e"][c][m])
            model.AddBoolOr([v["y"][c][m].Not(), v["y"][c][m + 1]]).OnlyEnforceIf(v["e"][c][m].Not())
        # e[12] = y[12]
        model.Add(v["e"][c][months[-1]] == v["y"][c][months[-1]])

        # C5: single = s AND e
        for m in months:
            model.AddBoolAnd([v["s"][c][m], v["e"][c][m]]).OnlyEnforceIf(v["single"][c][m])
            model.AddBoolOr([v["s"][c][m].Not(), v["e"][c][m].Not()]).OnlyEnforceIf(v["single"][c][m].Not())

def add_cumulative_trp_constraints(
    model: cp_model.CpModel,
    categories: Dict[str, Dict],
    months: List[int],
    trp_levels: List[int],
    v: Dict,
    competitors: Dict[str, Dict]
) -> None:
    """
    Кумулятивный TRP и TRP конкурентов. Без Big-M — через OnlyEnforceIf.
    """
    cat_names = list(categories.keys())

    for c in cat_names:
        for m in months:
            comp_trp_m = int(_get_competitor_trp(categories, competitors, c, m))

            if m == months[0]:
                # Первый месяц: ctrp = tau если y=1, иначе 0
                model.Add(v["ctrp"][c][m] == v["tau"][c][m]).OnlyEnforceIf(v["y"][c][m])
                model.Add(v["ctrp"][c][m] == 0).OnlyEnforceIf(v["y"][c][m].Not())
                model.Add(v["ctrp_comp"][c][m] == comp_trp_m).OnlyEnforceIf(v["y"][c][m])
                model.Add(v["ctrp_comp"][c][m] == 0).OnlyEnforceIf(v["y"][c][m].Not())
            else:
                # y=0: ctrp = 0
                model.Add(v["ctrp"][c][m] == 0).OnlyEnforceIf(v["y"][c][m].Not())
                model.Add(v["ctrp_comp"][c][m] == 0).OnlyEnforceIf(v["y"][c][m].Not())

                # s=1 (старт): ctrp = tau
                model.Add(v["ctrp"][c][m] == v["tau"][c][m]).OnlyEnforceIf(v["s"][c][m])
                model.Add(v["ctrp_comp"][c][m] == comp_trp_m).OnlyEnforceIf(v["s"][c][m])

                # Продолжение (y=1, s=0): ctrp = ctrp[m-1] + tau[m]
                cont = model.NewBoolVar(f"cont_{c}_{m}")
                model.AddBoolAnd([v["y"][c][m], v["s"][c][m].Not()]).OnlyEnforceIf(cont)
                model.AddBoolOr([v["y"][c][m].Not(), v["s"][c][m]]).OnlyEnforceIf(cont.Not())

                model.Add(
                    v["ctrp"][c][m] == v["ctrp"][c][m - 1] + v["tau"][c][m]
                ).OnlyEnforceIf(cont)
                model.Add(
                    v["ctrp_comp"][c][m] == v["ctrp_comp"][c][m - 1] + comp_trp_m
                ).OnlyEnforceIf(cont)

def add_dynamic_cost_constraints(
    model: cp_model.CpModel,
    categories: Dict[str, Dict],
    months: List[int],
    trp_levels: List[int],
    costs: Dict[str, Dict[int, float]],
    v: Dict
) -> None:
    """
    Точный расчёт бюджета с динамическими множителями через OnlyEnforceIf.
    Бюджет хранится в тысячах рублей (деление на BUDGET_SCALE).
    """
    
    cat_names = list(categories.keys())

    for c in cat_names:
        mults = _get_cost_multipliers(categories[c])

        for m in months:
            base_cost = costs[c][m]

            # Предвычисляем стоимость для каждого уровня TRP в каждом состоянии (в тыс. руб.)
            cost_single = int(round(base_cost * mults["single"] / BUDGET_SCALE))
            cost_mf = int(round(base_cost * mults["multi_first"] / BUDGET_SCALE))
            cost_cont = int(round(base_cost * mults["multi_cont"] / BUDGET_SCALE))

            # multi_first = s AND NOT single
            mf = model.NewBoolVar(f"mf_{c}_{m}")
            model.AddBoolAnd([v["s"][c][m], v["single"][c][m].Not()]).OnlyEnforceIf(mf)
            model.AddBoolOr([v["s"][c][m].Not(), v["single"][c][m]]).OnlyEnforceIf(mf.Not())

            # continuation = y AND NOT s
            cont = model.NewBoolVar(f"cont_b_{c}_{m}")
            model.AddBoolAnd([v["y"][c][m], v["s"][c][m].Not()]).OnlyEnforceIf(cont)
            model.AddBoolOr([v["y"][c][m].Not(), v["s"][c][m]]).OnlyEnforceIf(cont.Not())

            # budget[c][m] = cost_state * tau[c][m] / BUDGET_SCALE (уже учтено в cost_state)
            # Используем AddMultiplicationEquality: budget = cost * tau
            # Но cost зависит от состояния → 4 случая

            # Случай 1: y=0 → budget=0
            model.Add(v["budget"][c][m] == 0).OnlyEnforceIf(v["y"][c][m].Not())

            # Случай 2: single=1 → budget = cost_single * tau
            # CP-SAT: AddMultiplicationEquality(target, [var1, var2]) для двух переменных
            # Но cost_single — константа, поэтому просто linear:
            model.Add(
                v["budget"][c][m] == cost_single * v["tau"][c][m]
            ).OnlyEnforceIf(v["single"][c][m])

            # Случай 3: multi_first → budget = cost_mf * tau
            model.Add(
                v["budget"][c][m] == cost_mf * v["tau"][c][m]
            ).OnlyEnforceIf(mf)

            # Случай 4: continuation → budget = cost_cont * tau
            model.Add(
                v["budget"][c][m] == cost_cont * v["tau"][c][m]
            ).OnlyEnforceIf(cont)

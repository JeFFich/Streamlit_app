"""
Содержательные (логические) ограничения задачи оптимизации медиаплана.
"""

from ortools.sat.python import cp_model
from typing import Dict, List

from OptimizerNew.process_data import _get_cost_multipliers
from OptimizerNew.variables import BUDGET_SCALE


def _add_vertical_campaign_count_constraints(
    model: cp_model.CpModel, 
    verticals: Dict, 
    categories: Dict, 
    months: List, 
    v: Dict
) -> None:
    for vertical, info in verticals.items():
        cats_in_v = [c for c, ci in categories.items() if ci["vertical"] == vertical]
        total = sum(v["s"][c][m] for c in cats_in_v for m in months)
        model.Add(total >= info["min_campaigns"])
        model.Add(total <= info["max_campaigns"])

def _add_category_campaign_count_constraints(
    model: cp_model.CpModel, 
    categories: Dict, 
    months: List, 
    v: Dict
) -> None:
    for c, info in categories.items():
        n_c = sum(v["s"][c][m] for m in months)
        model.Add(n_c >= info["min_campaigns"])
        model.Add(n_c <= info["max_campaigns"])

def _add_duration_constraints(
    model: cp_model.CpModel, 
    categories: Dict, 
    months: List, 
    v: Dict
) -> None:
    for c, info in categories.items():
        min_dur = info["min_duration"]
        max_dur = info["max_duration"]

        for m in months:
            # --- Минимальная продолжительность ---
            # Если старт в m, то y[m+d]=1 для d=0..min_dur-1
            for d in range(min_dur):
                if m + d <= max(months):
                    model.AddImplication(v["s"][c][m], v["y"][c][m + d])

            # --- Запрет позднего старта ---
            if m + min_dur - 1 > max(months):
                model.Add(v["s"][c][m] == 0)

            # --- Максимальная продолжительность ---
            # Если старт в m, то e[m'] = 1 для какого-то m' в [m, m+max_dur-1]
            # Эквивалентно: если старт в m, то в пределах max_dur месяцев РК закончится
            # s[m]=1 → e[m] + e[m+1] + ... + e[m+max_dur-1] >= 1
            end_candidates = [
                v["e"][c][m + d] 
                for d in range(max_dur) 
                if m + d <= max(months)
            ]
            if end_candidates:
                # Если старт в m → хотя бы один конец в окне [m, m+max_dur-1]
                model.Add(sum(end_candidates) >= 1).OnlyEnforceIf(v["s"][c][m])

def _add_vertical_budget_constraints(
    model: cp_model.CpModel, 
    categories: Dict, 
    verticals: Dict, 
    months: List, 
    v: Dict
) -> None:
    for vertical, info in verticals.items():
        cats_in_v = [c for c, ci in categories.items() if ci["vertical"] == vertical]
        total_budget = sum(v["budget"][c][m] for c in cats_in_v for m in months)
        max_b = info["max_budget"] // BUDGET_SCALE
        model.Add(total_budget <= max_b)

def _add_category_budget_constraints(
    model: cp_model.CpModel, 
    categories: Dict, 
    months: List, 
    v: Dict
) -> None:
    for c, info in categories.items():
        total_budget = sum(v["budget"][c][m] for m in months)
        min_b = info["min_budget"] // BUDGET_SCALE
        max_b = info["max_budget"] // BUDGET_SCALE
        model.Add(total_budget >= min_b)
        model.Add(total_budget <= max_b)

def _add_min_trp_constraints(
    model: cp_model.CpModel, 
    categories: Dict, 
    months: List, 
    v: Dict
) -> None:
    """CTRP >= min_trp когда e=1 (конец РК)."""
    for c, info in categories.items():
        min_trp = info["min_trp"]
        for m in months:
            model.Add(v["ctrp"][c][m] >= min_trp).OnlyEnforceIf(v["e"][c][m])

def _add_max_trp_per_campaign_constraints(
    model: cp_model.CpModel, 
    categories: Dict, 
    months: List, 
    v: Dict,
    max_trp: int
) -> None:
    """CTRP <= max_trp всегда."""
    for c in categories:
        for m in months:
            model.Add(v["ctrp"][c][m] <= max_trp)

def _add_sov_constraints(
    model: cp_model.CpModel, 
    categories: Dict, 
    months: List, 
    v: Dict
) -> None:
    """SOV: (1-sov_min)*CTRP >= sov_min*CTRP_comp, активно при e=1."""
    for c, info in categories.items():
        sov_min = info["min_sov"]
        if sov_min <= 0:
            continue
        # Масштабируем до целых: (1-sov)*1000 * ctrp >= sov*1000 * ctrp_comp
        sov_min_int = int(round(sov_min * 1000))
        sov_comp_int = 1000 - sov_min_int

        for m in months:
            # sov_comp_int * ctrp >= sov_min_int * ctrp_comp (только при e=1)
            model.Add(
                sov_comp_int * v["ctrp"][c][m] >= sov_min_int * v["ctrp_comp"][c][m]
            ).OnlyEnforceIf(v["e"][c][m])

def _add_vertical_min_trp_constraints(
    model: cp_model.CpModel, 
    categories: Dict, 
    verticals: Dict,
    months: List, 
    trp_levels: List, 
    v: Dict
) -> None:
    for vertical, info in verticals.items():
        if "min_total_trp" not in info:
            continue
        cats_in_v = [c for c, ci in categories.items() if ci["vertical"] == vertical]
        total_trp = sum(v["tau"][c][m] for c in cats_in_v for m in months)
        model.Add(total_trp >= info["min_total_trp"])

def _add_mandatory_start_constraints(
    model: cp_model.CpModel, 
    categories: Dict, 
    months: List, 
    v: Dict
) -> None:
    for c, info in categories.items():
        mandatory = info.get("start_months", [])
        strict = info.get("strict_start", False)

        for m in mandatory:
            model.Add(v["y"][c][m] == 1)

        if strict and mandatory:
            for m in months:
                if m not in mandatory:
                    model.Add(v["s"][c][m] == 0)

def _add_overlap_exclusion_constraints(
    model: cp_model.CpModel, 
    categories: Dict,
    months: List, 
    v: Dict, 
    overlap_map: Dict
) -> None:
    added_pairs = set()
    for c in categories:
        for c_prime in overlap_map[c]:
            pair = tuple(sorted([c, c_prime]))
            if pair in added_pairs:
                continue
            added_pairs.add(pair)
            for m in months:
                model.Add(v["y"][c][m] + v["y"][c_prime][m] <= 1)

def _add_analyzability_constraints(
    model: cp_model.CpModel, 
    categories: Dict, 
    months: List, 
    v: Dict, 
    overlap_map: Dict
) -> None:
    """Нежёсткое ограничение анализируемости."""
    cat_names = list(categories.keys())

    for c in cat_names:
        overlap_cats = overlap_map[c]

        for m in months:
            if m <= 3:
                model.Add(v["z"][c][m] == 0)
            else:
                # q[c][m][m'] <= 1 - y[c''][m'] для всех пересекающихся
                for m_prime in range(m - 3, m):
                    for c_prime in overlap_cats:
                        model.AddImplication(v["q"][c][m][m_prime], v["y"][c_prime][m_prime].Not())

                # sum(q) >= s - z
                model.Add(
                    sum(v["q"][c][m][m_prime] for m_prime in range(m - 3, m))
                    >= v["s"][c][m] - v["z"][c][m]
                )

        # Связь f (штраф «размазывается» на все месяцы РК)
        for m in months:
            # f <= y
            model.AddImplication(v["f"][c][m], v["y"][c][m])
            # f >= z (в месяце старта)
            model.AddImplication(v["z"][c][m], v["f"][c][m])

        for m in months[1:]:
            # Наследование: если продолжение и предыдущий месяц со штрафом
            # f[m] >= f[m-1] + y[m] - 1 - s[m]  →  f[m] >= f[m-1] при y=1, s=0
            cont = model.NewBoolVar(f"anal_cont_{c}_{m}")
            model.AddBoolAnd([v["y"][c][m], v["s"][c][m].Not()]).OnlyEnforceIf(cont)
            model.AddBoolOr([v["y"][c][m].Not(), v["s"][c][m]]).OnlyEnforceIf(cont.Not())
            # Если продолжение и f[m-1]=1 → f[m]=1
            both = model.NewBoolVar(f"anal_both_{c}_{m}")
            model.AddBoolAnd([cont, v["f"][c][m - 1]]).OnlyEnforceIf(both)
            model.AddBoolOr([cont.Not(), v["f"][c][m - 1].Not()]).OnlyEnforceIf(both.Not())
            model.AddImplication(both, v["f"][c][m])

            # Сброс при старте новой РК без нарушения
            # f[m] <= z[m] + (1-s[m]) + (1-y[m])  → при s=1, y=1: f[m] <= z[m]
            start_no_z = model.NewBoolVar(f"snz_{c}_{m}")
            model.AddBoolAnd([v["s"][c][m], v["z"][c][m].Not()]).OnlyEnforceIf(start_no_z)
            model.AddBoolOr([v["s"][c][m].Not(), v["z"][c][m]]).OnlyEnforceIf(start_no_z.Not())
            model.AddImplication(start_no_z, v["f"][c][m].Not())

def add_logical_constraints(
    model: cp_model.CpModel,
    categories: Dict,
    verticals: Dict,
    months: List,
    trp_levels: List,
    costs: Dict,
    v: Dict,
    overlap_map: Dict,
    max_trp: int
) -> None:
    """Внешняя функция для добавления всех содержательных ограничений."""
    
    # Ограничение на число стартов, длительность РК и обязательные месяцы
    _add_vertical_campaign_count_constraints(model, verticals, categories, months, v)
    _add_category_campaign_count_constraints(model, categories, months, v)
    _add_mandatory_start_constraints(model, categories, months, v)
    _add_duration_constraints(model, categories, months, v)
    
    # Ограничения на бюджеты
    _add_vertical_budget_constraints(model, categories, verticals, months, v)
    _add_category_budget_constraints(model, categories, months, v)
    
    # Ограничения на TRP и SOV
    _add_min_trp_constraints(model, categories, months, v)
    _add_max_trp_per_campaign_constraints(model, categories, months, v, max_trp)
    _add_sov_constraints(model, categories, months, v)
    _add_vertical_min_trp_constraints(model, categories, verticals, months, trp_levels, v)
    
    # Ограничения анализируемости
    _add_overlap_exclusion_constraints(model, categories, months, v, overlap_map)
    _add_analyzability_constraints(model, categories, months, v, overlap_map)
    
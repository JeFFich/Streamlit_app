"""
Целевая функция: максимизация выручки со штрафом за неанализируемость.
"""

from ortools.sat.python import cp_model
from typing import Dict, List

from OptimizerNew.process_data import _get_revenue


def _compute_avg_revenue_at_trp1500(
    categories: Dict[str, Dict],
    verticals: Dict[str, Dict],
    forecast_dict: Dict[str, Dict],
    months: List[int]
) -> Dict[str, float]:
    """
    Функция для расчета средней месячной выручки по всем категориям планирования в вертикали при TRP=1500.
    Используется как базовая единица штрафа за неравномерность покрытия
    """
    
    avg_rev = {}
    for v_name in verticals:
        cats_in_v = [c for c, ci in categories.items() if ci["vertical"] == v_name]
        if not cats_in_v:
            avg_rev[v_name] = 0.0
            continue

        total = 0.0
        count = 0
        for c in cats_in_v:
            for m in months:
                rev = _get_revenue(forecast_dict, c, m, 1500)
                total += rev * categories[c]['season'][m]
                count += 1
        avg_rev[v_name] = total / count if count > 0 else 0.0

    return avg_rev

def add_coverage_uniformity_penalty(
    model: cp_model.CpModel,
    categories: Dict[str, Dict],
    verticals: Dict[str, Dict],
    forecast_dict: Dict[str, Dict],
    months: List[int],
    v: Dict,
    objective_terms: List,
    penalty_weight: float = 1.0
) -> None:
    """
    Квадратичный штраф за длину свободных окон между РК в вертикали (чтобы обеспечить большую равномерность планирования).
    Пустые вертикали (без единой запланированной РК) НЕ штрафуются
    """
    
    avg_rev_per_vert = _compute_avg_revenue_at_trp1500(
        categories, verticals, forecast_dict, months
    )

    n_months = len(months)
    extended_indices = list(range(2 * n_months))
    squares_table = [i * i for i in range(n_months + 1)]

    for v_name in verticals:
        cats_in_v = [c for c, ci in categories.items() if ci["vertical"] == v_name]
        if not cats_in_v:
            continue

        base_penalty = avg_rev_per_vert[v_name] * penalty_weight
        if base_penalty <= 0:
            continue

        # --- active_v[m]: вертикаль активна в месяце m ---
        active_v = {}
        for m in months:
            active_v[m] = model.NewBoolVar(f"active_vert_{v_name}_{m}")
            model.AddMaxEquality(active_v[m], [v["y"][c][m] for c in cats_in_v])

        # --- vert_active: вертикаль активна хотя бы в одном месяце года ---
        vert_active = model.NewBoolVar(f"vert_active_{v_name}")
        model.AddMaxEquality(vert_active, [active_v[m] for m in months])

        # --- gap_len для каждого индекса развёрнутого года ---
        gap_len = {}
        gap_sq = {}
        penalty_term = {}  # gap_sq, обнулённый при vert_active = 0

        for m_idx in extended_indices:
            real_month = months[m_idx % n_months]

            gap_len[m_idx] = model.NewIntVar(0, n_months, f"gap_{v_name}_{m_idx}")
            gap_sq[m_idx] = model.NewIntVar(
                0, n_months * n_months, f"gapsq_{v_name}_{m_idx}"
            )

            # Если месяц активен → gap = 0
            model.Add(gap_len[m_idx] == 0).OnlyEnforceIf(active_v[real_month])

            # Если месяц неактивен:
            if m_idx == 0:
                model.Add(gap_len[m_idx] == 1).OnlyEnforceIf(active_v[real_month].Not())
            else:
                model.Add(
                    gap_len[m_idx] == gap_len[m_idx - 1] + 1
                ).OnlyEnforceIf(active_v[real_month].Not())

            # Квадрат
            model.AddElement(gap_len[m_idx], squares_table, gap_sq[m_idx])

            # --- penalty_term = gap_sq * vert_active ---
            # Обнуляем штраф, если вертикаль полностью пустая
            penalty_term[m_idx] = model.NewIntVar(
                0, n_months * n_months, f"pen_{v_name}_{m_idx}"
            )
            model.Add(penalty_term[m_idx] == gap_sq[m_idx]).OnlyEnforceIf(vert_active)
            model.Add(penalty_term[m_idx] == 0).OnlyEnforceIf(vert_active.Not())

        # --- Штраф: сумма penalty_term по месяцам второго прохода ---
        second_pass_indices = extended_indices[n_months:]
        penalty_coef = int(round(base_penalty))
        for m_idx in second_pass_indices:
            objective_terms.append(-penalty_coef * penalty_term[m_idx])

def add_objective(
    model: cp_model.CpModel,
    categories: Dict[str, Dict],
    verticals: Dict[str, Dict],
    forecast_dict: Dict[str, Dict],
    months: List[int],
    trp_levels: List[int],
    v: Dict,
    penalty_alpha: float,
    coverage_penalty_weight: float = 0
) -> None:
    """
    Целевая функция: max sum(revenue * x) - alpha * sum(revenue * w),
    где w = x AND f (линеаризация штрафа).
    """
    cat_names = list(categories.keys())
    objective_terms = []

    for c in cat_names:
        for m in months:
            for t in trp_levels:
                rev = int(round(_get_revenue(forecast_dict, c, m, t)))
                if rev == 0:
                    continue

                # Положительная компонента: revenue * x
                objective_terms.append(rev * v["x"][c][m][t] * categories[c]['season'][m] ** 3)

                # Штраф: -alpha * revenue * (x AND f)
                # Линеаризуем: w = x AND f
                w = model.NewBoolVar(f"w_{c}_{m}_{t}")
                model.AddBoolAnd([v["x"][c][m][t], v["f"][c][m]]).OnlyEnforceIf(w)
                model.AddBoolOr([v["x"][c][m][t].Not(), v["f"][c][m].Not()]).OnlyEnforceIf(w.Not())

                penalty_val = int(round(penalty_alpha * rev))
                objective_terms.append(-penalty_val * w * categories[c]['season'][m] ** 3)

    # Штраф за неравномерность покрытия
    if coverage_penalty_weight > 0:
        add_coverage_uniformity_penalty(
            model, categories, verticals, forecast_dict, months,
            v, objective_terms, penalty_weight=coverage_penalty_weight
        )

    model.Maximize(sum(objective_terms))
    
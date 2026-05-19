"""
Целевая функция: максимизация выручки со штрафом за неанализируемость.
"""

from ortools.sat.python import cp_model
from typing import Dict, List

from OptimizerNew.process_data import _get_revenue


def add_objective(
    model: cp_model.CpModel,
    categories: Dict[str, Dict],
    forecast_dict: Dict[str, Dict],
    months: List[int],
    trp_levels: List[int],
    v: Dict,
    penalty_alpha: float
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
                objective_terms.append(rev * v["x"][c][m][t])

                # Штраф: -alpha * revenue * (x AND f)
                # Линеаризуем: w = x AND f
                w = model.NewBoolVar(f"w_{c}_{m}_{t}")
                model.AddBoolAnd([v["x"][c][m][t], v["f"][c][m]]).OnlyEnforceIf(w)
                model.AddBoolOr([v["x"][c][m][t].Not(), v["f"][c][m].Not()]).OnlyEnforceIf(w.Not())

                penalty_val = int(round(penalty_alpha * rev))
                objective_terms.append(-penalty_val * w)

    model.Maximize(sum(objective_terms))
    
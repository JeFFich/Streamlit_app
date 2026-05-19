"""
Вспомогательные геттеры
"""

from typing import Dict, List


def _compute_overlap_map(categories: Dict[str, Dict]) -> Dict:
    """
    Вычисляет для каждой категории множество пересекающихся категорий (по логкатам).
    """
    overlap_map = {}
    cat_names = list(categories.keys())

    for c in cat_names:
        overlap_map[c] = set()
        splits_c = set(categories[c]["logical_category"])
        for c_prime in cat_names:
            if c_prime == c:
                continue
            splits_c_prime = set(categories[c_prime]["logical_category"])
            if splits_c & splits_c_prime:
                overlap_map[c].add(c_prime)

    return overlap_map

def _get_competitor_trp(categories: Dict[str, Dict], competitors: Dict, category: str, month: int) -> float:
    comp_key = categories[category]["competitor_category"]
    return competitors.get(comp_key, {}).get(month, 0.0)

def _get_dtb(forecast_dict: Dict[str, Dict], category: str, month: int, trp: int) -> float:
    df = forecast_dict[category][month]
    row = df[df["TRP"] == trp]
    if row.empty or trp <= 0:
        return 0.0
    return float(row["DTB_pred"].iloc[0])

def _get_revenue(forecast_dict: Dict[str, Dict], category: str, month: int, trp: int) -> float:
    df = forecast_dict[category][month]
    row = df[df["TRP"] == trp]
    if row.empty or trp <= 0:
        return 0.0
    return float(row["revenue"].iloc[0])

def _get_cost_multipliers(category_info: Dict) -> Dict[str, float]:
    """Возвращает множители стоимости в зависимости от хроно и вертикали."""
    chrono = category_info.get("chrono", "20/10 s")
    vertical = category_info.get("vertical", "")

    if chrono == "40/20 s":
        return {
            "single": 1.54,
            "multi_first": 1.54,
            "multi_cont": 1.23
        }
    else:
        if vertical == "Goods":
            single_mult = 0.85
        else:
            single_mult = 0.79
        return {
            "single": single_mult,
            "multi_first": 0.83,
            "multi_cont": 0.69
        }
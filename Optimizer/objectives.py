import pulp
from typing import Dict, List

from Optimizer.process_data import _get_revenue

def add_objective(
    model: pulp.LpProblem,
    categories: Dict[str, Dict],
    forecast_dict: Dict[str, Dict],
    months: List,
    trp_levels: List,
    vars: Dict[str, Dict],
    penalty_alpha: float) -> pulp.LpProblem:
    """
    Целевая функция: максимизация выручки от плана, с учетом штрафа неанализируемости РК

    :param model: Задача оптимизации, которую пополняем ограничениями
    :param categories: Словарь с информацией по категориям
    :param forecast_dict: Словарь с прогнозами DTB и revenuе по категориям и месяцам
    :param months: Список месяцев планирования
    :param trp_levels: Список возможных уровней TRP
    :param vars: Словарь с переменными задачи оптимизации
    :param penalty_alpha: Коэффициент штрафа РК за неанализируемость
    
    :return: Модель с добавленной целевой функцией
    """
    
    catagory_names = list(categories.keys())

    # Сперва вводим линеаризацию произведения x * w
    for category in catagory_names:
        for month in months:
            for trp in trp_levels:
                model += (
                    vars["w"][category][month][trp] <= vars["x"][category][month][trp],
                    f"OBJ_w_le_x_{category}_{month}_{trp}"
                )
                
                model += (
                    vars["w"][category][month][trp] <= vars["f"][category][month],
                    f"OBJ_w_le_f_{category}_{month}_{trp}"
                )
                
                model += (
                    vars["w"][category][month][trp] >= vars["x"][category][month][trp] + vars["f"][category][month] - 1,
                    f"OBJ_w_ge_xf_{category}_{month}_{trp}"
                )

    # Строим положительную компоненту целевой функции
    revenue_term = pulp.lpSum(
        _get_revenue(forecast_dict, category, month, trp) * vars["x"][category][month][trp]
        for category in catagory_names
        for month in months
        for trp in trp_levels
    )

    # Строим отрицательную компоненту целевой функции
    penalty_term = pulp.lpSum(
        _get_revenue(forecast_dict, category, month, trp) * vars["w"][category][month][trp]
        for category in catagory_names
        for month in months
        for trp in trp_levels
    )

    # Добавляем саму целевую функцию в модель
    model += revenue_term - penalty_alpha * penalty_term, "Objective"
    
    return model

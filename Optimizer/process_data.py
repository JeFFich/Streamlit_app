from typing import Dict, List


def _compute_overlap_map(categories: Dict[str, Dict]) -> Dict:
        """
        Внутрення функция для вычисления по каждой категории множество пересекающихся с ним категорий
        (по логкатам).
        
        :param categories: Словарь с информацией по категориям (интересуют их логкаты)
        
        :return: Словарь со списком пересекающихся категорий
                Ключ: название категории
                Значение: множество пересекающихся категорий
        """
        overlap_map = {}
        
        # Список категорий
        cat_names = list(categories.keys())

        for c in cat_names:
            # Достаем все логкаты для текущей категории
            overlap_map[c] = set()
            splits_c = set(categories[c]["logical_category"])
            
            # Перебираем оставшиеся категории
            for c_prime in cat_names:
                # Скип рассматриваемой
                if c_prime == c:
                    continue
                
                # Проверка наличия пересечения по логкатам
                splits_c_prime = set(categories[c_prime]["logical_category"])
                if splits_c & splits_c_prime:
                    overlap_map[c].add(c_prime)
                    
        return overlap_map
    
# =========================================================================
# ВСПОМОГАТЕЛЬНЫЕ ГЕТТЕРЫ
# =========================================================================

def _get_cost(costs: Dict[str, Dict], category: str, month: int) -> float:
    """
    Возвращает стоимость 1 TRP для категории c в месяце m.
    
    :param costs: Словарь со стоимостями 1 TRP по категориям за каждый месяц
    :param category: Название интересующей категории
    :param month: Номер интересующего месяца
    
    :return: Стоимость 1 TRP в категории в конкретный месяц
    """
    return costs.get(category, {}).get(month, 0.0)

def _get_competitor_trp(categories: Dict[str, Dict], competitors: Dict, category: str, month: int) -> float:
    """
    Возвращает TRP конкурентов для категории c в месяце m.
    
    :param categories: Словарь с информацией по категориям
    :param competitors: Словарь с информацией по месячным TRP конкурентов по категориям
    :param category: Название интересующей категории
    :param month: Номер интересующего месяца
    
    :return: TRP конкурентов за месяц для категориии
    """
    comp_key = categories[category]["competitor_category"]
    return competitors.get(comp_key, {}).get(month, 0.0)

def _get_dtb(forecast_dict: Dict[str, Dict], category: str, month: int, trp: int) -> float:
    """
    Возвращает прогноз DTB для категории в конкретный месяц для конкретного уровня TRP
    
    :param forecast_dict: Словарь с прогнозами DTB и revenuе по категориям и месяцам
    :param category: Название интересующей категории
    :param month: Номер интересующего месяца
    :param trp: Интересующий уровень TRP
    
    :return: Прогноз DTB при заданных параметрах
    """

    df = forecast_dict[category][month]
    row = df[df["TRP"] == trp]
    
    if row.empty or trp <= 0:
        return 0.0
    
    return float(row["DTB_pred"].iloc[0])

def _get_revenue(forecast_dict: Dict[str, Dict], category: str, month: int, trp: int) -> float:
    """
    Возвращает прогноз выручки для категории в конкретный месяц для конкретного уровня TRP
    
    :param forecast_dict: Словарь с прогнозами DTB и revenuе по категориям и месяцам
    :param category: Название интересующей категории
    :param month: Номер интересующего месяца
    :param trp: Интересующий уровень TRP
    
    :return: Прогноз DTB при заданных параметрах
    """

    df = forecast_dict[category][month]
    row = df[df["TRP"] == trp]
    
    if row.empty or trp <= 0:
        return 0.0
    
    return float(row["revenue"].iloc[0])

# =========================================================================
# ДИНАМИЧЕСКАЯ КОРРЕКЦИЯ СТОИМОСТЕЙ С УЧЕТОМ ХРОНО
# =========================================================================

def _get_cost_multipliers(category_info: Dict) -> Dict[str, float]:
    """
    Возвращает множители стоимости для категории в зависимости от хроно и вертикали.

    :param category_info: Словарь с параметрами категории (нужно доставать от туда хроно и вертикаль)

    :return: Словарь с коэффициентами стоимостей под разные продолжительности РК в категории (с учетом вертикали и хроно)
    """
    
    chrono = category_info.get("chrono", "20/10 s")
    vertical = category_info.get("vertical", "")

    if chrono == "40/20 s":
        return {
            "single": 0.97,
            "multi_first": 0.97,
            "multi_cont": 0.9875
        }
    else:  # 20/10 s
        if vertical == "Goods":
            single_mult = 1.0175
        else:
            single_mult = 1.025

        return {
            "single": 1.02,
            "multi_first": 1.02,
            "multi_cont": 1.0375
        }

"""
Единая точка lookup'а вводных предсказателя c фоллбэками.

Логика:

* `dtb_for(key, month)`            — помесячный DTB. Сначала пытаемся
  собрать сумму по логкатам из Excel-таблицы (`dtb_loader`); если
  ни один логкат разреза в Excel не найден, падаем на `DTB_dict`
  (ловит legacy-псевдоразрезы вроде `Goods.Sellers` /
  `Realty.ShortRent`, которых в Excel нет).

* `value_for(key, month)`          — ценность DTB c YoY-поправкой
  (`yoy_dict[vertical] ** 2`, всегда). Если точного ключа нет —
  берём вертикаль первого логката из ключа.

* `ce_for(key)`                    — cross-effect; та же fallback-
  семантика, что у value_for.

* `sov_for(key, month)`            — SOV; при отсутствии точного
  ключа отдаём `SOV_dict["Default"]` (единицы).

* `trp_cost_for(key, month)`       — TRP-cost; при отсутствии ключа
  отдаём `trp_cost_dict["Default"]` (среднее по месяцам).

* `vertical_for(key)`              — вспомогательная: достаёт
  «вертикальный» канон-ключ для словарей (Goods / Services /
  Transport / Realty&Travel / Vacancies&Gigs).

Везде `key` — это исходная строка разреза (`'Goods.Fashion'` или
`'Goods.Furniture, Goods.HomeAndGarden, Goods.Food'`).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Mapping, Union, Tuple

from PROMISER.data_uploading import dtb_loader


# ---------------------------------------------------------------------------
# Вертикали
# ---------------------------------------------------------------------------
# Префикс логката (до первой точки) → канон-ключ вертикали в словарях.
# Realty + Travel объединены, Vacancies + Gigs объединены — так задано
# в ext_config.py (см. value_dict / yoy_dict).
_PREFIX_TO_VERTICAL: dict[str, str] = {
    "Goods": "Goods",
    "Services": "Services",
    "Transport": "Transport",
    "Realty": "Realty",
    "Travel": "Travel",
    "Vacancies": "Vacancies",
    "Gigs": "Gigs",
    # Jobs — алиас для Vacancies (исторический; в CE_dict встречается 'Jobs&Gigs').
    "Jobs": "Vacancies",
}

# В CE_dict вертикальный ключ когда-то писался как `Jobs&Gigs`, а в
# value_dict / yoy_dict — как `Vacancies&Gigs`. Чтобы lookup не падал,
# при поиске вертикали в словаре пробуем оба варианта.
_VERTICAL_ALIASES: dict[str, list[str]] = {
    "Vacancies": ["Vacancies", "Jobs"],
}


def _split_logcats(key: str) -> list[str]:
    """'A, B,C' → ['A','B','C']."""
    return [s.strip() for s in str(key).split(",") if s.strip()]


def vertical_for(key: str) -> str:
    """Возвращает канон-вертикаль для разреза.

    Берём префикс первого логката и ищем его в `_PREFIX_TO_VERTICAL`.
    Это соответствует требованию: «если нет прямого ключа в словарях
    под разрез, то берутся цифры по вертикали первого логката в списке».
    """
    parts = _split_logcats(key)
    if not parts:
        raise ValueError(f"Не могу определить вертикаль: пустой ключ {key!r}")
    prefix = parts[0].split(".", 1)[0]
    if prefix not in _PREFIX_TO_VERTICAL:
        raise KeyError(
            f"Неизвестный префикс логката {prefix!r} (из {key!r}). "
            f"Поддерживаются: {sorted(_PREFIX_TO_VERTICAL)}"
        )
    return _PREFIX_TO_VERTICAL[prefix]


def _from_dict_with_vertical_fallback(
    d: Mapping, key: str, *, dict_name: str
):
    """Точный ключ → вертикаль (с алиасами) → KeyError."""
    if key in d:
        return d[key]
    vertical = vertical_for(key)
    for alias in _VERTICAL_ALIASES.get(vertical, [vertical]):
        if alias in d:
            return d[alias]
    raise KeyError(
        f"{dict_name}: нет ни ключа {key!r}, ни вертикального fallback "
        f"({vertical!r} / алиасов {_VERTICAL_ALIASES.get(vertical, [])})"
    )


# ---------------------------------------------------------------------------
# Геттеры
# ---------------------------------------------------------------------------
def ce_for(key: str, ce_dict: Mapping[str, float]) -> float:
    """CE_dict с fallback на вертикаль."""
    return float(_from_dict_with_vertical_fallback(ce_dict, key, dict_name="CE_dict"))


def value_for(
    key: str,
    month: int,
    value_dict: Mapping[str, Mapping[int, float]],
    yoy_dict: Mapping[str, float],
    return_expanded: bool = False
) -> Union[float, Tuple[float, float, float]]:
    """value_dict (с fallback на вертикаль) × YoY² (всегда).

    YoY-коэффициент берётся по вертикали разреза. Применяется в квадрате,
    чтобы соответствовать ТЗ: «на её квадрат домножается ценность
    метрики 2025 года (всегда)».
    
    Если выставлен флаг return_expanded, то возвращается больше информации о расчете (для финальной отчетности)
    """
    series = _from_dict_with_vertical_fallback(value_dict, key, dict_name="value_dict")
    base = float(series[int(month)])
    vertical = vertical_for(key)
    yoy = float(yoy_dict.get(vertical, 1.0))
    
    if return_expanded:
        return base, yoy, base * yoy * yoy
    else:
        return base * yoy * yoy


def sov_for(key: str, month: int, sov_dict: Mapping[str, Mapping[int, float]]) -> float:
    """SOV точно или из 'Default' (единицы)."""
    series = sov_dict.get(key, sov_dict["Default"])
    return float(series[int(month)])


def trp_cost_for(
    key: str,
    month: int,
    trp_cost_dict: Mapping[str, Mapping[int, float]],
) -> float:
    """TRP-cost точно или из 'Default' (среднее по разрезам за месяц)."""
    series = trp_cost_dict.get(key, trp_cost_dict["Default"])
    return float(series[int(month)])


# ---------------------------------------------------------------------------
# DTB: Excel сначала, dict — fallback
# ---------------------------------------------------------------------------
@lru_cache(maxsize=512)
def _dtb_from_excel_cached(key: str) -> dict[int, int] | None:
    """Сумма помесячного DTB по логкатам из Excel.

    Возвращаем None, если ни один логкат разреза в Excel не найден
    (тогда вызывающий код пойдёт за `DTB_dict`-fallback'ом).
    """
    monthly = dtb_loader.load_monthly_dtb_table()
    parts = _split_logcats(key)
    cols = [p for p in parts if p in monthly.columns]
    if not cols:
        return None
    summed = monthly[cols].sum(axis=1).astype("int64")
    return {int(m): int(summed.at[m]) for m in summed.index}


def dtb_for(
    key: str,
    month: int,
    dtb_dict: Mapping[str, Mapping[int, int]] | None = None,
) -> int:
    """Помесячный DTB по разрезу.

    1. Берём сумму из Excel по присутствующим в нём логкатам.
    2. Если в Excel совсем нет колонок этого разреза (legacy-псевдо-
       ключи типа `Goods.Sellers`, `Realty.ShortRent`) — падаем на
       `DTB_dict`. Если и там нет — KeyError.
    """
    excel_series = _dtb_from_excel_cached(key)
    if excel_series is not None:
        return int(excel_series[int(month)])
    if dtb_dict is not None and key in dtb_dict:
        return int(dtb_dict[key][int(month)])
    raise KeyError(
        f"DTB не найден ни в Excel, ни в DTB_dict для ключа {key!r}"
    )

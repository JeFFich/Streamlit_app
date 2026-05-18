"""
Конфигурация пайплайна pROMIser → matrix.

Все хардкод-пути и магические числа собраны здесь, чтобы:
  * аналитик мог поправить путь / ID гугл-таблицы в одном месте;
  * не было `input(...)` или относительных путей внутри логики.
"""
from pathlib import Path


# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------

# Базовый путь ко всему PROMISER
BASE_PATH = Path(__file__).resolve().parent.parent

# OAuth-доступ к Google Sheets. token.json создаётся автоматически после
# первой авторизации; credentials.json нужно скачать в Google Cloud Console.
TOKEN_PATH = BASE_PATH / "configurations/token.json"
CREDENTIALS_PATH = BASE_PATH / "configurations/credentials.json"

# pickle с кривыми "охват → запомнившие сообщение" (один раз посчитан вне пайплайна)
SEEN_CURVES_PATH = BASE_PATH / "configurations/curves_mean.pickle"

# Excel с DAILY DTB по logcat за 2025 год (в файле колонки = logcat, строки = даты).
# Из него dtb_loader агрегирует помесячный DTB и склеивает комбо-разрезы.
DTB_EXCEL_PATH = BASE_PATH / "configurations/logcats_DTB_2025.xlsx"

# Куда складываем итоговый pickle с матрицей (lookup) для MILP-оптимизатора.
DEFAULT_OUTPUT_PATH = BASE_PATH / "CE_prediction_dict.pkl"
DEFAULT_LIGHT_OUTPUT_PATH = BASE_PATH / "CE_prediction_dict_light.pkl"


# ---------------------------------------------------------------------------
# Google Sheet IDs
# ---------------------------------------------------------------------------
# Лист "data Nat TV": факт TRP/SOV/бюджет по историческим флайтам.
# Также содержит лист на каждый флайт с кривой TRP→Reach (см. load_reach_trp).
CAMPAIGNS_SHEET_ID = "1nymqZ55uunXRlnNakDjRx6WPkbd-YBc4O9nFqolqzjU"

# Лист "results": метрики по флайтам (DTB-uplift, ROMI, OPM, consideration, ...).
METRICS_SHEET_ID = "1jVFhIIPQ0ZJZMijbOcyBV6o7qJG9TQB_pUepgP3BM5A"

# Макет для нового датасета (data_to_predict). Аналитик заполняет его руками.
INPUT_LAYOUT_SHEET_ID = "19txw3BS_yH9Hpsl57TjoHKdW6eCVM6fojyokDCtBwlM"


# ---------------------------------------------------------------------------
# Параметры предсказания
# ---------------------------------------------------------------------------
# Вопрос анкеты, по которому считаем "запомнили рекламу".
DEFAULT_QUESTION = "Основная идея рекламы_Спонтанно_Авито"

# Доля "видивших ролик" из формального reach (TRP-кривая считает охват per-OTS,
# нам нужен охват тех, кто реально посмотрел).
REAL_SEEN_COEFF = 0.6

# SOV-коридор: внутри него меняем sov_coeff_start → sov_coeff_end линейно.
# Значения отличаются для Goods и не-Goods (исторически калибровались отдельно).
SOV_BOUNDS_GOODS = (0.13, 0.18)        # (min_sov, max_sov)
SOV_BOUNDS_OTHER = (0.40, 0.56)
SOV_COEFF_START = 1.0
SOV_COEFF_END = 1.3

# Долгосрочный мультипликатор выручки от Brand-effect.
LONG_TERM_EFFECT = 2.0

# Среднее opm * consideration для нормализации creative_coeff.
AVG_CREATIVE_COEFF = 6.42


# ---------------------------------------------------------------------------
# Параметры построения матрицы
# ---------------------------------------------------------------------------
# Фиксированный TRP-anchor, относительно которого считаем коэффициент в
# discrete-optimizer-блоке. Подставляется как "стартовая точка" в make_sov_trp_coeffs.
DISCRETE_TRP_ANCHOR = 1000

# Месяцы в году, для которых строим прогноз.
MONTHS = list(range(1, 13))

# Сколько раз сэмплируем metric_abs_analytics ~ N(mean, mde/1.96), чтобы получить
# CI (low/high) по DTB_pred.
DEFAULT_N_BOOTSTRAP = 200

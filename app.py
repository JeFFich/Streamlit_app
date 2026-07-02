import streamlit as st
from typing import List, Tuple, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

from CategoryWidgetGroup import CategoryWidgetGroup, ValidationError
from data_parser import load_google_sheets, get_competitor_categories, get_target_audiences, transform_trp_comp_info, get_promiser_forecasts, transform_trp_cost_info, get_trp_categories_by_vertical, save_config_to_sheets, load_config_from_sheets_raw, get_categories_seasonality
from configs import *
from OptimizerNew.MediaPlanOptimizer import MediaPlanOptimizer
from PlanAnalyzer.MediaPlanAnalyzer import MediaPlanAnalyzer
from PlanAnalyzer.AnalyserOutput import create_analysis_plotly_view, create_analysis_google_sheet
from Output import create_media_plan_google_sheet, create_media_plan_chart


# ==============================================================================
# Ключи session_state для Google Sheets
# ==============================================================================

def _handle_sheets_url_change():
    """
    Внутрення функция для фиксации изменения ссылки на табличку с TRP
    
    Если не возникло никаких ошибок с выгрузкой, то соответсвующие ключи состояний меняются
    """
    new_url = st.session_state.get("google_sheets_url", "").strip()

    if not new_url:
        st.session_state["trp_cost_df"] = None
        st.session_state["competitors_trp_df"] = None
        st.session_state["competitor_categories"] = []
        st.session_state["target_audiences"] = []
        st.session_state["google_sheets_error"] = None
        st.session_state["google_sheets_success"] = False
        
        return

    trp_df, comp_df, error = load_google_sheets(new_url)

    st.session_state["trp_cost_df"] = trp_df
    st.session_state["competitors_trp_df"] = comp_df
    st.session_state["google_sheets_error"] = error
    st.session_state["google_sheets_success"] = (error is None)

    if error is None:
        new_competitors = get_competitor_categories(comp_df)
        st.session_state["competitor_categories"] = new_competitors
        
        new_audiences = get_target_audiences(trp_df)
        st.session_state["target_audiences"] = new_audiences
        
        categories_by_vertical = get_trp_categories_by_vertical(trp_df)
        st.session_state["categories"] = categories_by_vertical
    else:
        st.session_state["competitor_categories"] = []
        st.session_state["target_audiences"] = []
        st.session_state["categories"] = {}

# ==============================================================================
# Управление состоянием
# ==============================================================================

def _state_key(vertical_idx: int) -> str:
    """
    Внутренняя функция для создания ключа со списком group_id для вертикали
    
    :param vertical_idx: Уникальный идентификатор для вертикали
    
    :return: Созданный ключ для вертикали
    """
    
    return f"vertical_{vertical_idx}_group_ids"

def _counter_key(vertical_idx: int) -> str:
    """
    Внутренняя функция для создания ключа глобального счётчика id для вертикали
    
    :param vertical_idx: Уникальный идентификатор для вертикали
    
    :return: Созданный ключ для вертикали
    """
    
    return f"vertical_{vertical_idx}_next_id"

def _ensure_state(vertical_idx: int):
    """
    Внутренняя функция для инициализиции состояния для вертикали (если ещё не создано)
    
    :param vertical_idx: Уникальный идентификатор для вертикали
    """
    
    # Если не создана, то создаем
    if _state_key(vertical_idx) not in st.session_state:
        st.session_state[_state_key(vertical_idx)] = []
    if _counter_key(vertical_idx) not in st.session_state:
        st.session_state[_counter_key(vertical_idx)] = 0
    
        
def _add_group(vertical_idx: int, preset: Dict = None):
    """
    Внутренняя функция для добавления новой категории в переданной вертикали
    Глобальный уникальный id для категории определяется как  vertical_idx * 10000 + local_counter,
    где locak_counter - текущее число категорий в вертикали
    
    :param vertical_idx: Уникальный идентификатор для вертикали
    :param preset: Словарь для пресета (отвечает за то, является ли пресетом категория или нет)
    """
    # Получаем уникальные ключи для вертикали
    key = _state_key(vertical_idx)
    ctr = _counter_key(vertical_idx)
    
    # Рассчитываем уникальный id категории и запоминаем его
    global_id = vertical_idx * 10_000 + st.session_state[ctr]
    st.session_state[key].append(global_id)
    st.session_state[ctr] += 1
    st.session_state["group_meta"][global_id] = {"preset": preset}

def _delete_group(group_id: int):
    """
    Внутренняя функция для удаления категории из любой вертикали
    Удаление осуществляется по глобальному id категории, поэтому случайных удалений не происходит
    
    :param group_id: глобальный id для удаляемой группы
    """
    
    # Ищем удаляемую категорию среди всех вертикалей
    for v_idx in range(len(LOGICAL_CATEGORIES.keys())):
        key = _state_key(v_idx)
        if key in st.session_state and group_id in st.session_state[key]:
            st.session_state[key] = [
                gid for gid in st.session_state[key] if gid != group_id
            ]
            st.session_state["groups_registry"].pop(group_id, None)
            st.session_state["group_meta"].pop(group_id, None)
            
            return
   
# =============================================================================
# Отрисовка общей части для вертикали + валидация вводных параметров для одной вертикали
# ==============================================================================
 
def _vertical_widget_key(vertical_idx: int, name: str) -> str:
    """
    Внутренняя функция для создания уникального ключа для вертикального виджета (чтобы можно было потом доставать из него значение)
    
    :param vertical_idx: Уникальный идентификатор вертикали
    :param name: Название вертикали
    
    :return: Уникальный ключ для вертикального виджета
    """
    
    return f"vert_{vertical_idx}_{name}"

def render_vertical_widgets(vertical_idx: int):
    """
    Внутренняя функция для отрисовывает вертикальных виджетов
    
    :param vertical_idx: Укниальный идентификатор вертикали
    """
    
    # Функция для генерации ключей виджетов
    vk = lambda name: _vertical_widget_key(vertical_idx, name)
    
    # Инициализируем дефолты ТОЛЬКО если ключа ещё нет
    if vk("max_budget") not in st.session_state:
        st.session_state[vk("max_budget")] = DEF_VERT_BUDG
    if vk("min_trp") not in st.session_state:
        st.session_state[vk("min_trp")] = DEF_VERT_TRP
    if vk("min_campaigns") not in st.session_state:
        st.session_state[vk("min_campaigns")] = DEF_VERT_RK_MIN
    if vk("max_campaigns") not in st.session_state:
        st.session_state[vk("max_campaigns")] = DEF_VERT_RK_MAX 

    col1, col2 = st.columns(2)
    with col1:
        st.number_input(
            "Максимальный cуммарный бюджет на вертикаль (млн. руб.)",
            min_value=MIN_VERT_BUDG, max_value=MAX_VERT_BUDG, step=STEP_VERT_BUDG,
            key=vk("max_budget")
        )
    with col2:
        st.number_input(
            "Минимальный суммарный TRP на вертикаль",
            min_value=MIN_VERT_TRP, max_value=MAX_VERT_TRP, step=STEP_VERT_TRP,
            key=vk("min_trp"),
        )
        
    col3, col4 = st.columns(2)
    with col3:
        st.number_input(
            "Минимальное число РК в вертикали",
            min_value=MIN_VERT_RK_MIN, max_value=MAX_VERT_RK_MIN, step=STEP_VERT_RK_MAX,
            key=vk("min_campaigns")
        )
    with col4:
        st.number_input(
            "Максимальное число РК в вертикали",
            min_value=MIN_VERT_RK_MAX, max_value=MAX_VERT_RK_MAX, step=STEP_VERT_RK_MAX,
            key=vk("max_campaigns")
        )

def validate_vertical(vertical_idx: int, cat_values: List[Dict]) -> List[ValidationError]:
    """
    Внутренняя функция для валидации ввода на уровне вертикали
    
    :param vertical_idx: Уникальный идентификатор вертикали
    :param cat_values: Список значений категории для вертикали
    
    :return: Список валидационных ошибок
    """
    
    # Функция для генерации ключей виджетов
    vk = lambda name: _vertical_widget_key(vertical_idx, name)
    
    errors: List[ValidationError] = []

    vert_max_budget = st.session_state.get(vk("max_budget"), 300) * 1_000_000
    vert_min_trp = st.session_state.get(vk("min_trp"), 6000)
    vert_min_campaigns = st.session_state.get(vk("min_campaigns"), 2)
    vert_max_campaigns = st.session_state.get(vk("max_campaigns"), 4)

    # 0. Мин. число РК ≤ макс. число РК в вертикали
    if vert_min_campaigns > vert_max_campaigns:
        errors.append(ValidationError(
            "vert_campaigns",
            f"Мин. число РК в вертикали ({vert_min_campaigns}) > макс. ({vert_max_campaigns}).",
        ))

    # 1. Сумма (мин_бюджет * мин_число_РК) по категориям ≤ макс. бюджет вертикали
    if cat_values:
        sum_min_budgets = sum(
            cv["min_budget"] for cv in cat_values
        )

        if sum_min_budgets > vert_max_budget:
            errors.append(ValidationError(
                "vert_budget",
                f"Сумма мин. бюджетов РК по категориям ({sum_min_budgets:,} руб. c учетом мин. кол-в РК в категориях) "
                f"превышает макс. бюджет вертикали ({vert_max_budget:,} руб.).",
            ))

    # 2. Если мин. суммарный TRP > 0, должна быть хотя бы одна категория
    if vert_min_trp > 0 and not cat_values:
        errors.append(ValidationError(
            "vert_trp",
            f"Мин. суммарный TRP = {vert_min_trp}, но в вертикали нет ни одной категории.",
        ))

    # 3. Макс. число РК в вертикали ≥ сумма мин. РК по категориям
    if cat_values:
        sum_min_campaigns = sum(cv["min_campaigns"] for cv in cat_values)
        if vert_max_campaigns < sum_min_campaigns:
            errors.append(ValidationError(
                "vert_max_camps_vs_cats",
                f"Макс. число РК в вертикали ({vert_max_campaigns}) < "
                f"суммы мин. РК по категориям ({sum_min_campaigns}).",
            ))

    # 4. Мин. число РК в вертикали ≤ сумма макс. РК по категориям
    if cat_values:
        sum_max_campaigns = sum(cv["max_campaigns"] for cv in cat_values)
        if vert_min_campaigns > sum_max_campaigns:
            errors.append(ValidationError(
                "vert_min_camps_vs_cats",
                f"Мин. число РК в вертикали ({vert_min_campaigns}) > "
                f"суммы макс. РК по категориям ({sum_max_campaigns}).",
            ))
            
    # 5. Если мин. число РК в вертикали > 0, то для нее должна сущетсвовать хотя бы 1 категория
    if vert_min_campaigns > 0 and not cat_values:
        errors.append(ValidationError(
            "vert_trp",
            f"Мин. число РК в вертикали = {vert_min_campaigns}, но в вертикали нет ни одной категории.",
        ))
        
    # 6. Нет категорий с совпадающими именами
    if cat_values:
        names = [cv["name"].strip() for cv in cat_values if cv["name"].strip()]
        
        seen = {}
        for idx, name in enumerate(names):
            name_lower = name.lower()
            
            # Избегаем дублирования сообщений с ошибкой
            if name_lower in seen:
                errors.append(ValidationError(
                    "duplicate_name",
                    f"Название «{name}» используется несколько раз. "
                    f"Каждая категория должна иметь уникальное название.",
                ))
                break 
            
            seen[name_lower] = idx

    return errors

def validate_unique_category_names(vertical_idx: int, cat_values: List[dict]) -> List[ValidationError]:
    """
    Функция для проверки, что внутри вертикали нет категорий с одинаковыми именами
    
    :param vertical_idx: Уникальный идентификатор вертикали
    :param cat_values: Список значений категории для вертикали
    
    :return: Список валидационных ошибок
    """
    errors: List[ValidationError] = []

    if not cat_values:
        return errors

    # Собираем непустые имена
    names = [cv["name"].strip() for cv in cat_values if cv["name"].strip()]

    # Ищем дубли
    seen = {}
    for idx, name in enumerate(names):
        name_lower = name.lower()
        if name_lower in seen:
            errors.append(ValidationError(
                "duplicate_name",
                f"Название «{name}» используется несколько раз. "
                f"Каждая категория должна иметь уникальное название.",
            ))
            break  # одной ошибки достаточно, чтобы не дублировать сообщения
        seen[name_lower] = idx

    return errors

# ==============================================================================
# Отрисовка одной вертикали (полная, с учетом категорий)
# ==============================================================================

def render_vertical(vertical_idx: int, vertical: str) -> List[Tuple[int, List[ValidationError]]]:
    """
    Функция для отрисовки содержимого вкладки одной вертикали + возвращает список ошибок валидации вводных параметров категорий
    
    :param vertical_idx: Уникальный идентификатор для вертикали
    :param vertical: Название вертикали 
    
    :return: Список валидационных ошибок для категорий в конкретной вертикали
    """
    
    _ensure_state(vertical_idx)
    
    # --- Виджеты уровня вертикали ---
    
    st.subheader(f"Общие параметры вертикали")
    render_vertical_widgets(vertical_idx)
    
    # Плейсхолдер для ошибок вертикали — заполним ПОСЛЕ отрисовки категорий
    vert_errors_placeholder = st.empty()

    st.divider()
    
    # --- Выбор пресета или новой категории ---
    presets = PRESETS_BY_VERTICAL.get(vertical, [])
    with st.popover("➕ Добавить категорию", use_container_width=False):
        if presets:
            st.markdown("**Пресеты:**")
            for p_idx, preset in enumerate(presets):
                st.button(
                    preset["category_name"], 
                    key=f"preset_{vertical_idx}_{p_idx}", 
                    on_click=_add_group, 
                    args=(vertical_idx, preset), 
                    use_container_width=True
                )
        
        st.divider()
        st.button(
            "🆕 Новая категория", 
            key=f"new_empty_{vertical_idx}", 
            on_click=_add_group, 
            args=(vertical_idx, None), 
            use_container_width=True
        )

     # --- Виджеты уровня категорий ---
    group_ids = st.session_state[_state_key(vertical_idx)]
    if not group_ids:
        st.info("Нет категорий. Нажмите кнопку выше, чтобы добавить.")
        return []
    
     # Объединяем ошибки вертикали и категорий перед их возвращением
    all_tab_errors: List[Tuple[str, List[ValidationError]]] = []
    rendered_groups: List[CategoryWidgetGroup] = []

    registry: Dict[int, CategoryWidgetGroup] = st.session_state["groups_registry"]
    for display_num, gid in enumerate(group_ids, start=1):
        with st.expander(f"📂 Категория {display_num}", expanded=True):
            group = CategoryWidgetGroup(
                group_id=gid,
                vertical=vertical,
                on_delete=_delete_group,
                preset=st.session_state["group_meta"].get(gid, {}).get("preset")
            )
            # Сохраняем категорию в реестр
            registry[gid] = group
            rendered_groups.append(group)
            errors = group.render()
            if errors:
                all_tab_errors.append((f'Категория {display_num}', errors))
                
    # Валидация вертикали
    cat_values = [g.get_values() for g in rendered_groups]          
    vert_errors = validate_vertical(vertical_idx, cat_values)
    
    if vert_errors:
        with vert_errors_placeholder.container():
            for err in vert_errors:
                st.error(f"⚠️ {err.message}")
        # Вставляем в начало списка ошибок
        all_tab_errors.insert(0, ("Параметры вертикали", vert_errors))

    return all_tab_errors

# ==============================================================================
#  Полный сбор и восстановление состояния
# ==============================================================================

def _collect_full_state() -> Dict[str, Any]:
    """
    Собирает ВСЕ параметры приложения в один словарь.
    """
    
    num_to_month = {
        1: 'Январь', 2: 'Февраль', 3: 'Март',
        4: 'Апрель', 5: 'Май', 6: 'Июнь',
        7: 'Июль', 8: 'Август', 9: 'Сентябрь',
        10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }
    
    state = {
        "saved_at": datetime.now(ZoneInfo('Europe/Moscow')).isoformat(),
        "google_sheets_url": st.session_state.get("google_sheets_url", ""),
        "revenue_correction": st.session_state.get("revenue_correction", False),
        "drive_upload": st.session_state.get("drive_upload", False),
        "verticals": {}
    }

    for v_idx, v_name in enumerate(LOGICAL_CATEGORIES.keys()):
        vk = lambda name: _vertical_widget_key(v_idx, name)
        vertical_data = {
            "max_budget": st.session_state.get(vk("max_budget"), 300),
            "min_trp": st.session_state.get(vk("min_trp"), 6000),
            "min_campaigns": st.session_state.get(vk("min_campaigns"), 2),
            "max_campaigns": st.session_state.get(vk("max_campaigns"), 4),
            "categories": [],
        }

        # Категории
        group_ids = st.session_state.get(_state_key(v_idx), [])
        registry = st.session_state.get("groups_registry", {})

        for gid in group_ids:
            group = registry.get(gid)
            if group:
                cat_data = group.get_values()
                cat_data["default_romi"] *= 100
                cat_data["min_budget"] /= 1_000_000
                cat_data["max_budget"] /= 1_000_000
                cat_data["start_months"] = [num_to_month[month] for month in cat_data["start_months"]]
                
                # Добавляем метаинформацию о пресете
                meta = st.session_state.get("group_meta", {}).get(gid, {})
                preset = meta.get("preset")
                cat_data["preset_name"] = preset['category_name'] if preset else None
                cat_data["input_mode"] = st.session_state.get(
                    f"cat_group_{gid}_name_input_mode", "✏️ Вручную"
                )
                vertical_data["categories"].append(cat_data)

        state["verticals"][v_name] = vertical_data

    return state

def _restore_full_state(state: Dict[str, Any]):
    """
    Восстанавливает состояние приложения из сохранённого словаря.
    """
    
    st.session_state["_last_saved_at"] = state["saved_at"]
    
    # URL таблицы
    if state.get("google_sheets_url"):
        st.session_state["google_sheets_url"] = state["google_sheets_url"]
        _handle_sheets_url_change()

    # Коррекция
    st.session_state["revenue_correction"] = state.get("revenue_correction", False)
    st.session_state["drive_upload"] = state.get("drive_upload", False)

    # Вертикали
    for v_idx, v_name in enumerate(LOGICAL_CATEGORIES.keys()):
        vk = lambda name, vi=v_idx: _vertical_widget_key(vi, name)
        vert_data = state.get("verticals", {}).get(v_name, {})

        if not vert_data:
            continue

        # Параметры вертикали
        st.session_state[vk("max_budget")] = vert_data.get("max_budget", 300)
        st.session_state[vk("min_trp")] = vert_data.get("min_trp", 6000)
        st.session_state[vk("min_campaigns")] = vert_data.get("min_campaigns", 2)
        st.session_state[vk("max_campaigns")] = vert_data.get("max_campaigns", 4)

        # Категории
        categories = vert_data.get("categories", [])
        # Очищаем текущие группы вертикали
        st.session_state[_state_key(v_idx)] = []
        st.session_state[_counter_key(v_idx)] = 0

        for cat_data in categories:
            # Определяем пресет
            preset_name = cat_data.get("preset_name")
            preset = None
            if preset_name:
                presets = PRESETS_BY_VERTICAL.get(v_name, [])
                preset = next((p for p in presets if p["category_name"] == preset_name), None)

            # Добавляем группу
            _add_group(v_idx, preset)
            gid = st.session_state[_state_key(v_idx)][-1]  # последний добавленный id
            prefix = f"{v_name}_cat_group_{gid}"

            # Восстанавливаем значения виджетов
            st.session_state[f"{prefix}_name"] = cat_data.get("name", "")
            st.session_state[f"{prefix}_name_manual"] = cat_data.get("name", "")
            st.session_state[f"{prefix}_name_input_mode"] = cat_data.get(
                "input_mode", "✏️ Вручную"
            )
            st.session_state[f"{prefix}_incoming_categories"] = cat_data.get(
                "logical_category", []
            )
            st.session_state[f"{prefix}_min_trp"] = cat_data.get("min_trp", 1500)
            st.session_state[f"{prefix}_min_sov"] = cat_data.get("min_sov", 0.13)
            st.session_state[f"{prefix}_default_romi"] = cat_data.get("default_romi", -90)
            st.session_state[f"{prefix}_chrono"] = cat_data.get("chrono", None)
            st.session_state[f"{prefix}_target_audience"] = cat_data.get(
                "target_audience", None
            )
            st.session_state[f"{prefix}_competitor_category"] = cat_data.get(
                "competitor_category", None
            )
            st.session_state[f"{prefix}_min_campaigns"] = cat_data.get("min_campaigns", 1)
            st.session_state[f"{prefix}_max_campaigns"] = cat_data.get("max_campaigns", 2)
            st.session_state[f"{prefix}_min_budget"] = cat_data.get(
                "min_budget", 100_000_000
            )
            st.session_state[f"{prefix}_max_budget"] = cat_data.get(
                "max_budget", 500_000_000
            )
            st.session_state[f"{prefix}_min_duration"] = cat_data.get("min_duration", 1)
            st.session_state[f"{prefix}_max_duration"] = cat_data.get("max_duration", 2)
            st.session_state[f"{prefix}_mandatory_months"] = cat_data.get(
                "start_months", []
            )
            st.session_state[f"{prefix}_only_mandatory_months"] = cat_data.get(
                "strict_start", False
            )
            
def render_config_management():
    """Отрисовывает блок управления конфигурацией в сайдбаре."""
    with st.sidebar:
        st.divider()
        st.subheader("💾 Управление конфигурацией")

        st.text_input(
            "👤 Ваш идентификатор",
            key="current_user_id",
            placeholder="например: тег MM (без @)",
            help="Используется для сохранения и загрузки настроек",
        )
        
        user_id = st.session_state.get("current_user_id", False)

        if not user_id:
            st.warning("Введите идентификатор пользователя выше.")
            return

        st.caption(f"Пользователь: **{user_id}**")

        col_save, col_load = st.columns(2)

        with col_save:
            save_clicked = st.button("💾 Сохранить", use_container_width=True, key="save_config")
        with col_load:
            save_loaded = st.button("📂 Загрузить", use_container_width=True, key="load_config")

        if save_clicked:
            save_config_to_sheets(user_id, _collect_full_state())
            
        if save_loaded:
            config = load_config_from_sheets_raw(user_id)
                
            if config:
                _restore_full_state(config)
                st.session_state["config_status"] = True
                st.rerun()  # перерисовать с новым состоянием
                
        config_status = st.session_state.get("config_status", False)
        if config_status:
            st.success(f"✅ Загружено")
            del st.session_state["config_status"]
        
        # Информация о последнем сохранении
        last_state = st.session_state.get("_last_saved_at")
        if last_state:
            st.caption(f"Последнее сохранение: {last_state}")
            
def prepare_data(fake_seasonality: bool = False):
    """
    Внутрення функция для подготовки данных для оптимизатора/калькулятора
    
    :param fake_seasonality: флаг отключения рассчета сезонности
    """
    
    registry: Dict[int, CategoryWidgetGroup] = st.session_state["groups_registry"]
    
    # Словари по вертикалям и категориям 
    category_dict = {}
    vertical_dict = {}
    for vertical_idx, vertical in enumerate(LOGICAL_CATEGORIES.keys()):
        vk = lambda name: _vertical_widget_key(vertical_idx, name)
        vertical_dict[vertical] = {
            'max_budget': st.session_state.get(vk("max_budget"), 300) * 1_000_000,
            'min_total_trp': st.session_state.get(vk("min_trp"), 6000),
            'min_campaigns': st.session_state.get(vk("min_campaigns"), 2),
            'max_campaigns': st.session_state.get(vk("max_campaigns"), 4)
        }
        
        groups = st.session_state.get(_state_key(vertical_idx), [])
        if groups:
            for group_id in groups:
                category = registry[group_id].get_values()
                category_dict[category["name"]] = category
        else:
            vertical_dict.pop(vertical)
    
    # Словари по TRP
    trp_cost_dict = transform_trp_cost_info(st.session_state.get("trp_cost_df"), category_dict)
    competitors_dict = transform_trp_comp_info(st.session_state.get("competitors_trp_df"))

    # Прогнозы из промисера
    forecasts = get_promiser_forecasts(category_dict)
    
    # Сезонность
    get_categories_seasonality(category_dict, not fake_seasonality)
    
    return category_dict, vertical_dict, trp_cost_dict, competitors_dict, forecasts

# ==============================================================================
# Точка входа
# ==============================================================================

def main():
    # ---- Общая верхняя часть (вне вкладок) ----
    
    st.markdown(
        """
        <style>
        /* Фиксированная высота для multiselect (не растёт при выборе) */
        div[data-baseweb="select"] > div {
            max-height: 40px;
            overflow-y: auto !important;
        }
        div[data-testid="stAlert"] {
            max-height: 50px;
            overflow-y: auto !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    
    # Создаем общий регистр категорий, конкурентов и разметок пресетов
    if "groups_registry" not in st.session_state:
        st.session_state["groups_registry"] = {}
    if "competitor_categories" not in st.session_state:
        st.session_state["competitor_categories"] = []
    if "group_meta" not in st.session_state:
        st.session_state["group_meta"] = {}
    if "target_audiences" not in st.session_state:
        st.session_state["target_audiences"] = []
    if "categories" not in st.session_state:
        st.session_state["categories"] = {}
        
    st.set_page_config(page_title="Медиапланирование", layout="wide")
    st.title("Построение оптимального медиаплана")
    
    render_config_management()
    
    # ---- Общий виджет с ссылкой на гугл-таблицу + кнопка обновления ----
    
    col_1, col_2 = st.columns([4, 1], vertical_alignment="bottom")
    with col_1:
        st.text_input(
            "Гугл-таблица с информацией по TRP",
            value="",
            key="google_sheets_url",
            on_change=_handle_sheets_url_change,
            help=(
                "Вставьте ссылку на Google Sheets. Таблица должна содержать два листа:\n"
                "**TRP cost** — стоимости TRP\n"
                "**Competitors TRP** — данные по конкурентам (первая колонка = категории)"
            ),
            placeholder="https://docs.google.com/spreadsheets/d/...",
        )
    with col_2:
        st.button(
            "🔄 Обновить данные",
            key="reload_sheets",
            on_click=_handle_sheets_url_change,  # сработает всегда по клику
            use_container_width=True,
        )

    # Статус загрузки
    sheets_error = st.session_state.get("google_sheets_error")
    sheets_success = st.session_state.get("google_sheets_success", False)

    if sheets_error:
        st.error(f"❌ {sheets_error}")
    elif sheets_success:
        st.success("✅ Таблица успешно загружена!")

    st.divider()

    # ---- Вкладки по вертикалям ----
    
    tab_objects = st.tabs(LOGICAL_CATEGORIES.keys())

    # Отображаем все категории по вертикалям + запоминаем все ошибки для дальнейшего вывода
    all_errors: Dict[str, List[Tuple[int, List[ValidationError]]]] = {}
    for v_idx, (tab, vertical) in enumerate(zip(tab_objects, LOGICAL_CATEGORIES.keys())):
        with tab:
            tab_errors = render_vertical(v_idx, vertical)
            if tab_errors:
                all_errors[vertical] = tab_errors

    # ---- Общая нижняя часть (вне вкладок) ----

    # Есть хотя бы одна категория в вертикали
    has_any_group = any(
        st.session_state.get(_state_key(i), [])
        for i in range(len(LOGICAL_CATEGORIES.keys()))
    )
    
    # Есть ошибки в введенных данных
    has_errors = len(all_errors) > 0
    
    st.divider()
    
    # Если есть ошибки во введенных данных, то выводим про них и прячем кнопку
    if has_errors:
        st.warning("⚠️ Исправьте ошибки в введенных данных:")
        for vertical_name, errs_list in all_errors.items():
            for label, errs in errs_list:
                for err in errs:
                    st.markdown(f"- **{vertical_name} → {label}**: {err.message}")
    
    # Варианты режимов работы
    tab_optimize, tab_evaluate = st.tabs(["Расчёт оптимального плана", "Обсчёт текущего плана"])
    
    with tab_optimize:
        st.checkbox(
            "📐 Включить корректировку плана",
            value=False,
            key="revenue_correction",
            help="Если включено, то выручка будет полностью убрана + бюджеты домножатся на 1.3 (в названии листа на гугл-диске будет добавлена пометка «_скорректированный»)"
        )
        st.checkbox(
            "🔺 Создать флоучарт на гугл-диске",
            value=False,
            key="drive_upload",
            help="Если включено, то план продублируется в google-sheets (+ составится сводка по всем категориям, вертикалям и тотал)"
        )
        st.checkbox(
            "Включить в оптимизацию условие равномерности",
            value=False,
            key="uniform_flag",
            help="Если включено, то план будет строиться более равномерным в каждой вертикали"
        )
        st.checkbox(
            "Включить в оптимизацию сезонность",
            value=False,
            key="season_flag",
            help="Если включено, то в прогнозах будет учитываться сезонность"
        )
        
        # --- Дальнейший расчет ---
        if st.button("📊 Рассчитать оптимальный план", type="secondary", disabled=has_errors or not has_any_group):
            apply_correction = not st.session_state.get("revenue_correction", False)
            upload_to_drive = st.session_state.get("drive_upload", False)
            cov_penalty = 0.1 if st.session_state.get("uniform_flag", False) else 0
            seasonality = st.session_state.get("season_flag", False)
            
            category_dict, vertical_dict, trp_cost_dict, competitors_dict, forecasts = prepare_data(seasonality)
            
            # st.json(vertical_dict)
            # st.json(category_dict)
            # st.json(trp_cost_dict)
            # st.json(competitors_dict)
            
            with st.spinner("⏳ Выполняется расчет плана..."):
                try:
                    optimizer = MediaPlanOptimizer(coverage_penalty_weight=cov_penalty)
                    optimal_plan = optimizer.optimize(
                        categories=category_dict,
                        verticals=vertical_dict,
                        forecasts=forecasts,
                        competitors=competitors_dict,
                        costs=trp_cost_dict
                    )
                    
                    fig = create_media_plan_chart(optimal_plan, show_revenue=apply_correction)
                    if upload_to_drive:
                        result_sheet_url = create_media_plan_google_sheet(optimal_plan, apply_correction)

                    # --- Успех ---
                    st.success("✅ План создан")

                    # График Plotly
                    st.subheader("📈 Флоу чарт плана по вертикаля")
                    st.plotly_chart(fig, use_container_width=True)

                    # Дополнительно: кнопка-ссылка (более заметная)
                    if upload_to_drive:
                        st.link_button(
                            "📄 Перейти к таблице результатов на гугл-диске",
                            url=result_sheet_url,
                            use_container_width=True,
                        )

                except Exception as e:
                    # --- Ошибка ---
                    st.error(f"❌ Ошибка при выполнении оптимизации: {e}")
                    
    with tab_evaluate:
        st.checkbox(
            "🔺 Создать флоучарт на гугл-диске",
            value=False,
            key="drive_upload_calc",
            help="Если включено, то сводка продублируется в google-sheets"
        )
        
        uploaded_file = st.file_uploader(
            "Загрузить план",
            type=["xlsx", "xls"],
            key="flowchart_upload",
            help="Загрузите Excel-файл с флоучартом в требуемом формате",
        )
        
        evaluate_clicked = st.button(
            "Обсчитать план",
            disabled=(uploaded_file is None) or has_errors or not has_any_group,
            type="secondary",
            use_container_width=True,
            key="evaluate_run",
        )

        if evaluate_clicked and uploaded_file is not None:
            with st.spinner("⏳ Выполняется обсчет плана..."):
                try:
                    upload_to_drive = st.session_state.get("drive_upload_calc", False)
                    category_dict, vertical_dict, trp_cost_dict, competitors_dict, forecasts = prepare_data()
                    
                    analyzer = MediaPlanAnalyzer(
                        categories=category_dict,
                        verticals=vertical_dict,
                        forecasts=forecasts,
                        competitors=competitors_dict,
                        costs=trp_cost_dict
                    )
                    
                    #st.json(vertical_dict)
                    #st.json(category_dict)
                    #st.json(trp_cost_dict)
                    #st.json(competitors_dict)

                    output = analyzer.analyze(uploaded_file)

                    fig = create_analysis_plotly_view(*output)
                    
                    if upload_to_drive:
                        result_sheet_url = create_analysis_google_sheet(*output)
                        
                    # --- Успех ---
                    st.success("✅ План успешно обсчитан")

                    # График Plotly
                    st.subheader("📈 Сводка по плану")
                    st.plotly_chart(fig, use_container_width=True)

                    # Дополнительно: кнопка-ссылка (более заметная)
                    if upload_to_drive:
                        st.link_button(
                            "📄 Перейти к сводке на гугл-диске",
                            url=result_sheet_url,
                            use_container_width=True,
                        )
                except Exception as e:
                    # --- Ошибка ---
                    st.error(f"❌ Ошибка при выполнении обсчета: {e}")
                
if __name__ == "__main__":
    main()
    
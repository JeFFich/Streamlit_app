import streamlit as st
from typing import List, Tuple, Dict
import pandas as pd

from CategoryWidgetGroup import CategoryWidgetGroup, ValidationError
from data_parser import load_google_sheets, get_competitor_categories, get_target_audiences, transform_trp_comp_info, get_promiser_forecasts, transform_trp_cost_info, get_trp_categories_by_vertical
from configs import *
from Optimizer.MediaPlanOptimizer import MediaPlanOptimizer
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

        # Сбрасываем выбранные значения «Категория конкурентов» и «Целевая аудитория» у всех категорий
        _reset_all_competitor_selections()
        _reset_all_target_audience_selections()
    else:
        st.session_state["competitor_categories"] = []
        st.session_state["target_audiences"] = []
        st.session_state["categories"] = {}

def _reset_all_competitor_selections():
    """
    Внутрення функция сброса значений виджета «Категория конкурентов» у всех категорий.
    
    Срабатывает при изменении ссылки на табличку с TRP
    """
    for key in list(st.session_state.keys()):
        if key.endswith("_competitor_category"):
            st.session_state[key] = None

def _reset_all_target_audience_selections():
    """
    Внутренняя функция сброса значений виджета «Целевая аудитория» у всех категорий
    
    Срабатывает при изменении ссылки на табличку с TRP 
    """
    for key in list(st.session_state.keys()):
        if key.endswith("_target_audience"):
            st.session_state[key] = None

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

    col1, col2 = st.columns(2)
    with col1:
        st.number_input(
            "Максимальный cуммарный бюджет на вертикаль (млн. руб.)",
            min_value=MIN_VERT_BUDG, max_value=MAX_VERT_BUDG, value=DEF_VERT_BUDG, step=STEP_VERT_BUDG,
            key=vk("max_budget")
        )
    with col2:
        st.number_input(
            "Минимальный суммарный TRP на вертикаль",
            min_value=MIN_VERT_TRP, max_value=MAX_VERT_TRP, value=DEF_VERT_TRP, step=STEP_VERT_TRP,
            key=vk("min_trp"),
        )
        
    col3, col4 = st.columns(2)
    with col3:
        st.number_input(
            "Минимальное число РК в вертикали",
            min_value=MIN_VERT_RK_MIN, max_value=MAX_VERT_RK_MIN, value=DEF_VERT_RK_MIN, step=STEP_VERT_RK_MAX,
            key=vk("min_campaigns")
        )
    with col4:
        st.number_input(
            "Максимальное число РК в вертикали",
            min_value=MIN_VERT_RK_MAX, max_value=MAX_VERT_RK_MAX, value=DEF_VERT_RK_MAX, step=STEP_VERT_RK_MAX,
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
        # competitor_cats = st.session_state.get("competitor_categories", [])
        # if competitor_cats:
        #     st.caption(f"Найдено категорий конкурентов: {len(competitor_cats)} — {', '.join(competitor_cats[:5])}{'...' if len(competitor_cats) > 5 else ''}")
        #     st.dataframe(st.session_state.get("competitors_trp_df"))

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
    
    # --- Дальнейший расчет ---
    if st.button("📊 Рассчитать оптимальный план", type="secondary", disabled=has_errors or not has_any_group):
        registry: Dict[int, CategoryWidgetGroup] = st.session_state["groups_registry"]
        apply_correction = not st.session_state.get("revenue_correction", False)
        upload_to_drive = st.session_state.get("drive_upload", False)
        
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
        
        # st.json(vertical_dict)
        # st.json(category_dict)
        # st.json(trp_cost_dict)
        # st.json(competitors_dict)
        
        with st.spinner("⏳ Выполняется расчет плана..."):
            try:
                optimizer = MediaPlanOptimizer()
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

if __name__ == "__main__":
    main()
    
import streamlit as st
from typing import List, Optional
from configs import *
from dataclasses import dataclass


@dataclass
class ValidationError:
    """
    Микрокласс для стандартизации ошибок валидации входных параметров
    """
    field: str
    message: str


class CategoryWidgetGroup:
    """
    Группа виджетов для описания категории медиаплана.
    """

    def __init__(
        self,
        group_id: int,
        vertical: str,
        preset: dict = None,
        on_delete = None,
    ):
        """
        Класс, позволяющий удобно создавать группы подобных по структуре категорий
        
        :param group_id: уникальный идентификатор группы (для генерации ключей виджетов).
        :param vertical: вертикаль, в которой происходит создание категории
        :param preset: словарь характеристики пресета (если не пресет, то будет просто None)
        :param on_delete: callback, вызываемый при нажатии кнопки удаления категории
        """
        self.group_id = group_id
        self._vertical = vertical
        self._incoming_options = LOGICAL_CATEGORIES[vertical]
        self._on_delete = on_delete
        self._preset = preset
        self._prefix = f"{vertical}_cat_group_{group_id}"
        
    def _init_default(self, name: str, default):
        """Инициализирует значение в session_state, если его ещё нет."""
        key = self._key(name)
        if key not in st.session_state:
            st.session_state[key] = default

    def _key(self, name: str) -> str:
        """
        Функция для генерирации уникального ключа виджета (чтобы потом можно было брать с него значение)
        
        :param name: Уникальное имя виджета.
        
        :return: Уникальный ключ для конкретного виджета
        """
        return f"{self._prefix}_{name}"
    
    def _get(self, name: str, default=None):
        """
        Внутренняя функция для получения значения из session_state (нужна для валидации введенных параметров)
        """
        return st.session_state.get(self._key(name), default)
    
    def validate(self) -> List[ValidationError]:
        """
        Функция для проверки введенных значений у виджетов и возврата списка ошибок (если все корректно, то список пустой)
        """
        errors: List[ValidationError] = []

        # 1. Название категории не пустое (или не одни пробелы)
        name = self._get("name", "")
        if not name or not name.strip():
            errors.append(ValidationError(
                field="name",
                message="Название категории не должно быть пустым.",
            ))

        # 2. Хотя бы одна входящая логическая категория
        incoming = self._get("incoming_categories", [])
        if not incoming:
            errors.append(ValidationError(
                field="incoming_categories",
                message="Выберите хотя бы одну входящую логическую категорию.",
            ))
            
        # 3. Должны быть заполнены поля с хроно, ЦА и конкурентами
        chrono = self._get("chrono", None)
        if not chrono:
            errors.append(ValidationError("chrono", "Выберите хроно роликов"))

        target_audience = self._get("target_audience", None)
        if not target_audience:
            errors.append(ValidationError("target_audience", "Выберите целевую аудиторию"))

        competitor_category = self._get("competitor_category", None)
        if not competitor_category:
            errors.append(ValidationError("competitor_category", "Выберите категорию конкурентов"))

        # 4. Минимальные значения ≤ максимальных (для числа РК, бюджетов, длительностей месячных)
        min_campaigns = self._get("min_campaigns", 1)
        max_campaigns = self._get("max_campaigns", 2)
        if min_campaigns > max_campaigns:
            errors.append(ValidationError(
                field="campaigns",
                message=f"Мин. число РК ({min_campaigns}) > макс. ({max_campaigns}).",
            ))

        min_budget = self._get("min_budget", 100_000_000)
        max_budget = self._get("max_budget", 500_000_000)
        if min_budget > max_budget:
            errors.append(ValidationError(
                field="budget",
                message=f"Мин. бюджет ({min_budget:,}) > макс. ({max_budget:,}).",
            ))

        min_duration = self._get("min_duration", 1)
        max_duration = self._get("max_duration", 2)
        if min_duration > max_duration:
            errors.append(ValidationError(
                field="duration",
                message=f"Мин. длительность ({min_duration}) > макс. ({max_duration}).",
            ))

        # 5. Количество обязательных месяцев старта ≤ мин. числа РК
        mandatory_months = self._get("mandatory_months", [])
        if len(mandatory_months) > min_campaigns:
            errors.append(ValidationError(
                field="mandatory_months",
                message=(
                    f"Выбрано обязательных месяцев ({len(mandatory_months)}) "
                    f"больше, чем мин. число РК ({min_campaigns})."
                ),
            ))

        # 6. Если обязательные месяцы старта пустые, то чекбокс не должен быть активен
        only_mandatory = self._get("only_mandatory_months", False)
        if only_mandatory and not mandatory_months:
            errors.append(ValidationError(
                field="only_mandatory_months",
                message=(
                    "Чекбокс «Старт только в обязательные месяцы» активен, "
                    "но обязательные месяцы не выбраны."
                ),
            ))

        return errors

    def render(self) -> List[ValidationError]:
        """
        Функция для отрисовки всей группы виджетов + добавляет inline-ошибки, при некорректных введенных данных
        """

        # --- Строка 1: Название категории | Входящие логические категории ---
        col1, col2 = st.columns(2, vertical_alignment="bottom")
        with col1:
            if self._preset:
                st.info(f"🔒 {self._preset['category_name']}")
                st.session_state[self._key("name")] = self._preset["category_name"]
            else:
                # Получаем доступные категории для вертикали (чтобы могли из них выбирать)
                categories_by_vert = st.session_state.get("categories", {})
                trp_categories = categories_by_vert.get(self._vertical, [])
                has_trp_categories = len(trp_categories) > 0
                radio_options = ["📋 С листа TRP Cost", "✏️ Вручную"]
                self._init_default("name_input_mode", radio_options[0] if has_trp_categories else radio_options[1])
                
                input_mode = st.radio(
                    "Способ ввода названия",
                    options=radio_options,
                    key=self._key("name_input_mode"),
                    horizontal=True,
                    label_visibility="collapsed"
                )
                
                st.markdown("**Название категории**")
                
                if input_mode == "📋 С листа TRP Cost":
                    if has_trp_categories:
                        saved_name = self._get("name_from_list", None) # копия
                        if saved_name and saved_name not in trp_categories:
                            trp_categories.append(saved_name)
                            
                        self._init_default("name_from_list", saved_name)    
                        selected = st.selectbox(
                            "Название категории",
                            options=trp_categories,
                            key=self._key("name_from_list"),
                            placeholder=f"Выберите категорию ({self._vertical})...",
                            help=f"Категории для вертикали «{self._vertical}» из листа TRP cost",
                            label_visibility="collapsed"
                        )
                        
                        st.session_state[self._key("name")] = selected or ""
                    else:
                        st.warning(
                            f"Нет доступных категорий для вертикали «{self._vertical}». "
                            "Загрузите таблицу или введите вручную."
                        )
                        
                        st.session_state[self._key("name")] = ""
                        
                else:
                    self._init_default("name_manual", "")
                    st.text_input(
                        "Название категории",
                        key=self._key("name_manual"),
                        placeholder="Введите название категории...",
                        help="Произвольное название категории",
                        label_visibility="collapsed"
                    )
                    
                    st.session_state[self._key("name")] = (
                        st.session_state.get(self._key("name_manual"), "")
                    )
                    
        with col2:
            if self._preset:
                st.info(f"🔒 {', '.join(self._preset['logical_category'])}")
                st.session_state[self._key("incoming_categories")] = self._preset["logical_category"]
            else:
                saved_incoming = self._get("incoming_categories", [])
                available_options = list(self._incoming_options)
                # Добавляем сохранённые значения, если их нет в options
                for val in saved_incoming:
                    if val not in available_options:
                        available_options.append(val)
                
                self._init_default("incoming_categories", [])
                st.multiselect(
                    "Входящие логические категории",
                    options=available_options,
                    key=self._key("incoming_categories"),
                )

        # --- Строка 2: Минимальный TRP | Минимальный SOV | ROMI по умолчанию ---
        col3, col4, col5 = st.columns(3)
        with col3:
            self._init_default("min_trp", DEF_TRP)
            st.number_input(
                "Минимальный TRP",
                min_value=MIN_TRP,
                max_value=MAX_TRP,
                step=STEP_TRP,
                key=self._key("min_trp"),
            )
        with col4:
            self._init_default("min_sov", DEF_SOV)
            st.number_input(
                "Минимальный SOV",
                min_value=MIN_SOV,
                max_value=MAX_SOV,
                step=STEP_SOV,
                format="%.2f",
                key=self._key("min_sov"),
            )
        with col5:
            self._init_default("default_romi", DEF_ROMI)
            st.number_input(
                "ROMI по умолчанию",
                min_value=MIN_ROMI,
                max_value=MAX_ROMI,
                step=STEP_ROMI,
                key=self._key("default_romi"),
                help="Значение ROMI, используемое при прогнозе DTB для разрезов, где не было РК ранее (при мин. TRP и SOV)"
            )
            
        # --- Строка 3: Хроно | ЦА | Категория конкурентов ---
        col6, col7, col8 = st.columns(3)
        with col6:
            chrono_options = ["20/10 s", "40/20 s"]
            saved_chrono = self._get("chrono", None)
            if saved_chrono and saved_chrono not in chrono_options:
                chrono_options.append(saved_chrono)
            
            self._init_default("chrono", saved_chrono)
            st.selectbox(
                "Хроно роликов",
                options=chrono_options,
                key=self._key("chrono"),
                placeholder="Выберите...",
                help="Два варианта размещений, по которым корректируется стоимость TRP",
            )
            
        with col7:
            loaded_audiences = st.session_state.get("target_audiences", [])
            target_audience_options = loaded_audiences if loaded_audiences else ["Нет"]
            saved_ta = self._get("target_audience", None)
            if saved_ta and saved_ta not in target_audience_options:
                target_audience_options.append(saved_ta)
            
            self._init_default("target_audience", saved_ta)
            st.selectbox(
                "Целевая аудитория",
                options=target_audience_options,
                key=self._key("target_audience"),
                placeholder="Выберите...",
                help="Все варианты ЦА из гугл-таблички со стоимостями TRP",
            )
            
        with col8:
            comp_categories_options = ["Нет"] + st.session_state.get("competitor_categories", [])
            saved_comp = self._get("competitor_category", None)
            if saved_comp and saved_comp not in comp_categories_options:
                comp_categories_options.append(saved_comp)
            
            self._init_default("competitor_category", saved_comp)
            st.selectbox(
                "Категория конкурентов",
                options=comp_categories_options,
                key=self._key("competitor_category"),
                placeholder="Выберите...",
                help="Категория конкурентов из таблицы TRP (если конкурентов нет, то выберитие опцию «Нет»)",
            )

        # --- Строка 4: Мин. число РК | Макс. число РК ---
        col9, col10 = st.columns(2)
        with col9:
            self._init_default("min_campaigns", DEF_RK_MIN)
            st.number_input(
                "Минимальное число РК в категории",
                min_value=MIN_RK,
                max_value=MAX_RK,
                step=STEP_RK,
                key=self._key("min_campaigns"),
            )
        with col10:
            self._init_default("max_campaigns", DEF_RK_MAX)
            st.number_input(
                "Максимальное число РК в категории",
                min_value=MIN_RK,
                max_value=MAX_RK,
                step=STEP_RK,
                key=self._key("max_campaigns"),
            )

        # --- Строка 4: Мин. бюджет | Макс. бюджет ---
        col11, col12 = st.columns(2)
        with col11:
            self._init_default("min_budget", DEF_BUDG_MIN)
            st.number_input(
                "Минимальный суммарнный бюджет на все РК в категории (в млн. руб.)",
                min_value=MIN_BUDG,
                max_value=MAX_BUDG,
                step=STEP_BUDG,
                key=self._key("min_budget"),
            )
        with col12:
            self._init_default("max_budget", DEF_BUDG_MAX)
            st.number_input(
                "Максимальный суммарный бюджет на все РК в категории (в млн. руб.)",
                min_value=MIN_BUDG,
                max_value=MAX_BUDG,
                step=STEP_BUDG,
                key=self._key("max_budget"),
            )

        # --- Строка 5: Мин. длительность | Макс. длительность ---
        col13, col14 = st.columns(2)
        with col13:
            self._init_default("min_duration", DEF_LEN_MIN)
            st.number_input(
                "Минимальная длительность РК в категории (мес.)",
                min_value=MIN_LEN,
                max_value=MAX_LEN,
                step=STEP_LEN,
                key=self._key("min_duration"),
            )
        with col14:
            self._init_default("max_duration", DEF_LEN_MAX)
            st.number_input(
                "Максимальная длительность РК в категории (мес.)",
                min_value=MIN_LEN,
                max_value=MAX_LEN,
                step=STEP_LEN,
                key=self._key("max_duration"),
            )

        # --- Строка 6: Обязательные месяцы | Чекбокс | Кнопка удаления ---
        col15, col16, col17 = st.columns([3, 2, 1], vertical_alignment="bottom")
        with col15:
            self._init_default("mandatory_months", [])
            st.multiselect(
                "Обязательные месяцы проведения РК",
                options=DEFAULT_MONTHS,
                key=self._key("mandatory_months"),
                help="Месяцы, когда обязана идти РК в данном разрезе (если это не требуется, то нужно оставить пустым)"
            )
        with col16:
            self._init_default("only_mandatory_months", False)
            st.checkbox(
                "Старт только в обязательные месяцы",
                key=self._key("only_mandatory_months"),
                help='Если флаг выставлен, то РК может начинаться ТОЛЬКО в обязательные месяцы'
            )
        with col17:
            st.button(
                "Удалить категорию",
                key=self._key("delete"),
                on_click=self._on_delete,
                args=(self.group_id,) if self._on_delete else None,
                use_container_width=True,
                type="primary"
            )
    
        # --- Валидация и вывод ошибок ---
        errors = self.validate()
        if errors:
            st.divider()
            for err in errors:
                st.error(f"⚠️ {err.message}")

        return errors

    def get_values(self) -> dict:
        """
        Функция для возвращения текущих значений всех виджетов группы
        
        :return: Словарь в формате название виджета (типовое) - значение в нем
        """
        
        # Перевод названий месяцев в их номера
        month_to_num = {
            'Январь': 1, 'Февраль': 2, 'Март': 3,
            'Апрель': 4, 'Май': 5, 'Июнь': 6,
            'Июль': 7, 'Август': 8, 'Сентябрь': 9,
            'Октябрь': 10, 'Ноябрь': 11, 'Декабрь': 12,
        }
        months = [month_to_num[month] for month in st.session_state.get(self._key("mandatory_months"), [])]
        
        return {
            "name": st.session_state.get(self._key("name"), ""),
            "vertical": self._vertical,
            "logical_category": st.session_state.get(self._key("incoming_categories"), []),
            "min_trp":  st.session_state.get(self._key("min_trp"), 1500),
            "min_sov":  st.session_state.get(self._key("min_sov"), 0.13),
            "default_romi":  st.session_state.get(self._key("default_romi"), -90.0) / 100,
            "chrono": self._get("chrono", '20/10 s'),
            "target_audience": self._get("target_audience", 'Нет'),
            "competitor_category": self._get("competitor_category", ''),
            "min_campaigns":  st.session_state.get(self._key("min_campaigns"), 1),
            "max_campaigns":  st.session_state.get(self._key("max_campaigns"), 2),
            "min_budget":  st.session_state.get(self._key("min_budget"), 100) * 1_000_000,
            "max_budget":  st.session_state.get(self._key("max_budget"), 500) * 1_000_000,
            "min_duration":  st.session_state.get(self._key("min_duration"), 1),
            "max_duration":  st.session_state.get(self._key("max_duration"), 2),
            "start_months":  months,
            "strict_start":  st.session_state.get(self._key("only_mandatory_months"), False),
        }

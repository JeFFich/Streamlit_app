"""
Модуль визуализации результатов анализа медиаплана (в plotly и на гугл-диске)
"""

import plotly.graph_objects as go
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ КОМПОНЕНТЫ
# =============================================================================

# Символы для замены True/False в таблицах проверок
CHECK_MARK = "✅"
CROSS_MARK = "❌"

# Русские названия месяцев
MONTH_LABELS = [
    'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
    'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'
]

def _fmt_num(value: float) -> str:
    """Форматирует число с разделением триад пробелами."""
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(value)

def _fmt_money_mln(value: float) -> str:
    """Форматирует денежное значение как округлённое число миллионов с буквой М."""
    try:
        mln = int(round(float(value) / 1_000_000))
        return f"{_fmt_num(mln)} М"
    except (ValueError, TypeError):
        return str(value)

def _fmt_pct(value: float, digits: int = 1) -> str:
    """Форматирует число как процент."""
    try:
        return f"{int(round(value*100))} %"
    except (ValueError, TypeError):
        return str(value)

def _fmt_month(value) -> str:
    """Форматирует номер месяца как трёхбуквенное название."""
    try:
        return MONTH_LABELS[int(value) - 1]
    except (ValueError, TypeError, IndexError):
        return str(value)

# =============================================================================
# ПОСТРОЕНИЕ ПЛАНА В PLOTLY
# =============================================================================

def _prepare_detail_df(detail_df: pd.DataFrame) -> pd.DataFrame:
    """Форматирует детальную таблицу РК для вывода."""
    if detail_df.empty:
        return detail_df.copy()

    out = pd.DataFrame({
        "Категория": detail_df["category"],
        "Вертикаль": detail_df["vertical"],
        "Месяц старта": detail_df["month_start"].apply(_fmt_month),
        "Месяц окончания": detail_df["month_end"].apply(_fmt_month),
        "TRP": detail_df["TRP"].apply(_fmt_num),
        "Бюджет": detail_df["budget"].apply(_fmt_money_mln),
        "TRP конкурентов": detail_df["comp_TRP"].apply(_fmt_num),
        "SOV": detail_df["SOV"].apply(_fmt_pct),
        "DTB прогноз": detail_df["DTB_pred"].apply(_fmt_num),
        "Выручка прогноз": detail_df["Revenue_pred"].apply(_fmt_money_mln),
        "ROMI прогноз": detail_df["ROMI_pred"].apply(lambda x: _fmt_pct(x, 2)),
    })
    return out

def _prepare_summary_df(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Форматирует сводную таблицу по вертикалям для вывода."""
    if summary_df.empty:
        return summary_df.copy()

    out = pd.DataFrame({
        "Вертикаль": summary_df["vertical"],
        "Кол-во РК": summary_df["num_campaigns"],
        "Суммарный TRP": summary_df["total_trp"].apply(_fmt_num),
        "SOV за периоды размещения": summary_df["sov_active"].apply(_fmt_pct),
        "SOV за год": summary_df["sov_year"].apply(_fmt_pct),
        "Бюджет": summary_df["total_budget"].apply(_fmt_money_mln),
        "DTB": summary_df["total_dtb"].apply(_fmt_num),
        "Выручка": summary_df["total_revenue"].apply(_fmt_money_mln),
        "ROMI": summary_df["romi"].apply(lambda x: _fmt_pct(x, 2)),
    })
    return out

def _prepare_checks_df(checks_df: pd.DataFrame, index_label: str) -> pd.DataFrame:
    """
    Форматирует таблицу проверок: True → галочка, False → крестик.
    Индекс (категория или вертикаль) выносится в первый столбец.
    """
    if checks_df.empty:
        return checks_df.copy()

    out = checks_df.copy()

    # Заменяем True/False на символы
    for col in out.columns:
        out[col] = out[col].apply(lambda v: CHECK_MARK if bool(v) else CROSS_MARK)

    # Сбрасываем индекс в столбец
    out = out.reset_index()
    out = out.rename(columns={out.columns[0]: index_label})

    return out

def _build_table_trace(
    df: pd.DataFrame,
    visible: bool = False,
    header_color: str = "#4472C4",
    cell_color: str = "#F2F2F2"
) -> go.Table:
    """Строит один trace go.Table из DataFrame."""
    if df.empty:
        return go.Table(
            header=dict(values=["Нет данных"]),
            cells=dict(values=[[]]),
            visible=visible,
        )
    
    n_cols = len(df.columns)
    cell_values = []
    for i, c in enumerate(df.columns):
        col_values = df[c].astype(str).tolist()
        if i == 0:
            col_values = [f"<b>{v}</b>" for v in col_values]
        cell_values.append(col_values)

    return go.Table(
        columnwidth=[1.4] + [1.0] * (n_cols - 1),
        header=dict(
            values=[f"<b>{c}</b>" for c in df.columns],
            fill_color=header_color,
            font=dict(color="white", size=11),
            align="center",
            height=42,
            line=dict(color="#DDDDDD", width=1),
        ),
        cells=dict(
            values=cell_values,
            fill_color=cell_color,
            font=dict(color="black", size=10),
            align="center",
            height=28,
            line=dict(color="#DDDDDD", width=1),
        ),
        visible=visible,
    )

def create_analysis_plotly_view(
    detail_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    cat_checks: pd.DataFrame,
    vert_checks: pd.DataFrame,
):
    """
    Строит единую Plotly Figure с переключателем между четырьмя таблицами:
    - Детальная таблица по РК
    - Сводка по вертикалям
    - Проверки по категориям
    - Проверки по вертикалям

    :param detail_df: Детальная таблица РК.
    :param summary_df: Сводка по вертикалям.
    :param cat_checks: Таблица проверок по категориям.
    :param vert_checks: Таблица проверок по вертикалям.
    :return: self.pegure с dropdown-переключателем.
    """
    # Подготавливаем форматированные таблицы
    detail_fmt = _prepare_detail_df(detail_df)
    summary_fmt = _prepare_summary_df(summary_df)
    cat_checks_fmt = _prepare_checks_df(cat_checks, "Категория")
    vert_checks_fmt = _prepare_checks_df(vert_checks, "Вертикаль")

    tabs = [
        ("Список по отдельным РК", detail_fmt),
        ("Сводка по вертикалям", summary_fmt),
        ("Сводка проверок по ограничениям категорий", cat_checks_fmt),
        ("Сводка проверок по ограничениям вертикалей", vert_checks_fmt),
    ]

    fig = go.Figure()

    # Добавляем по одному trace на каждую таблицу
    for i, (_, df) in enumerate(tabs):
        fig.add_trace(_build_table_trace(df, visible=(i == 0)))

    # Кнопки переключателя
    buttons = []
    for i, (label, _) in enumerate(tabs):
        visibility = [False] * len(tabs)
        visibility[i] = True
        buttons.append(dict(
            label=label,
            method="update",
            args=[
                {"visible": visibility},
                {"title": {"text": ""}},
            ],
        ))

    fig.update_layout(
        updatemenus=[
            dict(
                type="dropdown",
                direction="down",
                x=1.0,
                xanchor="right",
                y=1.18,
                yanchor="top",
                buttons=buttons,
                showactive=True,
                active=0,
                bgcolor="white",
                bordercolor="#cccccc",
                font=dict(size=13),
            )
        ],
        height=700,
        margin=dict(l=20, r=20, t=120, b=20),
    )

    return fig

# =============================================================================
# ПОСТРОЕНИЕ ПЛАНА НА ГУГЛ-ДИСКЕ
# =============================================================================

def _fill_detail_sheet(worksheet: gspread.Worksheet, detail_df: pd.DataFrame):
    """Заполняет лист с детальной таблицей по всем РК."""
    header = [
        "Категория", "Вертикаль", "Месяц старта", "Месяц окончания",
        "TRP", "Бюджет", "TRP конкурентов", "SOV",
        "DTB прогноз", "Выручка прогноз", "ROMI прогноз"
    ]

    rows = []
    for _, row in detail_df.iterrows():
        rows.append([
            row["category"],
            row["vertical"],
            _fmt_month(row["month_start"]),
            _fmt_month(row["month_end"]),
            _fmt_num(row["TRP"]),
            _fmt_money_mln(row["budget"]),
            _fmt_num(row["comp_TRP"]),
            _fmt_pct(row["SOV"]),
            _fmt_num(row["DTB_pred"]),
            _fmt_money_mln(row["Revenue_pred"]),
            _fmt_pct(row["ROMI_pred"], 2),
        ])

    all_cells = [
        {'range': 'A1', 'values': [header]}
    ]
    if rows:
        all_cells.append({'range': 'A2', 'values': rows})

    worksheet.batch_update(all_cells, value_input_option='RAW')

    _format_simple_table(worksheet, num_rows=len(rows), num_cols=len(header))

def _fill_summary_sheet(worksheet: gspread.Worksheet, summary_df: pd.DataFrame):
    """Заполняет лист со сводной таблицей по вертикалям."""
    header = [
        "Вертикаль", "Кол-во РК", "Суммарный TRP", "SOV за периоды размещения",
        "SOV за год", "Бюджет", "DTB", "Выручка", "ROMI"
    ]

    rows = []
    total_row_idx = None  # 1-based позиция строки "ИТОГО"
    for i, (_, row) in enumerate(summary_df.iterrows()):
        is_total = str(row["vertical"]).strip().upper() == "ИТОГО"
        if is_total:
            total_row_idx = 2 + i  # +2 = заголовок (1) + 1

        rows.append([
            row["vertical"],
            int(row["num_campaigns"]),
            _fmt_num(row["total_trp"]),
            _fmt_pct(row["sov_active"]),
            _fmt_pct(row["sov_year"]),
            _fmt_money_mln(row["total_budget"]),
            _fmt_num(row["total_dtb"]),
            _fmt_money_mln(row["total_revenue"]),
            _fmt_pct(row["romi"], 2),
        ])

    all_cells = [
        {'range': 'A1', 'values': [header]}
    ]
    if rows:
        all_cells.append({'range': 'A2', 'values': rows})

    worksheet.batch_update(all_cells, value_input_option='RAW')

    _format_simple_table(
        worksheet,
        num_rows=len(rows),
        num_cols=len(header),
        highlight_row_1based=total_row_idx
    )

def _fill_checks_sheet(
    worksheet: gspread.Worksheet,
    cat_checks: pd.DataFrame,
    vert_checks: pd.DataFrame
):
    """
    Заполняет лист с проверками: сначала по категориям, затем по вертикалям.
    True → ✅, False → ❌
    """
    all_cells = []

    # --- Секция: Проверки по категориям ---
    all_cells.append({'range': 'A1', 'values': [["ПРОВЕРКИ ПО КАТЕГОРИЯМ"]]})

    cat_header = ["Категория"] + list(cat_checks.columns)
    all_cells.append({'range': 'A2', 'values': [cat_header]})

    cat_rows = []
    for idx, row in cat_checks.iterrows():
        cat_rows.append(
            [idx] + [CHECK_MARK if bool(v) else CROSS_MARK for v in row.values]
        )

    if cat_rows:
        all_cells.append({'range': 'A3', 'values': cat_rows})

    # --- Секция: Проверки по вертикалям ---
    vert_section_start = 2 + len(cat_rows) + 2  # 1-based номер строки заголовка
    all_cells.append({
        'range': f'A{vert_section_start}',
        'values': [["ПРОВЕРКИ ПО ВЕРТИКАЛЯМ"]]
    })

    vert_header = ["Вертикаль"] + list(vert_checks.columns)
    all_cells.append({
        'range': f'A{vert_section_start + 1}',
        'values': [vert_header]
    })

    vert_rows = []
    for idx, row in vert_checks.iterrows():
        vert_rows.append(
            [idx] + [CHECK_MARK if bool(v) else CROSS_MARK for v in row.values]
        )

    if vert_rows:
        all_cells.append({
            'range': f'A{vert_section_start + 2}',
            'values': vert_rows
        })

    worksheet.batch_update(all_cells, value_input_option='RAW')

    # --- Форматирование ---
    _format_checks_sheet(
        worksheet,
        num_cat_rows=len(cat_rows),
        num_cat_cols=len(cat_header),
        vert_section_start=vert_section_start,
        num_vert_rows=len(vert_rows),
        num_vert_cols=len(vert_header),
    )

def _format_simple_table(
    worksheet: gspread.Worksheet,
    num_rows: int,
    num_cols: int,
    highlight_row_1based: int = None
):
    """
    Базовое форматирование таблицы:
    - Заголовок (A1) — жирный, крупный
    - Шапка (строка 3) — жирная, серый фон
    - Границы
    - Автоширина столбцов
    - Опциональная подсветка строки "ИТОГО"
    """
    sheet_id = worksheet.id
    requests = []

    # Шапка
    requests.append({
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 0, 'endRowIndex': 1,
                'startColumnIndex': 0, 'endColumnIndex': num_cols
            },
            'cell': {
                'userEnteredFormat': {
                    'textFormat': {'bold': True, 'fontSize': 10},
                    'backgroundColor': {'red': 0.92, 'green': 0.92, 'blue': 0.92},
                    'horizontalAlignment': 'CENTER'
                }
            },
            'fields': 'userEnteredFormat(textFormat,backgroundColor,horizontalAlignment)'
        }
    })
    
    # Первый столбец данных — жирный (со строки 2 до конца данных)
    if num_rows > 0:
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 1,
                    'endRowIndex': 1 + num_rows,
                    'startColumnIndex': 0,
                    'endColumnIndex': 1
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'bold': True, 'fontSize': 10}
                    }
                },
                'fields': 'userEnteredFormat.textFormat'
            }
        })

    # Подсветка строки ИТОГО (слабо-красный фон)
    if highlight_row_1based is not None:
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': highlight_row_1based - 1,
                    'endRowIndex': highlight_row_1based,
                    'startColumnIndex': 0, 'endColumnIndex': num_cols
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'bold': True, 'fontSize': 10},
                        'backgroundColor': {'red': 1.0, 'green': 0.85, 'blue': 0.85}
                    }
                },
                'fields': 'userEnteredFormat(textFormat,backgroundColor)'
            }
        })

    # Границы
    if num_rows > 0:
        requests.append({
            'updateBorders': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 0,
                    'endRowIndex': 1 + num_rows,
                    'startColumnIndex': 0,
                    'endColumnIndex': num_cols
                },
                'top': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
                'bottom': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
                'left': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
                'right': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
                'innerHorizontal': {'style': 'SOLID', 'color': {'red': 0.85, 'green': 0.85, 'blue': 0.85}},
                'innerVertical': {'style': 'SOLID', 'color': {'red': 0.85, 'green': 0.85, 'blue': 0.85}},
            }
        })

    # Автоширина
    requests.append({
        'autoResizeDimensions': {
            'dimensions': {
                'sheetId': sheet_id,
                'dimension': 'COLUMNS',
                'startIndex': 0, 'endIndex': num_cols
            }
        }
    })

    worksheet.spreadsheet.batch_update({'requests': requests})

def _format_checks_sheet(
    worksheet: gspread.Worksheet,
    num_cat_rows: int,
    num_cat_cols: int,
    vert_section_start: int,
    num_vert_rows: int,
    num_vert_cols: int
):
    """Форматирование совмещённого листа с проверками."""
    sheet_id = worksheet.id
    max_cols = max(num_cat_cols, num_vert_cols)
    requests = []

    # Подзаголовки секций
    for row_1based in [1, vert_section_start]:
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': row_1based - 1,
                    'endRowIndex': row_1based,
                    'startColumnIndex': 0,
                    'endColumnIndex': max_cols
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'bold': True, 'fontSize': 11}
                    }
                },
                'fields': 'userEnteredFormat.textFormat'
            }
        })

    # Шапки таблиц (строка 2 и vert_section_start + 1)
    for row_1based, cols in [(2, num_cat_cols), (vert_section_start + 1, num_vert_cols)]:
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': row_1based - 1,
                    'endRowIndex': row_1based,
                    'startColumnIndex': 0,
                    'endColumnIndex': cols
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'bold': True, 'fontSize': 10},
                        'backgroundColor': {'red': 0.92, 'green': 0.92, 'blue': 0.92},
                        'horizontalAlignment': 'CENTER',
                        'wrapStrategy': 'WRAP'
                    }
                },
                'fields': 'userEnteredFormat(textFormat,backgroundColor,horizontalAlignment,wrapStrategy)'
            }
        })

    # Центрирование данных в обеих секциях
    for start_row_1based, n_rows, n_cols in [
        (3, num_cat_rows, num_cat_cols),
        (vert_section_start + 2, num_vert_rows, num_vert_cols),
    ]:
        if n_rows > 0:
            requests.append({
                'repeatCell': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': start_row_1based - 1,
                        'endRowIndex': start_row_1based - 1 + n_rows,
                        'startColumnIndex': 1,  # Первый столбец (название) выравниваем отдельно
                        'endColumnIndex': n_cols
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'horizontalAlignment': 'CENTER',
                            'textFormat': {'fontSize': 12}
                        }
                    },
                    'fields': 'userEnteredFormat(horizontalAlignment,textFormat)'
                }
            })

    # Границы для обеих секций
    for start_row_1based, n_rows, n_cols in [
        (2, num_cat_rows, num_cat_cols),
        (vert_section_start + 1, num_vert_rows, num_vert_cols),
    ]:
        if n_rows > 0:
            requests.append({
                'updateBorders': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': start_row_1based - 1,
                        'endRowIndex': start_row_1based - 1 + 1 + n_rows,
                        'startColumnIndex': 0,
                        'endColumnIndex': n_cols
                    },
                    'top': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
                    'bottom': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
                    'left': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
                    'right': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
                    'innerHorizontal': {'style': 'SOLID', 'color': {'red': 0.85, 'green': 0.85, 'blue': 0.85}},
                    'innerVertical': {'style': 'SOLID', 'color': {'red': 0.85, 'green': 0.85, 'blue': 0.85}},
                }
            })

    # Автоширина
    requests.append({
        'autoResizeDimensions': {
            'dimensions': {
                'sheetId': sheet_id,
                'dimension': 'COLUMNS',
                'startIndex': 0,
                'endIndex': max_cols
            }
        }
    })

    worksheet.spreadsheet.batch_update({'requests': requests})
    
def create_analysis_google_sheet(
    detail_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    cat_checks: pd.DataFrame,
    vert_checks: pd.DataFrame,
    folder_id: str = '1Pba508FSa2JKGT0vVq7sqlgMzFE2euEm'
) -> str:
    """
    Создаёт Google-таблицу с результатами анализа медиаплана.

    Структура:
        - Лист 1 "Информация по РК": детальная таблица всех РК
        - Лист 2 "Сводка": агрегированная информация по вертикалям
        - Лист 3 "Проверки": сначала проверки категорий, затем — вертикалей

    :param detail_df: Детальная таблица РК.
    :param summary_df: Сводка по вертикалям.
    :param cat_checks: Таблица проверок по категориям.
    :param vert_checks: Таблица проверок по вертикалям.
    :param folder_id: ID папки на Google Drive, куда создаются анализы
    
    :return: URL созданной таблицы.
    """
    # Авторизация через личный аккаунт
    token_info = st.secrets["token"]
    
    creds = Credentials(
        token=token_info["token"],
        refresh_token=token_info["refresh_token"],
        token_uri=token_info["token_uri"],
        client_id=token_info["client_id"],
        client_secret=token_info["client_secret"],
        scopes=list(token_info["scopes"]),
    )
    
    if creds.expired or not creds.valid:
        creds.refresh(Request())
    
    gc = gspread.authorize(creds)

    timestamp = datetime.now(ZoneInfo('Europe/Moscow')).strftime("%Y-%m-%d_%H-%M-%S")
    sheet_title = f"Анализ_медиаплана_{timestamp}"

    spreadsheet = gc.create(sheet_title, folder_id=folder_id)
    spreadsheet.share('', perm_type='anyone', role='writer')

    # === Лист 1: Информация по РК ===
    ws_detail = spreadsheet.sheet1
    ws_detail.update_title("Информация по РК")
    _fill_detail_sheet(ws_detail, detail_df)

    # === Лист 2: Сводка по вертикалям ===
    ws_summary = spreadsheet.add_worksheet(title="Сводка", rows=100, cols=15)
    _fill_summary_sheet(ws_summary, summary_df)

    # === Лист 3: Проверки ===
    ws_checks = spreadsheet.add_worksheet(title="Проверки", rows=200, cols=20)
    _fill_checks_sheet(ws_checks, cat_checks, vert_checks)

    return spreadsheet.url

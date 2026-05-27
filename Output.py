import plotly.graph_objects as go
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List
import streamlit as st

from configs import BUDGET_COEFF_CORRECTRION


# =========================================================================
# ОТОБРАЖЕНИЕ ФЛОУЧАРТА В СТРИМЛИТЕ
# =========================================================================

def _get_category_color(category_idx: int) -> str:
    """Возвращает цвет для категории по её индексу."""
    colors = [
        'rgba(33, 150, 243, 0.7)',
        'rgba(76, 175, 80, 0.7)',
        'rgba(255, 152, 0, 0.7)',
        'rgba(156, 39, 176, 0.7)',
        'rgba(244, 67, 54, 0.7)',
        'rgba(0, 188, 212, 0.7)',
        'rgba(121, 85, 72, 0.7)',
        'rgba(96, 125, 139, 0.7)',
        'rgba(233, 30, 99, 0.7)',
        'rgba(63, 81, 181, 0.7)',
        'rgba(139, 195, 74, 0.7)',
        'rgba(255, 87, 34, 0.7)',
    ]
    return colors[category_idx % len(colors)]

def create_media_plan_chart(plan_df: pd.DataFrame, show_revenue: bool = True):
    """
    Строит интерактивный флоучарт медиаплана с переключением между вертикалями.
    """

    month_labels = [
        'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
        'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'
    ]

    verticals = sorted(plan_df['vertical'].unique())

    fig = go.Figure()

    # Назначаем цвета по категориям (единый цвет для каждой категории)
    all_categories = sorted(plan_df['category'].unique())
    category_colors = {
        cat: _get_category_color(idx)
        for idx, cat in enumerate(all_categories)
    }

    # Для каждой вертикали собираем данные
    traces_per_vertical = {}

    for vertical in verticals:
        v_df = plan_df[plan_df['vertical'] == vertical].copy()
        categories = sorted(v_df['category'].unique())

        if not categories:
            continue

        traces_per_vertical[vertical] = {
            'categories': categories,
            'campaigns': []
        }

        for _, row in v_df.iterrows():
            cat_idx = categories.index(row['category'])
            start = int(row['start_month'])
            end = int(row['end_month'])
            color = category_colors[row['category']]

            # Формируем hover-текст
            if show_revenue:
                hover_text = (
                    f"<b>TRP:</b> {int(row['total_trp']):,}<br>"
                    f"<b>SOV:</b> {row['sov']:.1%}<br>"
                    f"<b>Бюджет:</b> {row['budget']:,.0f} ₽<br>"
                    f"<br>"
                    f"<b>Прогноз DTB:</b> {row['dtb']:,.0f}<br>"
                    f"<b>Прогноз выручки:</b> {row['revenue']:,.0f} ₽<br>"
                    f"<b>ROMI:</b> {row['romi']:.2%}"
                )
            else:
                hover_text = (
                    f"<b>TRP:</b> {int(row['total_trp']):,}<br>"
                    f"<b>SOV:</b> {row['sov']:.1%}<br>"
                    f"<b>Бюджет:</b> {row['budget'] * BUDGET_COEFF_CORRECTRION:,.0f} ₽<br>"
                    f"<br>"
                    f"<b>Прогноз DTB:</b> {row['dtb']:,.0f}<br>"
                    f"<b>ROMI:</b> {row['romi']:.2%}"
                )

            traces_per_vertical[vertical]['campaigns'].append({
                'cat_idx': cat_idx,
                'start': start,
                'end': end,
                'color': color,
                'hover_text': hover_text
            })

    # Строим trace'ы
    visibility_map = {}
    trace_idx = 0

    for vertical in verticals:
        data = traces_per_vertical[vertical]
        categories = data['categories']
        campaigns = data['campaigns']

        visibility_map[vertical] = []

        for campaign in campaigns:
            cat_idx = campaign['cat_idx']
            start = campaign['start']
            end = campaign['end']
            color = campaign['color']
            hover_text = campaign['hover_text']

            # Координаты прямоугольника
            x0 = start - 0.4
            x1 = end + 0.4
            y0 = cat_idx - 0.35
            y1 = cat_idx + 0.35

            # Заполненный прямоугольник (без hover)
            rect_trace = go.Scatter(
                x=[x0, x1, x1, x0, x0],
                y=[y0, y0, y1, y1, y0],
                fill='toself',
                fillcolor=color,
                line=dict(color='white', width=1.5),
                mode='lines',
                hoverinfo='skip',
                showlegend=False,
                visible=(vertical == verticals[0])
            )
            fig.add_trace(rect_trace)
            visibility_map[vertical].append(trace_idx)
            trace_idx += 1

            # Прозрачные маркеры для hover
            n_months_span = end - start + 1
            hover_x = list(range(start, end + 1))
            hover_y = [cat_idx] * n_months_span
            hover_texts = [hover_text] * n_months_span

            hover_trace = go.Scatter(
                x=hover_x,
                y=hover_y,
                mode='markers',
                marker=dict(
                    size=30,
                    color='rgba(0,0,0,0)',
                    line=dict(width=0)
                ),
                hoverinfo='text',
                hovertext=hover_texts,
                showlegend=False,
                visible=(vertical == verticals[0])
            )
            fig.add_trace(hover_trace)
            visibility_map[vertical].append(trace_idx)
            trace_idx += 1

    # Dropdown меню
    buttons = []
    for vertical in verticals:
        visibility = [False] * trace_idx
        for idx in visibility_map.get(vertical, []):
            visibility[idx] = True

        categories = traces_per_vertical[vertical]['categories']
        n_cats = len(categories)

        # Жирные названия категорий с отступом
        bold_categories = [f'  <b>{cat}</b>' for cat in categories]

        buttons.append(dict(
            label=vertical,
            method='update',
            args=[
                {'visible': visibility},
                {
                    'yaxis': {
                        'tickvals': list(range(n_cats)),
                        'ticktext': bold_categories,
                        'title': '',
                        'showgrid': False,
                        'range': [-0.5, n_cats - 0.5],
                        'zeroline': False,
                    }
                }
            ]
        ))

    # Layout
    first_vertical = verticals[0]
    first_categories = traces_per_vertical[first_vertical]['categories']
    n_first = len(first_categories)
    bold_first_categories = [f'  <b>{cat}</b>' for cat in first_categories]

    # Разделительные линии
    max_cats = max(len(traces_per_vertical[v]['categories']) for v in verticals)
    shapes = []

    # Вертикальные разделители (между месяцами)
    for m in range(1, 12):
        shapes.append(dict(
            type='line',
            x0=m + 0.5, x1=m + 0.5,
            y0=-0.5, y1=max_cats - 0.5,
            line=dict(color='rgba(200,200,200,0.6)', width=1)
        ))

    # Горизонтальные разделители (между категориями)
    for c in range(1, max_cats):
        shapes.append(dict(
            type='line',
            x0=0.5, x1=12.5,
            y0=c - 0.5, y1=c - 0.5,
            line=dict(color='rgba(200,200,200,0.6)', width=1)
        ))

    # Внешняя рамка
    shapes.append(dict(
        type='rect',
        x0=0.5, x1=12.5,
        y0=-0.5, y1=max_cats - 0.5,
        line=dict(color='rgba(150,150,150,0.8)', width=1.5),
        fillcolor='rgba(0,0,0,0)'
    ))

    fig.update_layout(
        title=dict(
            text='Флоучарт РК',
            font=dict(size=18),
            x=0.5
        ),
        updatemenus=[
            dict(
                type='dropdown',
                direction='down',
                x=1.0,
                xanchor='right',
                y=1.15,
                yanchor='top',
                buttons=buttons,
                showactive=True,
                active=0,
                bgcolor='white',
                bordercolor='#cccccc',
                font=dict(size=13)
            )
        ],
        xaxis=dict(
            tickvals=list(range(1, 13)),
            ticktext=month_labels,
            title='Месяц',
            showgrid=False,
            range=[0.5, 12.5],
            zeroline=False,
        ),
        yaxis=dict(
            tickvals=list(range(n_first)),
            ticktext=bold_first_categories,
            title='',  # Убрана подпись вертикальной оси
            showgrid=False,
            range=[-0.5, n_first - 0.5],
            zeroline=False,
        ),
        plot_bgcolor='white',
        hoverlabel=dict(
            bgcolor='white',
            font_size=14,
            font_family='Arial',
            font_color='black',
            bordercolor='#333333'
        ),
        shapes=shapes,
        height=max(400, 120 + 70 * max(
            len(traces_per_vertical[v]['categories']) for v in verticals
        )),
        width=950,
        margin=dict(l=200, r=50, t=100, b=60),
        annotations=[
            dict(
                text="",
                x=1.0,
                xref="paper",
                xanchor="right",
                y=1.11,
                yref="paper",
                yanchor="top",
                xshift=-110,
                showarrow=False,
                font=dict(size=13)
            )
        ]
    )

    return fig

# =========================================================================
# СОЗДАНИЕ ФЛОУЧАРТА НА ГУГЛ-ДИСКЕ
# =========================================================================

def _fill_vertical_sheet(
    worksheet: gspread.Worksheet,
    v_df: pd.DataFrame,
    vertical: str,
    show_revenue: bool = True
):
    """
    Заполняет лист вертикали флоучартом РК.

    Структура:
        Строка 1: Заголовок вертикали
        Строка 2: пустая
        Строка 3: шапка (категория + месяцы)
        Строки 4+: категории с объединёнными ячейками РК
    """
    
    month_labels = [
        'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
        'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'
    ]

    categories = sorted(v_df['category'].unique())

    # Формируем данные для batch update
    all_cells = []

    # Строка 1: заголовок
    all_cells.append({
        'range': 'A1',
        'values': [[f'Вертикаль: {vertical}']]
    })

    # Строка 3: шапка с месяцами
    header_row = ['Категория'] + month_labels
    all_cells.append({
        'range': 'A3',
        'values': [header_row]
    })

    # Строки 4+: категории и данные по РК
    for cat_idx, category in enumerate(categories):
        row_num = cat_idx + 4

        # Название категории
        all_cells.append({
            'range': f'A{row_num}',
            'values': [[category]]
        })

        # Заполняем только первую ячейку каждой РК (остальные будут объединены)
        cat_campaigns = v_df[v_df['category'] == category]

        for _, campaign in cat_campaigns.iterrows():
            start = int(campaign['start_month'])

            # Текст с полной информацией по РК
            if show_revenue:
                cell_text = (
                    f"TRP: {int(campaign['total_trp'])}\n"
                    f"SOV: {campaign['sov']:.0%}\n"
                    f"Бюджет: {campaign['budget'] / 1_000_000:.0f} M\n"
                    f"DTB: {campaign['dtb']:,.0f}\n"
                    f"Выручка: {campaign['revenue'] / 1_000_000:.0f} M\n"
                    f"ROMI: {campaign['romi']:.0%}"
                )
            else:
                cell_text = (
                    f"TRP: {int(campaign['total_trp'])}\n"
                    f"SOV: {campaign['sov']:.0%}\n"
                    f"Бюджет: {campaign['budget'] * BUDGET_COEFF_CORRECTRION / 1_000_000:.0f} M\n"
                    f"DTB: {campaign['dtb']:,.0f}\n"
                    f"ROMI: {campaign['romi']:.0%}"
                )

            # Записываем текст только в первую ячейку диапазона
            col_letter = _col_num_to_letter(start + 1)
            all_cells.append({
                'range': f'{col_letter}{row_num}',
                'values': [[cell_text]]
            })

    # Записываем данные
    worksheet.batch_update(all_cells, value_input_option='RAW')

    # Объединяем ячейки и форматируем
    _format_vertical_sheet(worksheet, v_df, categories)

def _format_vertical_sheet(
    worksheet: gspread.Worksheet,
    v_df: pd.DataFrame,
    categories: List[str]
):
    """
    Применяет форматирование и объединение ячеек к листу вертикали.
    """
    sheet_id = worksheet.id
    category_colors = {
        cat: _get_category_color_rgb(idx)
        for idx, cat in enumerate(categories)
    }

    requests = []

    # Заголовок (A1) — жирный, крупный шрифт
    requests.append({
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 0,
                'endRowIndex': 1,
                'startColumnIndex': 0,
                'endColumnIndex': 13
            },
            'cell': {
                'userEnteredFormat': {
                    'textFormat': {'bold': True, 'fontSize': 14}
                }
            },
            'fields': 'userEnteredFormat.textFormat'
        }
    })

    # Шапка (строка 3) — жирный, серый фон, по центру
    requests.append({
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 2,
                'endRowIndex': 3,
                'startColumnIndex': 0,
                'endColumnIndex': 13
            },
            'cell': {
                'userEnteredFormat': {
                    'textFormat': {'bold': True, 'fontSize': 10},
                    'horizontalAlignment': 'CENTER',
                    'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
                }
            },
            'fields': 'userEnteredFormat(textFormat,horizontalAlignment,backgroundColor)'
        }
    })

    # Названия категорий — жирные
    for cat_idx in range(len(categories)):
        row_idx = cat_idx + 3
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': row_idx,
                    'endRowIndex': row_idx + 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': 1
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'bold': True, 'fontSize': 10},
                        'verticalAlignment': 'MIDDLE'
                    }
                },
                'fields': 'userEnteredFormat(textFormat,verticalAlignment)'
            }
        })

    # Объединение ячеек и закрашивание для каждой РК
    for cat_idx, category in enumerate(categories):
        cat_campaigns = v_df[v_df['category'] == category]
        color = category_colors[category]
        row_idx = cat_idx + 3

        for _, campaign in cat_campaigns.iterrows():
            start = int(campaign['start_month'])
            end = int(campaign['end_month'])

            # Объединяем ячейки, если РК > 1 месяца
            if end > start:
                requests.append({
                    'mergeCells': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': row_idx,
                            'endRowIndex': row_idx + 1,
                            'startColumnIndex': start,
                            'endColumnIndex': end + 1
                        },
                        'mergeType': 'MERGE_ALL'
                    }
                })

            # Закрашиваем ячейки РК
            requests.append({
                'repeatCell': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': row_idx,
                        'endRowIndex': row_idx + 1,
                        'startColumnIndex': start,
                        'endColumnIndex': end + 1
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': color,
                            'textFormat': {'fontSize': 9},
                            'horizontalAlignment': 'CENTER',
                            'verticalAlignment': 'MIDDLE',
                            'wrapStrategy': 'WRAP'
                        }
                    },
                    'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)'
                }
            })

    # Ширина столбца A (категории)
    requests.append({
        'updateDimensionProperties': {
            'range': {
                'sheetId': sheet_id,
                'dimension': 'COLUMNS',
                'startIndex': 0,
                'endIndex': 1
            },
            'properties': {'pixelSize': 180},
            'fields': 'pixelSize'
        }
    })

    # Ширина столбцов B-M (месяцы)
    requests.append({
        'updateDimensionProperties': {
            'range': {
                'sheetId': sheet_id,
                'dimension': 'COLUMNS',
                'startIndex': 1,
                'endIndex': 13
            },
            'properties': {'pixelSize': 110},
            'fields': 'pixelSize'
        }
    })

    # Высота строк с данными
    requests.append({
        'updateDimensionProperties': {
            'range': {
                'sheetId': sheet_id,
                'dimension': 'ROWS',
                'startIndex': 3,
                'endIndex': 3 + len(categories)
            },
            'properties': {'pixelSize': 100},
            'fields': 'pixelSize'
        }
    })

    # Границы таблицы
    requests.append({
        'updateBorders': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 2,
                'endRowIndex': 3 + len(categories),
                'startColumnIndex': 0,
                'endColumnIndex': 13
            },
            'top': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
            'bottom': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
            'left': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
            'right': {'style': 'SOLID', 'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}},
            'innerHorizontal': {'style': 'SOLID', 'color': {'red': 0.85, 'green': 0.85, 'blue': 0.85}},
            'innerVertical': {'style': 'SOLID', 'color': {'red': 0.85, 'green': 0.85, 'blue': 0.85}},
        }
    })

    # Выполняем форматирование
    worksheet.spreadsheet.batch_update({'requests': requests})

def _fill_detail_sheet(
    worksheet: gspread.Worksheet,
    plan_df: pd.DataFrame,
    show_revenue: bool = True
):
    """
    Заполняет лист с полной таблицей всех РК в плане.
    """
    all_cells = []

    # Заголовок
    all_cells.append({'range': 'A1', 'values': [['Полная таблица c РК в плане']]})

    # Шапка
    if show_revenue:
        header = ['Вертикаль', 'Категория', 'Месяц старта', 'Месяц конца', 'Суммарный TRP', 'SOV', 
                  'Бюджет (в млн. руб.)', 'DTB', 'Выручки (в млн. руб.)', 'ROMI']
    else:
        header = ['Вертикаль', 'Категория', 'Месяц старта', 'Месяц конца', 'Суммарный TRP', 'SOV', 
                  'Бюджет (в млн. руб.)', 'DTB', 'ROMI']
    all_cells.append({'range': 'A3', 'values': [header]})

    # Данные
    month_labels = [
        'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
        'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'
    ]

    rows = []
    for _, row in plan_df.iterrows():
        start_label = month_labels[int(row['start_month']) - 1]
        end_label = month_labels[int(row['end_month']) - 1]

        if show_revenue:
            data_row = [
                row['vertical'],
                row['category'],
                start_label,
                end_label,
                f"{row['total_trp']:.0f}".replace(",", " "),
                f"{row['sov']:.0%}",
                f"{row['budget'] / 1_000_000:,.0f} М".replace(",", " "),
                f"{row['dtb']:,.0f}".replace(",", " "),
                f"{row['revenue'] / 1_000_000:,.0f} М".replace(",", " "),
                f"{row['romi']:.0%}"
            ]
        else:
            data_row = [
                row['vertical'],
                row['category'],
                start_label,
                end_label,
                f"{row['total_trp']:.0f}".replace(",", " "),
                f"{row['sov']:.0%}",
                f"{row['budget'] * BUDGET_COEFF_CORRECTRION / 1_000_000:,.0f} М".replace(",", " "),
                f"{row['dtb']:,.0f}".replace(",", " "),
                f"{row['romi']:.0%}"
            ]
        rows.append(data_row)

    all_cells.append({'range': 'A4', 'values': rows})

    # Записываем данные
    worksheet.batch_update(all_cells, value_input_option='RAW')

    # Форматирование
    _format_detail_sheet(worksheet, len(rows), len(header))


def _format_detail_sheet(
    worksheet: gspread.Worksheet,
    num_rows: int,
    num_cols: int
):
    """Форматирование листа с полной таблицей РК."""
    sheet_id = worksheet.id
    requests = []

    # Заголовок — жирный, крупный
    requests.append({
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 0, 'endRowIndex': 1,
                'startColumnIndex': 0, 'endColumnIndex': num_cols
            },
            'cell': {
                'userEnteredFormat': {
                    'textFormat': {'bold': True, 'fontSize': 14}
                }
            },
            'fields': 'userEnteredFormat.textFormat'
        }
    })

    # Шапка — жирный, серый фон
    requests.append({
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 2, 'endRowIndex': 3,
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

    # Границы таблицы
    requests.append({
        'updateBorders': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 2,
                'endRowIndex': 3 + num_rows,
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
                'startIndex': 0,
                'endIndex': num_cols
            }
        }
    })

    worksheet.spreadsheet.batch_update({'requests': requests})

def _fill_summary_sheet(worksheet: gspread.Worksheet, plan_df: pd.DataFrame, show_revenue: bool = True):
    """
    Заполняет сводный лист с агрегированной информацией.
    SOV считается как средневзвешенное (пропорционально TRP).
    Итого по плану — последней строкой в сводке по вертикалям, выделенной красным.
    """
    all_cells = []

    # Заголовок
    all_cells.append({'range': 'A1', 'values': [['Сводка по медиаплану']]})

    # === Сводка по категориям ===
    all_cells.append({'range': 'A3', 'values': [['СВОДКА ПО КАТЕГОРИЯМ']]})

    if show_revenue:
        cat_header = [
            'Вертикаль', 'Категория', 'Кол-во РК',
            'Суммарный TRP', 'Средневзв. SOV', 'Суммарный бюджет (в млн. руб.)',
            'Суммарный DTB', 'Суммарная выручка (в млн. руб.)', 'ROMI'
        ]
    else:
        cat_header = [
            'Вертикаль', 'Категория', 'Кол-во РК',
            'Суммарный TRP', 'Средневзв. SOV', 'Суммарный бюджет (в млн. руб.)',
            'Суммарный DTB', 'ROMI'
        ]
        
    all_cells.append({'range': 'A4', 'values': [cat_header]})

    # Агрегация по категориям с средневзвешенным SOV
    cat_summary = plan_df.groupby(['vertical', 'category']).apply(
        lambda g: pd.Series({
            'num_campaigns': len(g),
            'total_trp': g['total_trp'].sum(),
            'weighted_sov': (g['sov'] * g['total_trp']).sum() / g['total_trp'].sum()
                if g['total_trp'].sum() > 0 else 0,
            'total_budget': g['budget'].sum(),
            'total_dtb': g['dtb'].sum(),
            'total_revenue': g['revenue'].sum()
        })
    ).reset_index()
    cat_summary['romi'] = cat_summary['total_revenue'] / cat_summary['total_budget'] - 1

    cat_rows = []
    for _, row in cat_summary.iterrows():
        if show_revenue:
            cat_rows.append([
                row['vertical'],
                row['category'],
                int(row['num_campaigns']),
                f"{row['total_trp']:.0f}".replace(",", " "),
                f"{row['weighted_sov']:.0%}",
                f"{row['total_budget'] / 1_000_000:,.0f} М".replace(",", " "),
                f"{row['total_dtb']:,.0f}".replace(",", " "),
                f"{row['total_revenue'] / 1_000_000:,.0f} М".replace(",", " "),
                f"{row['romi']:.0%}"
            ])
        else:
            cat_rows.append([
                row['vertical'],
                row['category'],
                int(row['num_campaigns']),
                f"{row['total_trp']:.0f}".replace(",", " "),
                f"{row['weighted_sov']:.0%}",
                f"{row['total_budget'] * BUDGET_COEFF_CORRECTRION / 1_000_000:,.0f} М".replace(",", " "),
                f"{row['total_dtb']:,.0f}".replace(",", " "),
                f"{row['romi']:.0%}"
            ])
            
    all_cells.append({'range': 'A5', 'values': cat_rows})

    # === Сводка по вертикалям ===
    vert_start_row = 5 + len(cat_rows) + 2
    all_cells.append({'range': f'A{vert_start_row}', 'values': [['СВОДКА ПО ВЕРТИКАЛЯМ']]})

    if show_revenue:
        vert_header = [
            'Вертикаль', 'Кол-во РК', 'Суммарный TRP',
            'Средневзв. SOV', 'Суммарный бюджет (в млн. руб.)',
            'Суммарный DTB', 'Суммарная выручка (в млн. руб.)', 'ROMI'
        ]
    else:
        vert_header = [
            'Вертикаль', 'Кол-во РК', 'Суммарный TRP', 'Средневзв. SOV', 
            'Суммарный бюджет (в млн. руб.)', 'Суммарный DTB', 'ROMI'
        ]
        
    all_cells.append({'range': f'A{vert_start_row + 1}', 'values': [vert_header]})

    # Агрегация по вертикалям с средневзвешенным SOV
    vert_summary = plan_df.groupby('vertical').apply(
        lambda g: pd.Series({
            'num_campaigns': len(g),
            'total_trp': g['total_trp'].sum(),
            'weighted_sov': (g['sov'] * g['total_trp']).sum() / g['total_trp'].sum()
                if g['total_trp'].sum() > 0 else 0,
            'total_budget': g['budget'].sum(),
            'total_dtb': g['dtb'].sum(),
            'total_revenue': g['revenue'].sum()
        })
    ).reset_index()
    vert_summary['romi'] = vert_summary['total_revenue'] / vert_summary['total_budget'] - 1

    vert_rows = []
    for _, row in vert_summary.iterrows():
        if show_revenue:
            vert_rows.append([
                row['vertical'],
                int(row['num_campaigns']),
                f"{row['total_trp']:.0f}".replace(",", " "),
                f"{row['weighted_sov']:.0%}",
                f"{row['total_budget'] / 1_000_000:,.0f} М".replace(",", " "),
                f"{row['total_dtb']:,.0f}".replace(",", " "),
                f"{row['total_revenue'] / 1_000_000:,.0f} М".replace(",", " "),
                f"{row['romi']:.0%}"
            ])
        else:
            vert_rows.append([
                row['vertical'],
                int(row['num_campaigns']),
                f"{row['total_trp']:.0f}".replace(",", " "),
                f"{row['weighted_sov']:.0%}",
                f"{row['total_budget'] * BUDGET_COEFF_CORRECTRION / 1_000_000:,.0f} М".replace(",", " "),
                f"{row['total_dtb']:,.0f}".replace(",", " "),
                f"{row['romi']:.0%}"
            ])

    # Итого по плану — последняя строка в таблице вертикалей
    total_budget = plan_df['budget'].sum()
    total_revenue = plan_df['revenue'].sum()
    total_trp = plan_df['total_trp'].sum()
    total_romi = total_revenue / total_budget - 1 if total_budget > 0 else 0
    total_weighted_sov = (
        (plan_df['sov'] * plan_df['total_trp']).sum() / total_trp
        if total_trp > 0 else 0
    )

    if show_revenue:
        vert_rows.append([
            'ИТОГО',
            int(len(plan_df)),
            f"{total_trp:.0f}".replace(",", " "),
            f"{total_weighted_sov:.0%}",
            f"{total_budget / 1_000_000:,.0f} М".replace(",", " "),
            f"{plan_df['dtb'].sum():,.0f}".replace(",", " "),
            f"{total_revenue / 1_000_000:,.0f} М".replace(",", " "),
            f"{total_romi:.0%}"
        ])
    else:
        vert_rows.append([
            'ИТОГО',
            int(len(plan_df)),
            f"{total_trp:.0f}".replace(",", " "),
            f"{total_weighted_sov:.0%}",
            f"{total_budget * BUDGET_COEFF_CORRECTRION / 1_000_000:,.0f} М".replace(",", " "),
            f"{plan_df['dtb'].sum():,.0f}".replace(",", " "),
            f"{total_romi:.0%}"
        ])

    all_cells.append({'range': f'A{vert_start_row + 2}', 'values': vert_rows})

    # Записываем данные
    worksheet.batch_update(all_cells, value_input_option='RAW')

    # Форматирование
    # total_row_idx: 1-based номер строки с ИТОГО
    total_row_idx = vert_start_row + 1 + len(vert_rows)
    _format_summary_sheet(worksheet, vert_start_row, total_row_idx)

def _format_summary_sheet(
    worksheet: gspread.Worksheet,
    vert_start_row: int,
    total_row_idx: int
):
    """Форматирование сводного листа."""
    sheet_id = worksheet.id
    requests = []

    # Заголовок — жирный, крупный
    requests.append({
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 0,
                'endRowIndex': 1,
                'startColumnIndex': 0,
                'endColumnIndex': 9
            },
            'cell': {
                'userEnteredFormat': {
                    'textFormat': {'bold': True, 'fontSize': 14}
                }
            },
            'fields': 'userEnteredFormat.textFormat'
        }
    })

    # Подзаголовки секций — жирные
    for row_idx in [2, vert_start_row - 1]:
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': row_idx,
                    'endRowIndex': row_idx + 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': 9
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'bold': True, 'fontSize': 11}
                    }
                },
                'fields': 'userEnteredFormat.textFormat'
            }
        })

    # Шапки таблиц — жирные, серый фон
    for row_idx in [3, vert_start_row]:
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': row_idx,
                    'endRowIndex': row_idx + 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': 9
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'bold': True, 'fontSize': 10},
                        'backgroundColor': {'red': 0.92, 'green': 0.92, 'blue': 0.92}
                    }
                },
                'fields': 'userEnteredFormat(textFormat,backgroundColor)'
            }
        })

    # Строка ИТОГО — жирный, слабо-красный фон
    requests.append({
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': total_row_idx - 1,
                'endRowIndex': total_row_idx,
                'startColumnIndex': 0,
                'endColumnIndex': 9
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

    # Автоширина столбцов
    requests.append({
        'autoResizeDimensions': {
            'dimensions': {
                'sheetId': sheet_id,
                'dimension': 'COLUMNS',
                'startIndex': 0,
                'endIndex': 9
            }
        }
    })

    worksheet.spreadsheet.batch_update({'requests': requests})

def _col_num_to_letter(col_num: int) -> str:
    """Преобразует номер столбца (1-based) в букву: 1->A, 2->B, ..., 27->AA."""
    result = ''
    while col_num > 0:
        col_num, remainder = divmod(col_num - 1, 26)
        result = chr(65 + remainder) + result
    return result

def _get_category_color_rgb(category_idx: int) -> Dict[str, float]:
    """Возвращает цвет для категории в формате Google Sheets API (0..1 RGB)."""
    colors = [
        {'red': 0.66, 'green': 0.85, 'blue': 0.96},
        {'red': 0.70, 'green': 0.91, 'blue': 0.72},
        {'red': 1.00, 'green': 0.85, 'blue': 0.60},
        {'red': 0.85, 'green': 0.70, 'blue': 0.92},
        {'red': 1.00, 'green': 0.72, 'blue': 0.70},
        {'red': 0.60, 'green': 0.93, 'blue': 0.95},
        {'red': 0.85, 'green': 0.75, 'blue': 0.70},
        {'red': 0.78, 'green': 0.83, 'blue': 0.87},
        {'red': 1.00, 'green': 0.70, 'blue': 0.82},
        {'red': 0.72, 'green': 0.75, 'blue': 0.92},
    ]
    return colors[category_idx % len(colors)]

def create_media_plan_google_sheet(
    plan_df: pd.DataFrame,
    show_revenue: bool = False,
    folder_id: str = "1M_--Ju2b6tN4gwb3MEkiqbIpaWtcyN6c",
) -> str:
    """
    Создаёт Google-таблицу с флоучартом медиаплана.

    Args:
        plan_df: DataFrame из оптимизатора со столбцами:
            vertical, category, start_month, end_month,
            total_trp, sov, budget, dtb, revenue, romi
        show_revenue: Была ли проведена корректировка плана (для отдачи RoRe)
        folder_id: ID папки на Google Drive.

    Returns:
        URL созданной таблицы.
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

    # Генерируем название таблицы
    timestamp = datetime.now(ZoneInfo('Europe/Moscow')).strftime("%Y-%m-%d_%H-%M-%S")
    sheet_title = f"Медиаплан_флоучарт_скорректированный_{timestamp}" if not show_revenue else f"Медиаплан_флоучарт_{timestamp}"

    # Создаём таблицу в указанной папке
    spreadsheet = gc.create(sheet_title, folder_id=folder_id)

    # Открываем доступ для всех по ссылке
    spreadsheet.share('', perm_type='anyone', role='writer')

    # Получаем список вертикалей
    verticals = sorted(plan_df['vertical'].unique())

    # Создаём лист для каждой вертикали
    for i, vertical in enumerate(verticals):
        v_df = plan_df[plan_df['vertical'] == vertical].copy()

        if i == 0:
            worksheet = spreadsheet.sheet1
            worksheet.update_title(vertical)
        else:
            worksheet = spreadsheet.add_worksheet(
                title=vertical, rows=100, cols=20
            )

        _fill_vertical_sheet(worksheet, v_df, vertical, show_revenue=show_revenue)

    # Создаем полную таблицу всех РК и скрываем ее по умолчанию
    detail_ws = spreadsheet.add_worksheet(title="Все РК", rows=100, cols=15)
    _fill_detail_sheet(detail_ws, plan_df, show_revenue)
    spreadsheet.batch_update({'requests': [{
        'updateSheetProperties': {
            'properties': {
                'sheetId': detail_ws.id,
                'hidden': True
            },
            'fields': 'hidden'
        }
    }]})

    # Создаём сводный лист
    summary_ws = spreadsheet.add_worksheet(title="Сводка", rows=100, cols=15)
    _fill_summary_sheet(summary_ws, plan_df, show_revenue=show_revenue)

    return spreadsheet.url

from typing import List, Optional, Tuple, Dict, Any
import pandas as pd
import pickle
import json
import streamlit as st

from PROMISER.data_uploading.table_parser import GoogleSheetsParser
from PROMISER.slim_promiser import SlimPromiser
from configs import LOGICAL_CATEGORIES, CONFIG_SHEET_ID


# ==============================================================================
# Google Sheets: загрузка и парсинг инфы по TRP
# ==============================================================================

def _extract_sheet_code(url: str) -> Optional[str]:
    """
    Внутренняя функция для извлечения spreadsheet ID из URL Google Sheets
    
    :param url: Ссылка на гугл-таблицу
    
    :return: Строка c ID гугл-таблицы (если что-то не то в ссылке, то вернется None)
    """

    try:
        parts = url.split("/")
        d_idx = parts.index("d")
        return parts[d_idx + 1]
    except (ValueError, IndexError):
        return None

def load_google_sheets(
    url: str,
    token_path: str = './PROMISER/configurations/token.json',
    credentials_path: str = './PROMISER/configurations/credentials.json') -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[str]]:
    """
    Функция для загрузки листов с информацией о TRP
    
    :param url: Ссылка на гугл-таблицу
    :param token_path: Путь к токену для гугл-аккаунта
    :param credentials_path: Пукть к креденталсам для гугл-акканута

    :return: Две таблички с информацией по TRP (стоимость и конкуренты) + сообщение об ошибке (если не удалось выгрузить)
    """
    
    # Достаем ID таблицы
    sheet_code = _extract_sheet_code(url)
    if not sheet_code:
        return None, None, "Не удалось извлечь ID таблицы из URL. Проверьте формат ссылки."

    # Создаем парсер и считываем таблицы
    trp_cost_df = None
    competitors_trp_df = None
    
    try:
        parser = GoogleSheetsParser()
    except Exception as e:
        return None, None, f"Ошибка авторизации Google Sheets: {e}"

    try:
        trp_cost_df = parser.read_sheet(sheet_code, "TRP cost")
    except Exception as e:
        return None, None, f"Ошибка при чтении листа «TRP cost»: {e}"

    try:
        competitors_trp_df = parser.read_sheet(sheet_code, "Competitors TRP")
    except Exception as e:
        return None, None, f"Ошибка при чтении листа «Competitors TRP»: {e}"

    return trp_cost_df, competitors_trp_df, None

def get_competitor_categories(competitors_df: Optional[pd.DataFrame]) -> List[str]:
    """
    Функция для извлечения списка конкурентов из первого столбца таблички с информацией по ним
    
    :param competitors_df: Таблица с информацией о TRP конкурентов
    
    :return: Список конкурентов (возможно пустой)
    """
    
    if competitors_df is None or competitors_df.empty:
        return []
    
    first_col = competitors_df.iloc[:, 0]
    return sorted(first_col.dropna().unique().tolist())

def get_target_audiences(trp_cost_df: Optional[pd.DataFrame]) -> List[str]:
    """
    Функция для извлечения уникальных значений из столбца 'ЦА' таблички с информацией по стоимостям TRP
    
    :param trp_cost_df: Таблица с информацией по стоимостям TRP
    
    :param: Список опций для ЦА
    """
    
    if trp_cost_df is None or trp_cost_df.empty:
        return []
    
    if "ЦА" not in trp_cost_df.columns:
        return []
    
    return sorted(trp_cost_df["ЦА"].dropna().unique().tolist())

def get_trp_categories_by_vertical(trp_cost_df: Optional[pd.DataFrame]) -> Dict[str, List[str]]:
    """
    Функция для извлечения категорий из листа TRP cost, сгруппированные по вертикалям.

    :param trp_cost_df: Табличка с данными по стоимостям TRP

    :return: Словарь с названиями категорий по вертикалям
    """
    
    if trp_cost_df is None or trp_cost_df.empty:
        return {}

    if "vertical" not in trp_cost_df.columns:
        # Если столбца vertical нет — возвращаем все категории без привязки
        all_cats = sorted(trp_cost_df["category"].dropna().unique().tolist())
        # Присваиваем всем вертикалям одинаковый список
        result = {vertical: all_cats for vertical in LOGICAL_CATEGORIES.keys()}
    else:
        result = {}
        
        for vertical_name, group in trp_cost_df.groupby("vertical"):
            cats = sorted(group["category"].dropna().unique().tolist())
            result[str(vertical_name)] = cats

    return result

# ==============================================================================
# Преобразование данных для передачи в оптимизатор
# ==============================================================================

def transform_trp_comp_info(df: pd.DataFrame) -> Dict[str, Dict]:
    """
    Функция для перегона таблички с TRP конкурентов в вид словаря (более удобно отдавать в задачу оптимизации)
    
    :param df: Табличка с информацией по TRP конкурентов (где первая колонка - название категории, а далее идут циферные колонки значений по месяцам)
    
    :return: Необходимое представление таблицы в формате словаря
    """
    
    if df is None:
        return {}

    df = df.set_index(df.columns[0])
    df.loc[:, "1":] = df.loc[:, "1":].map(lambda x: float(x.replace('\xa0', '').replace(" ", '')))
    df.columns = df.columns.astype(int)

    return df.to_dict(orient='index')

def transform_trp_cost_info(df: pd.DataFrame, categories: Dict) -> Dict[str, Dict]:
    """
    Функция для перегона таблички с стоимостями TRP в вид словаря (более удобно отдавать в задачу оптимизации)
    При этом, стоимости зависят от вертикали/категории/ЦА, поэтому в таком же итеративном порядке проходимся для формирования словаря:
    
    - Если нет категории, то усредняем по вертикали
    - Если есть категория, но нет ЦА, то усредняем по всем вариантам ЦА в категории
    - Если есть категория и подходящая ЦА, то берем именно эту строку
    
    :param df: Табличка с информацией по стоимостям TRP (где сначала идут характеристики, а далее идут стоимости по месяцам)
    :param categories: Словарь с рассматриваемыми категориями
    
    :return: Необходимое представление таблицы в формате словаря
    """
    
    if df is None:
        return {}
    
    categories_costs = {}
    transform_func = lambda x: float(x.replace('\xa0', '').replace(" ", ''))
    
    for category, category_info in categories.items():
        # Итеративный поиск наиболее подходящих костов
        vertical_df = df[df["vertical"] == category_info["vertical"]]
        
        if category not in vertical_df.category.unique():
            proper_info = vertical_df.loc[:, "1":].map(transform_func).mean(axis=0)
        else:
            category_df = vertical_df[vertical_df["category"] == category]
            
            if category_info["target_audience"] not in category_df["ЦА"].unique():
                proper_info = category_df.loc[:, "1":].map(transform_func).mean(axis=0)
            else:
                proper_info = category_df.loc[category_df["ЦА"] == category_info["target_audience"], "1":].map(transform_func).iloc[0]
        
        proper_info.index = proper_info.index.astype(int)
        categories_costs[category] = proper_info.to_dict()

    return categories_costs

def get_promiser_forecasts(
    categories_dict: Dict[str, Dict],
    histroical_promiser_forecasts: str = './PROMISER_prediction_dict_new.pkl') -> Dict[str, Dict]:
    """
    Функция для составления словаря с прогнозами по DTB/Revenue на месяц по необходимым категориям.
    Базовые прогнозы берутся из pickle-файла; если для категории там нет прогнозов, то они выстраиваются через SlimPromiser
    
    :param categories_dict: Словарь с информацией по анализируемым категориям
    :param histroical_promiser_forecasts: Путь к pickle-файлу с прогнозами обычного Promiser
    
    :return: Словарь с табличными прогнозами
    """

    # Сначала обрабатываем исторические прогнозы
    with open(histroical_promiser_forecasts, 'rb') as f:
        data = pickle.load(f)
        
    parsed_data = {}
    for key, values in data.items():
        categ, month = key.split("_")
        if categ not in parsed_data:
            parsed_data[categ] = {}
        
        parsed_data[categ][int(month)] = values
        
    # Затем обрабатываем категории, по которым нет прогнозов
    promiser = SlimPromiser()
    predictions = []
    for category, category_info in categories_dict.items():
        if category not in parsed_data:
            short_categ_dict = {
                "name": category,
                "logcats": category_info["logical_category"],
                "min_TRP": category_info["min_trp"], 
                "min_SOV": category_info["min_sov"],  
                "ROMI": category_info["default_romi"]
            }
            
            predictions.append(short_categ_dict)
            
    predictions = promiser.build(predictions)        
    for key, values in predictions.items():
        categ, month = key.split("_")
        if categ not in parsed_data:
            parsed_data[categ] = {}
        
        parsed_data[categ][int(month)] = values
        
    return parsed_data

# ==============================================================================
# Считывание/запись инфы про состояния параметров
# ==============================================================================

def save_config_to_sheets(user_id: str, state: Dict[str, Any]):
    """Сохраняет конфигурацию пользователя в Google Sheets"""
    
    if not user_id:
        st.error("Укажите идентификатор пользователя.")
        return
    
    json_str = json.dumps(state, ensure_ascii=False, indent=2)

    try:
        parser = GoogleSheetsParser()
        service = parser.sheets_service

        # Безопасное имя листа (email может содержать спецсимволы)
        sheet_name = user_id.replace("@", "_at_").replace(".", "_")[:50]

        # Пытаемся создать лист (если не существует — создаём)
        try:
            service.spreadsheets().batchUpdate(
                spreadsheetId=CONFIG_SHEET_ID,
                body={
                    "requests": [
                        {
                            "addSheet": {
                                "properties": {"title": sheet_name}
                            }
                        }
                    ]
                },
            ).execute()
        except Exception:
            pass  # лист уже существует — ок

        # Очищаем лист
        service.spreadsheets().values().clear(
            spreadsheetId=CONFIG_SHEET_ID,
            range=sheet_name,
        ).execute()

        # Записываем JSON построчно (каждая строка — одна строка JSON)
        lines = json_str.split("\n")
        body = {"values": [[line] for line in lines]}

        service.spreadsheets().values().update(
            spreadsheetId=CONFIG_SHEET_ID,
            range=f"{sheet_name}!A1",
            valueInputOption="RAW",
            body=body,
        ).execute()

        st.success(f"✅ Cохранено для пользователя «{user_id}»")
        st.session_state["_last_saved_at"] = state["saved_at"]

    except Exception as e:
        st.error(f"❌ Ошибка сохранения: {e}")
        
def load_config_from_sheets_raw(user_id: str) -> Optional[Dict[str, Any]]:
    """Загружает конфигурацию напрямую через Sheets API"""
    
    if not user_id:
        st.error("Укажите идентификатор пользователя.")
        return None

    try:
        parser = GoogleSheetsParser()
        service = parser.sheets_service
        sheet_name = user_id.replace("@", "_at_").replace(".", "_")[:50]

        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=CONFIG_SHEET_ID, range=sheet_name)
            .execute()
        )
        rows = result.get("values", [])

        if not rows:
            st.warning("Сохранённая конфигурация пуста.")
            return None

        json_str = "\n".join(row[0] for row in rows if row)
        return json.loads(json_str)

    except json.JSONDecodeError as e:
        st.error(f"❌ Ошибка парсинга: {e}")
        return None
    except Exception as e:
        st.error(f"❌ Конфигурация для «{user_id}» не найдена: {e}")
        return None

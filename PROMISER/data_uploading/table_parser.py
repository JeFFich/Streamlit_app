"""
Тонкая обёртка над Google Sheets API.

Совпадает по поведению с TableParser.GoogleSheetsParser из старого кода —
вынесена в отдельный модуль с понятным именем, чтобы не таскать с собой
зависимости от .ipynb-related утилит.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import streamlit as st


SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


class GoogleSheetsParser:
    def __init__(self):
        token_info = st.secrets["token"]

        creds = Credentials(
            token=token_info["token"],
            refresh_token=token_info["refresh_token"],
            token_uri=token_info["token_uri"],
            client_id=token_info["client_id"],
            client_secret=token_info["client_secret"],
            scopes=list(token_info["scopes"]),
        )

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                raise RuntimeError(
                    "Credentials невалидны и нет возможности обновить. "
                    "Переавторизуйтесь локально и обновите секреты."
                )

        self.sheets_service = build("sheets", "v4", credentials=creds)

    def read_sheet(
        self, sheet_code: str, sheet_list_name: str, skip_rows: int = 0
    ) -> pd.DataFrame:
        """Читает прямоугольный диапазон листа и возвращает pandas DataFrame.

        Первая строка после `skip_rows` интерпретируется как заголовок;
        остальные — данные. Длина колонок выравнивается по заголовку
        (лишние ячейки в строках обрезаются).
        """
        rows = (
            self.sheets_service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_code, range=sheet_list_name)
            .execute()
        )
        data = rows.get("values", [])
        if not data:
            return pd.DataFrame()

        columns = data[skip_rows]
        col_len = len(columns)
        body = [row[:col_len] for row in data[1 + skip_rows:]]
        return pd.DataFrame(body, columns=columns)

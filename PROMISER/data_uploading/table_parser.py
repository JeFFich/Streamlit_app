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


SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


class GoogleSheetsParser:
    def __init__(self, token_path: str | Path, credentials_path: str | Path):
        token_path = Path(token_path)
        credentials_path = Path(credentials_path)

        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json())

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

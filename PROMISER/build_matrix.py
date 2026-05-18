"""
CLI-точка входа: строит матрицу для MILP-оптимизатора и сохраняет её в pickle.

Использование (из python):
    from promiser_clean import build_and_save
    build_and_save(
        input_path="df_for_pROMIser.xlsx",
        output_path="CE_prediction_dict.pkl",
        n_bootstrap=200,
    )

Использование (из терминала):
    python -m promiser_clean.build_matrix \
        --input  df_for_pROMIser.xlsx \
        --output CE_prediction_dict.pkl \
        --bootstrap 200
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import pandas as pd

from PROMISER.configurations import config
from PROMISER.configurations.dictionaries import (
    DTB_dict,
    SOV_dict,
    value_dict,
    trp_cost_dict,
    CE_dict,
)
from PROMISER.promiser_for_matrexa import MatrixBuilder


def build_and_save(
    input_path: str | Path,
    output_path: str | Path = config.DEFAULT_OUTPUT_PATH,
    n_bootstrap: int = config.DEFAULT_N_BOOTSTRAP,
) -> Path:
    """Полный прогон пайплайна с записью pickle.

    input_path:  Excel/CSV с описанием новых флайтов
                 (см. макет config.INPUT_LAYOUT_SHEET_ID).
    output_path: куда сохранить итоговый словарь.
    n_bootstrap: количество итераций для CI (low/high).
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if input_path.suffix.lower() in (".xlsx", ".xls"):
        data = pd.read_excel(input_path)
    else:
        data = pd.read_csv(input_path)
        
    # Упорядочиваем последовательность логкатов, чтобы корректно тянуть значения из словарей всяких
    data["logical_category"] = data["logical_category"].apply(lambda s: ", ".join(sorted(s.split(', '))))

    builder = MatrixBuilder(data_to_predict=data)
    matrix = builder.build(
        DTB_dict=DTB_dict,
        SOV_dict=SOV_dict,
        value_dict=value_dict,
        trp_cost_dict=trp_cost_dict,
        CE_dict=CE_dict,
        n_bootstrap=n_bootstrap,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(matrix, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[promiser_clean] записал {len(matrix)} ключей в {output_path}")
    return output_path


def _cli() -> None:
    p = argparse.ArgumentParser(description="Построить матрицу для MILP-оптимизатора.")
    p.add_argument("--input", required=True, help="Excel/CSV с новыми флайтами")
    p.add_argument("--output", default=str(config.DEFAULT_OUTPUT_PATH))
    p.add_argument("--bootstrap", type=int, default=config.DEFAULT_N_BOOTSTRAP)
    args = p.parse_args()
    build_and_save(args.input, args.output, args.bootstrap)


if __name__ == "__main__":
    _cli()

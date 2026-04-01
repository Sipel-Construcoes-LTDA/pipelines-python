import glob
import logging
import os
import warnings
from typing import Any, List

import pandas as pd

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress specific warnings
warnings.simplefilter(action="ignore", category=FutureWarning)
warnings.simplefilter(action="ignore", category=UserWarning)

# --- Diretórios ---
# O script está em 'src', então navegamos um nível acima para a raiz do módulo
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SRC_DIR)
VALORES_DIR = os.path.join(BASE_DIR, "valores_executados")
DIMENSOES_DIR = os.path.join(VALORES_DIR, "dimensões")
ZRM_DIR = os.path.join(VALORES_DIR, "ZRM")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")


def clean_text(text: Any) -> str:
    if pd.isna(text):
        return ""
    return str(text).strip()


def find_header_row(file_path: str, encoding: str = "utf-16") -> int:
    """Encontra a linha de cabeçalho baseada nas colunas esperadas."""
    try:
        with open(file_path, "r", encoding=encoding) as f:
            for i, line in enumerate(f):
                if "Nota" in line and "GrCoAt" in line:
                    return i
    except Exception as e:
        logger.warning(f"Erro ao ler linhas para encontrar header em {file_path}: {e}")
    return 0


def load_dim_ct() -> pd.DataFrame:
    path = os.path.join(DIMENSOES_DIR, "dim_Ct.xlsx")
    logger.info(f"Carregando dim_Ct de {path}")
    df = pd.read_excel(path)
    df = df[["NOMECLATURA_BD_IW69", "BASE OPERACIONAL"]].copy()
    df["NOMECLATURA_BD_IW69"] = df["NOMECLATURA_BD_IW69"].apply(clean_text)
    return df


def load_fato_zrm_map() -> pd.DataFrame:
    """
    Carrega fato_zrm e cria um mapa de Serv.R/3 (Clean) -> Chave composta (FK).
    """
    path = os.path.join(ZRM_DIR, "fato_zrm.xlsx")
    logger.info(f"Carregando fato_zrm de {path}")
    df = pd.read_excel(path, sheet_name=" BASE ZRM")

    df["Grp.Ação"] = df["Grp.Ação"].fillna("").astype(str)
    df["Serv.CCS"] = df["Serv.CCS"].fillna("").astype(str)
    df["Chave composta (FK)"] = df["Grp.Ação"] + df["Serv.CCS"]
    df = df.drop_duplicates(subset=["Chave composta (FK)"])

    df["Serv.R/3"] = df["Serv.R/3"].astype(str).str.strip()
    df["Limpar"] = df["Serv.R/3"].apply(clean_text)

    return df[["Limpar", "Chave composta (FK)"]]


def load_dim_values(zrm_map: pd.DataFrame, year_label: str) -> pd.DataFrame:
    """
    Carrega valores de serviços (2024, 2025 ou 2026) e prepara tabela de lookup.
    """
    path = os.path.join(DIMENSOES_DIR, "dim_valor_servicos.xlsx")
    
    # Mapeamento das abas por ano
    sheet_map = {
        "2024": "Valores antigos",
        "2025": "Valores novos",
        "2026": "Valores novos 2026"
    }
    
    sheet_name = sheet_map.get(year_label)
    if not sheet_name:
        logger.error(f"Ano {year_label} não configurado para carregar valores.")
        return pd.DataFrame(columns=["FK_FINAL", f"Valor Total {year_label}"])

    logger.info(f"Carregando dim_valor_servicos ({sheet_name}) de {path}")
    df = pd.read_excel(path, sheet_name=sheet_name)

    df["COD PAGAMENTO"] = df["COD PAGAMENTO"].astype(str).str.strip()
    df["Limpar"] = df["COD PAGAMENTO"].apply(clean_text)

    merged = pd.merge(df, zrm_map, on="Limpar", how="left")

    merged["BASE"] = merged["BASE"].fillna("").astype(str)
    merged["Chave composta (FK)"] = merged["Chave composta (FK)"].fillna("").astype(str)
    merged["FK_FINAL"] = merged["BASE"] + merged["Chave composta (FK)"]

    bases_to_exclude = ["BONFIM", "JACOBINA", "JUAZEIRO", "REMANSO"]
    merged = merged[~merged["FK_FINAL"].isin(bases_to_exclude)]

    if "Valor Total" not in merged.columns:
        if "VALOR" in merged.columns and "Fator K" in merged.columns:
            merged["Valor Total"] = merged["VALOR"] * merged["Fator K"]

    col_valor = f"Valor Total {year_label}"
    merged = merged.rename(columns={"Valor Total": col_valor})
    merged = merged.drop_duplicates(subset=["FK_FINAL"])

    return merged[["FK_FINAL", col_valor]]


def process_pipeline() -> None:
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # 1. Carregar Dimensões e Mapas
    dim_ct = load_dim_ct()
    zrm_map = load_fato_zrm_map()

    # Definimos os anos que queremos processar
    years = ["2024", "2025", "2026"]
    dim_vals = {year: load_dim_values(zrm_map, year) for year in years}

    # 2. Encontrar e Processar Arquivos Mensais
    all_files: List[str] = glob.glob(
        os.path.join(VALORES_DIR, "**", "*.XLS"), recursive=True
    )
    logger.info(f"Encontrados {len(all_files)} arquivos para processar.")

    dfs: List[pd.DataFrame] = []

    for file_path in all_files:
        try:
            filename = os.path.basename(file_path)
            if filename.lower().endswith(".xlsx"):
                continue

            header_row = find_header_row(file_path)
            df_temp = pd.read_csv(
                file_path, sep="\t", encoding="utf-16", skiprows=header_row
            )

            if "Unnamed: 0" in df_temp.columns:
                df_temp = df_temp.drop(columns=["Unnamed: 0"])

            df_temp.columns = [c.strip() for c in df_temp.columns]

            required_cols = ["GrCoAt", "CódA", "CenTrabRes", "Nota", "Data"]
            missing = [c for c in required_cols if c not in df_temp.columns]
            if missing:
                logger.warning(
                    f"Arquivo {filename} ignorado. Colunas faltantes: {missing}"
                )
                continue

            dfs.append(df_temp)

        except Exception as e:
            logger.error(f"Erro ao processar arquivo {file_path}: {e}")

    if not dfs:
        logger.error("Nenhum dado carregado.")
        return

    # 3. Combinar Fatos
    full_df = pd.concat(dfs, ignore_index=True)
    logger.info(f"Total de registros brutos: {len(full_df)}")

    # 4. Transformações
    full_df["GrCoAt"] = full_df["GrCoAt"].fillna("").astype(str).str.strip()
    full_df["CódA"] = full_df["CódA"].fillna("").astype(str).str.strip()
    full_df["ChaveFK"] = full_df["GrCoAt"] + full_df["CódA"]

    full_df["CenTrabRes"] = full_df["CenTrabRes"].fillna("").astype(str).str.strip()
    full_df = pd.merge(
        full_df,
        dim_ct,
        left_on="CenTrabRes",
        right_on="NOMECLATURA_BD_IW69",
        how="left",
    )

    full_df["BASE OPERACIONAL"] = (
        full_df["BASE OPERACIONAL"].fillna("").astype(str).str.strip()
    )
    full_df["PK"] = full_df["BASE OPERACIONAL"] + full_df["ChaveFK"]

    # Merge de valores para cada ano definido
    for year in years:
        full_df = pd.merge(
            full_df, dim_vals[year], left_on="PK", right_on="FK_FINAL", how="left"
        ).drop(columns=["FK_FINAL"], errors="ignore")

    group_cols: List[str] = ["Nota", "Data", "BASE OPERACIONAL"]
    additional_cols: List[str] = ["Fim avaria", "Texto code para codificação", "Local"]

    for col in additional_cols:
        if col in full_df.columns:
            full_df[col] = full_df[col].fillna("").astype(str).str.strip()
            group_cols.append(col)

    cols_vals = [f"Valor Total {year}" for year in years]
    for c in cols_vals:
        if c not in full_df.columns:
            full_df[c] = 0.0
        full_df[c] = full_df[c].fillna(0.0)

    # Agrupamento final
    final_df = full_df.groupby(group_cols, as_index=False)[cols_vals].sum()

    initial_len = len(final_df)
    # Remove linhas onde todos os anos estão zerados
    final_df = final_df[~(final_df[cols_vals] == 0).all(axis=1)]
    logger.info(f"Linhas removidas (valores zerados): {initial_len - len(final_df)}")

    # Output
    output_path = os.path.join(PROCESSED_DIR, "faturamentos_executados_consolidado.csv")
    final_df.to_csv(
        output_path, index=False, sep=";", encoding="utf-8-sig", decimal=","
    )
    logger.info(f"Pipeline concluído. Arquivo salvo em: {output_path}")
    logger.info(f"Linhas finais: {len(final_df)}")


if __name__ == "__main__":
    process_pipeline()

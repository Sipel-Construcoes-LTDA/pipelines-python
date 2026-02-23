import logging
import os
from typing import List

import pandas as pd

# Configuração de Logging conforme PADROES_PROJETO.md
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configurações & Constantes ---
IDS_PLANILHAS = {
    "Bonfim": "1gNr558RS_DHwv8PjaSdwOvDI0mqlVVY3GEKFFXKsU5U",
    "Jacobina": "19OdT08BBNJqQwU4GNyYySNlpTj6p7UVW66xFYyd5B5I",
    "Juazeiro": "1Q9-OHTSZG7IRoZ2zocmLjv934_fTwOB7FhCFXbzECG0",
}
GIDS = {
    "Bonfim": "1164135827",
    "Jacobina": "1906289711",
    "Juazeiro": "1923088500",
}
OUTPUT_PATH = "pipelines-python/vistorias_comercial/data/processed/vistorias_consolidadas.csv"


def get_url(spreadsheet_id: str, gid: str) -> str:
    """Gera a URL de exportação CSV para o Google Sheets."""
    return (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
    )


def validate_required_columns(
    df: pd.DataFrame, required_cols: List[str], source_name: str
) -> None:
    """Verifica se todas as colunas necessárias existem no DataFrame."""
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Fonte '{source_name}' inválida. Colunas ausentes: {missing_cols}"
        )


def safe_to_datetime(series: pd.Series) -> pd.Series:
    """Converte série para datetime com segurança para o formato brasileiro."""
    return pd.to_datetime(series, errors="coerce", dayfirst=True)


def clean_nota(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Garante que a coluna NOTA seja numérica, registrando e removendo inválidos."""
    if "NOTA" not in df.columns:
        logger.warning(f"[{source_name}] Coluna 'NOTA' não encontrada. Pulando limpeza.")
        return df

    df_copy = df.copy()
    df_copy["NOTA"] = pd.to_numeric(df_copy["NOTA"], errors="coerce")

    invalid_rows = df_copy["NOTA"].isna()
    if invalid_rows.any():
        num_invalid = invalid_rows.sum()
        logger.warning(
            f"[{source_name}] Removendo {num_invalid} linha(s) com valor de NOTA inválido."
        )
        df_copy = df_copy.dropna(subset=["NOTA"])

    if not df_copy.empty:
        df_copy["NOTA"] = df_copy["NOTA"].astype(int)
    return df_copy


def process_bonfim(spreadsheet_id: str, gid: str) -> pd.DataFrame:
    """Extrai e trata os dados de Senhor do Bonfim."""
    source_name = "Bonfim"
    logger.info(f"Processando base: {source_name}")
    url = get_url(spreadsheet_id, gid)
    df = pd.read_csv(url)

    required_cols = ["NOTA", "PRAZO DA NOTA", "DATA DO CONTATO", "COLABORADOR", "STATUS", "CONFORMIDADE"]
    validate_required_columns(df, required_cols, source_name)

    df = clean_nota(df, source_name)

    df["PRAZO DA NOTA"] = safe_to_datetime(df["PRAZO DA NOTA"])
    df["DATA DO CONTATO"] = safe_to_datetime(df["DATA DO CONTATO"])
    df["DATA DO RETORNO"] = safe_to_datetime(df.get("DATA DO RETORNO"))

    df = df.rename(
        columns={
            "COLABORADOR": "RESPONSAVEL",
            "STATUS": "TEMP_STATUS",
            "CONFORMIDADE": "STATUS",
        }
    )
    df = df.rename(columns={"TEMP_STATUS": "CONFORMIDADE"})

    df["MUNICIPIO"] = "SENHOR DO BONFIM"
    return df


def process_jacobina(spreadsheet_id: str, gid: str) -> pd.DataFrame:
    """Extrai e trata os dados de Jacobina."""
    source_name = "Jacobina"
    logger.info(f"Processando base: {source_name}")

    url = get_url(spreadsheet_id, gid)
    df = pd.read_csv(url)
    df = df.dropna(how="all")

    required_cols = ["NOTA", "STATUS", "CONFORMIDADE"]
    validate_required_columns(df, required_cols, source_name)

    df = clean_nota(df, source_name)

    col_contato = "DATA CONTATO" if "DATA CONTATO" in df.columns else "DATA DO CONTATO"
    df["DATA DO CONTATO"] = safe_to_datetime(df.get(col_contato))
    df["DATA DO RETORNO"] = safe_to_datetime(df.get("DATA RETORNO"))

    df = df.rename(
        columns={
            "LOCAL": "MUNICIPIO",
            "STATUS": "TEMP_STATUS",
            "CONFORMIDADE": "STATUS",
        }
    )
    df = df.rename(columns={"TEMP_STATUS": "CONFORMIDADE"})
    return df


def process_juazeiro(spreadsheet_id: str, gid: str) -> pd.DataFrame:
    """Extrai e trata os dados de Juazeiro."""
    source_name = "Juazeiro"
    logger.info(f"Processando base: {source_name}")

    url = get_url(spreadsheet_id, gid)
    df = pd.read_csv(url)

    if "UTEP" not in df.columns and "NOTA" not in df.columns:
        logger.warning(f"[{source_name}] Cabeçalho suspeito. Tentando pular a primeira linha.")
        df = pd.read_csv(url, skiprows=1)

    required_cols = ["UTEP", "NOTA", "COLABORADOR", "DATA CONTATO", "RETORNO"]
    validate_required_columns(df, required_cols, source_name)

    df = df.rename(
        columns={
            "UTEP": "MUNICIPIO",
            "COLABORADOR": "RESPONSAVEL",
            "DATA CONTATO": "DATA DO CONTATO",
            "DATA RETORNO": "DATA DO RETORNO",
            "RETORNO": "CONFORMIDADE",
        }
    )
    df = clean_nota(df, source_name)
    df["DATA DO CONTATO"] = safe_to_datetime(df.get("DATA DO CONTATO"))
    df["DATA DO RETORNO"] = safe_to_datetime(df.get("DATA DO RETORNO"))
    return df


def main() ->  None:
    """Ponto de entrada do pipeline de ETL de Vistorias."""
    logger.info("--- Iniciando Pipeline de Vistorias Comercial ---")

    datasets = {
        "Bonfim": (process_bonfim, IDS_PLANILHAS["Bonfim"], GIDS["Bonfim"]),
        "Jacobina": (process_jacobina, IDS_PLANILHAS["Jacobina"], GIDS["Jacobina"]),
        "Juazeiro": (process_juazeiro, IDS_PLANILHAS["Juazeiro"], GIDS["Juazeiro"]),
    }

    processed_dfs = []
    for name, (func, sheet_id, gid) in datasets.items():
        try:
            df = func(sheet_id, gid)
            processed_dfs.append(df)
            logger.info(f"Sucesso ao processar {name}. ({len(df)} linhas)")
        except Exception as e:
            logger.error(f"Falha CRÍTICA ao processar {name}: {e}", exc_info=True)

    if not processed_dfs:
        logger.error("Nenhuma fonte de dados foi processada com sucesso. Encerrando.")
        return

    logger.info("Consolidando bases...")
    df_final = pd.concat(processed_dfs, ignore_index=True)

    if df_final.empty:
        logger.error("Dataframe final vazio após consolidação. Encerrando.")
        return

    # Garantir colunas finais e ordem
    colunas_finais = [
        "NOTA", "DATA DO CONTATO", "DATA DO RETORNO",
        "MUNICIPIO", "RESPONSAVEL", "STATUS", "CONFORMIDADE"
    ]
    for col in colunas_finais:
        if col not in df_final.columns:
            df_final[col] = pd.NA
    df_final = df_final[colunas_finais]

    # Limpeza final e regras de negócio
    df_final["DATA DO CONTATO"] = pd.to_datetime(df_final["DATA DO CONTATO"], errors="coerce").dt.date
    df_final["DATA DO RETORNO"] = pd.to_datetime(df_final["DATA DO RETORNO"], errors="coerce").dt.date

    rows_before = len(df_final)
    df_final = df_final.dropna(subset=["DATA DO CONTATO"])
    rows_after = len(df_final)
    if rows_before > rows_after:
        logger.warning(f"Removidas {rows_before - rows_after} linhas sem 'DATA DO CONTATO'.")

    # Salvar output
    output_dir = os.path.dirname(OUTPUT_PATH)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    df_final.to_csv(OUTPUT_PATH, index=False, sep=";", encoding="utf-8-sig")

    logger.info("--- Pipeline concluído! ---")
    logger.info(f"Salvo em: {OUTPUT_PATH}")
    logger.info(f"Total de vistorias consolidadas: {len(df_final)}")


if __name__ == "__main__":
    main()

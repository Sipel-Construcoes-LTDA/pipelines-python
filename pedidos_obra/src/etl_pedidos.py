import logging
from pathlib import Path
from typing import List

import pandas as pd

# Configuração de Logging conforme PADROES_PROJETO.md
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configurações & Constantes ---
IDS_PLANILHAS = {
    "Bonfim_obra": "1xRM5ArGu70p0sUtoLNpmOx-pEogwcJsPEO5kVT7jaZY",
    "Jacobina_obra": "1oluRkWRsj6GuS8QJ0L3jFXi3FkLkCHCyVvbNpOjrdl4",
    "Juazeiro_obra": "1lreFnHhjlEubtw_L6TDnQ1Ho3-_3VUDDmCOnN9Nsy2k"
}
GIDS = {
    "Bonfim_obra": "1533241260",
    "Jacobina_obra": "1533241260",
    "Juazeiro_obra": "870879769",
    "Bonfim_manut":"1995794361",
    "Jacobina_manut":"1995794361",
    "Juazeiro_manut":"1926173995",
}
MODULE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = MODULE_ROOT.parent


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


def clean_currency(series: pd.Series) -> pd.Series:
    """Limpa valores monetários (Ex: R$ 1.234,56 -> 1234.56)."""
    if series is None or series.empty:
        return series
    clean_series = (
        series.astype(str)
        .str.replace("R$", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
    )
    return pd.to_numeric(clean_series, errors="coerce")


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Remove espaços extras nos nomes das colunas e aplica mapeamento padrão."""
    df.columns = [col.strip() for col in df.columns]
    # Mapeamento de colunas com nomes variados ou caracteres especiais
    mapping = {
        "Val.líq.": "VALOR_LIQUIDO",
        "DATA ENVIO": "DATA_ENVIO",
        "Data doc": "DATA_DOC",
        "DEFINIÇÃO": "DEFINICAO",
        "RESPONSAVEL": "RESPONSAVEL",
        "PEDIDOS": "PEDIDO",
        "CONTRATO": "CONTRATO",
        "MUNICIPIO": "MUNICIPIO",
        "BASE": "BASE",
        "CICLO": "CICLO",
        "PEP": "PEP",
        "TIPO": "TIPO"
    }
    # Procura por colunas que contenham "Val.líq." mesmo com espaços ou não-quebra-de-espaço
    for col in df.columns:
        if "Val.líq." in col:
            df = df.rename(columns={col: "VALOR_LIQUIDO"})
    return df.rename(columns=mapping)

def process_generic(source_name: str, spreadsheet_id: str, gid: str) -> pd.DataFrame:
    """Função genérica para processar as bases de pedidos."""
    logger.info(f"Processando base: {source_name}")
    url = get_url(spreadsheet_id, gid)
    df = pd.read_csv(url)
    df = df.dropna(how="all")

    df = standardize_columns(df)
    required_cols = ["DATA_ENVIO", "RESPONSAVEL", "PEDIDO", "VALOR_LIQUIDO", "DATA_DOC"]
    validate_required_columns(df, required_cols, source_name)
    # Conversões de tipo
    df = df.assign(
        DATA_ENVIO=safe_to_datetime(df["DATA_ENVIO"]),
        DATA_DOC=safe_to_datetime(df["DATA_DOC"]),
        VALOR_LIQUIDO=clean_currency(df["VALOR_LIQUIDO"]),
        PEDIDO=pd.to_numeric(df["PEDIDO"], errors="coerce").fillna(0).astype(int).astype(str)
    )
    return df
def main() -> None:
    """Ponto de entrada do pipeline de ETL de Pedidos de Obra."""
    logger.info("--- Iniciando Pipeline de Pedidos de Obra ---")

    processed_dfs = []
    for name, sheet_id in IDS_PLANILHAS.items():
        gid = GIDS[name]
        try:
            df = process_generic(name, sheet_id, gid)
            processed_dfs.append(df)
            logger.info(f"Sucesso ao processar {name}. ({len(df)} linhas)")
        except Exception as e:
            logger.error(f"Falha ao processar {name}: {e}")

    if not processed_dfs:
        logger.error("Nenhuma fonte de dados foi processada com sucesso. Encerrando.")
        return

    logger.info("Consolidando bases...")
    df_final = pd.concat(processed_dfs, ignore_index=True)

    # Colunas finais desejadas
    colunas_finais = [
        "DATA_ENVIO", "DATA_DOC", "RESPONSAVEL", "TIPO", "PEP", "DEFINICAO", "PEDIDO", "VALOR_LIQUIDO", "CONTRATO", "MUNICIPIO", "BASE", "CICLO"
    ]
    # Adiciona colunas ausentes como NA
    for col in colunas_finais:
        if col not in df_final.columns:
            df_final[col] = pd.NA
    df_final = df_final[colunas_finais].copy()

    # Garante que as datas sejam datetime antes de extrair .date
    df_final.loc[:, "DATA_ENVIO"] = pd.to_datetime(df_final["DATA_ENVIO"], errors="coerce")
    df_final.loc[:, "DATA_DOC"] = pd.to_datetime(df_final["DATA_DOC"], errors="coerce")

    # Limpezas finais
    df_final = df_final.dropna(subset=["DATA_ENVIO", "PEDIDO"])
    # Formatação de datas para o CSV final (converte para string ou objeto date)
    df_final.loc[:, "DATA_ENVIO"] = df_final["DATA_ENVIO"].dt.date
    df_final.loc[:, "DATA_DOC"] = df_final["DATA_DOC"].dt.date

    # Salvar output
    output_dir_processed = MODULE_ROOT / "data" / "processed"
    output_dir_processed.mkdir(parents=True, exist_ok=True)
    output_path_processed = output_dir_processed / "pedidos_consolidados.csv"
    df_final.to_csv(output_path_processed, index=False, sep=";", encoding="utf-8-sig")

    logger.info("--- Pipeline concluído! ---")
    logger.info(f"Salvo em: {output_path_processed}")
    logger.info(f"Total de pedidos consolidados: {len(df_final)}")


if __name__ == "__main__":
    main()

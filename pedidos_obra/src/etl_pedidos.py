import logging
from pathlib import Path
from typing import Dict

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
    "Juazeiro_obra": "1lreFnHhjlEubtw_L6TDnQ1Ho3-_3VUDDmCOnN9Nsy2k",
    "Bonfim_manut": "1xRM5ArGu70p0sUtoLNpmOx-pEogwcJsPEO5kVT7jaZY",
    "Jacobina_manut": "1oluRkWRsj6GuS8QJ0L3jFXi3FkLkCHCyVvbNpOjrdl4",
    "Juazeiro_manut": "1lreFnHhjlEubtw_L6TDnQ1Ho3-_3VUDDmCOnN9Nsy2k",
}

GIDS = {
    "Bonfim_obra": "1533241260",
    "Jacobina_obra": "1533241260",
    "Juazeiro_obra": "870879769",
    "Bonfim_manut": "1995794361",
    "Jacobina_manut": "1995794361",
    "Juazeiro_manut": "1926173995",
}

MODULE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = MODULE_ROOT.parent

def get_url(spreadsheet_id: str, gid: str) -> str:
    """Gera a URL de exportação CSV para o Google Sheets."""
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"

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
    mapping = {
        "Val.líq.": "VALOR_LIQUIDO",
        "DATA ENVIO": "DATA_ENVIO",
        "Data doc": "DATA_DOC",
        "DEFINIÇÃO": "DEFINICAO",
        "RESPONSAVEL": "RESPONSAVEL",
        "PEDIDOS": "PEDIDO",
        "Contrato": "CONTRATO",
        "MUNICIPIO": "MUNICIPIO",
        "BASE": "BASE",
        "CICLO": "CICLO",
        "PEP": "PEP",
        "TIPO": "TIPO",
        "DESCRIÇÃO": "DESCRICAO",
        "SETOR": "SETOR",
        "TEXTO BREVE": "TEXTO_BREVE"
    }

    for col in df.columns:
        if "Val.líq." in col:
            df = df.rename(columns={col: "VALOR_LIQUIDO"})
    return df.rename(columns=mapping)

def apply_specific_filters(df: pd.DataFrame, source_name: str, discards: Dict[str, int]) -> pd.DataFrame:
    """Aplica os filtros de linha e rastreia os descartes por motivo."""
    # Filtro PEP não vazio para Bonfim e Jacobina
    if source_name in ["Bonfim_obra", "Jacobina_obra", "Bonfim_manut", "Jacobina_manut"]:
        initial_count = len(df)
        if "PEP" in df.columns:
            df = df[df["PEP"].notna() & (df["PEP"].astype(str).str.strip() != "")]
            diff = initial_count - len(df)
            discards["Filtro PEP Vazio"] += diff

    # Filtro de BASE para Jacobina Obra
    if source_name == "Jacobina_obra":
        initial_count = len(df)
        if "BASE" in df.columns:
            df = df[df["BASE"].astype(str).str.upper().str.strip() == "JACOBINA"]
            diff = initial_count - len(df)
            discards["Filtro BASE (Não Jacobina)"] += diff

    return df

def process_source(source_name: str, spreadsheet_id: str, gid: str, discards: Dict[str, int]) -> pd.DataFrame:
    """Função principal para processar cada fonte individualmente."""
    logger.info(f"Processando fonte: {source_name}")
    url = get_url(spreadsheet_id, gid)
    try:
        df = pd.read_csv(url)
    except Exception as e:
        logger.error(f"Erro ao ler URL {url}: {e}")
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    total_bruto = len(df)
    df = df.dropna(how="all")
    discards["Linhas Completamente Vazias"] += (total_bruto - len(df))

    df = standardize_columns(df)
    # Aplicar filtros específicos do Power Query (Filtro de Setor removido conforme pedido)
    df = apply_specific_filters(df, source_name, discards)
    # Conversões de tipo
    if "DATA_ENVIO" in df.columns:
        df["DATA_ENVIO"] = safe_to_datetime(df["DATA_ENVIO"])
    if "DATA_DOC" in df.columns:
        df["DATA_DOC"] = safe_to_datetime(df["DATA_DOC"])
    if "VALOR_LIQUIDO" in df.columns:
        df["VALOR_LIQUIDO"] = clean_currency(df["VALOR_LIQUIDO"])
    if "PEDIDO" in df.columns:
        df["PEDIDO"] = pd.to_numeric(df["PEDIDO"], errors="coerce").fillna(0).astype(int)
    if "CONTRATO" in df.columns:
        df["CONTRATO"] = pd.to_numeric(df["CONTRATO"], errors="coerce").fillna(0).astype(int)

    # Adicionar metadados da fonte
    df["FONTE_ORIGEM"] = source_name
    df["CATEGORIA"] = "OBRA" if "obra" in source_name.lower() else "MANUT"
    return df

def main() -> None:
    """Ponto de entrada do pipeline de ETL de Pedidos."""
    logger.info("--- Iniciando Pipeline de Pedidos (Obra + Manut) ---")

    processed_dfs = []
    discards_global = {
        "Linhas Completamente Vazias": 0,
        "Filtro PEP Vazio": 0,
        "Filtro BASE (Não Jacobina)": 0
    }

    for name, sheet_id in IDS_PLANILHAS.items():
        gid = GIDS[name]
        df = process_source(name, sheet_id, gid, discards_global)
        if not df.empty:
            processed_dfs.append(df)
            logger.info(f"Sucesso: {name} ({len(df)} linhas úteis)")

    if not processed_dfs:
        logger.error("Nenhuma fonte de dados foi processada. Encerrando.")
        return

    logger.info("Consolidando bases (Table.Combine)...")
    df_final = pd.concat(processed_dfs, ignore_index=True)

    # 1. Linhas em Branco Removidas (remove se todos os campos relevantes forem nulos/vazios)
    df_final = df_final.dropna(how="all")

    # 2. Valor Substituído (RESPONSAVEL: "LOGISTICA " -> "LOGISTICA")
    if "RESPONSAVEL" in df_final.columns:
        df_final["RESPONSAVEL"] = df_final["RESPONSAVEL"].astype(str).str.replace("LOGISTICA ", "LOGISTICA", regex=False)

    # 3. Valor Substituído1 (TIPO: "Uso Mutuo" -> "USO MUTUO")
    # 4. Valor Substituído2 (TIPO: "Linha Viva Preventiva" -> "LINHA VIVA")
    if "TIPO" in df_final.columns:
        df_final["TIPO"] = df_final["TIPO"].astype(str).replace({
            "Uso Mutuo": "USO MUTUO",
            "Linha Viva Preventiva": "LINHA VIVA"
        })

    # 5. Texto Inserido Após o Delimitador (Extrai após o hífen no PEP)
    if "PEP" in df_final.columns:
        # split("-", n=1) divide no primeiro hífen, .str[1] pega o que vem depois
        df_final["TEXTO_APOS_DELIMITADOR"] = df_final["PEP"].astype(str).str.split("-", n=1).str[1]
    else:
        df_final["TEXTO_APOS_DELIMITADOR"] = pd.NA

    # Seleção e ordenação final das colunas
    colunas_finais = [
        "DATA_ENVIO", "DATA_DOC", "RESPONSAVEL", "TIPO", "PEP", "TEXTO_APOS_DELIMITADOR",
        "DEFINICAO", "PEDIDO", "VALOR_LIQUIDO", "CONTRATO", "MUNICIPIO", "BASE", "CICLO",
        "DESCRICAO", "SETOR", "TEXTO_BREVE", "FONTE_ORIGEM", "CATEGORIA"
    ]
    for col in colunas_finais:
        if col not in df_final.columns:
            df_final[col] = pd.NA

    df_final = df_final[colunas_finais].copy()

    # Formatação final para CSV
    df_final["DATA_ENVIO"] = pd.to_datetime(df_final["DATA_ENVIO"]).dt.date
    df_final["DATA_DOC"] = pd.to_datetime(df_final["DATA_DOC"]).dt.date

    # Salvar output
    output_dir = MODULE_ROOT / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "pedidos_consolidados.csv"
    df_final.to_csv(output_path, index=False, sep=";", encoding="utf-8-sig")
    logger.info("--- Pipeline concluído! ---")
    logger.info(f"Arquivo salvo em: {output_path}")
    logger.info(f"Total consolidado: {len(df_final)} pedidos")
    total_descartado = sum(discards_global.values())
    logger.info("="*40)
    logger.info(f"RESUMO DE DESCARTE (TOTAL: {total_descartado} linhas)")
    for motivo, quantidade in discards_global.items():
        if quantidade > 0:
            logger.info(f" - {motivo}: {quantidade} linhas")
    logger.info("="*40)

if __name__ == "__main__":
    main()

import base64
import csv
import logging
from io import BytesIO
from pathlib import Path
from typing import Dict

import pandas as pd
import requests

# Configuração de Logging conforme PADROES_PROJETO.md
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configurações & Constantes ---
# Link de download direto público para fServiço CIF
CIF_URL = "https://onedrive.live.com/:x:/g/personal/15cb95ca5bdc1f45/IQB4UPujoI5bR4wLOkBacaKWATIhf0G_VXSWSX806WuzAsU?download=1"

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

def create_onedrive_directdownload(onedrive_link: str) -> str:
    """Converte um link de compartilhamento do OneDrive em um link de download direto."""
    try:
        data_bytes64 = base64.b64encode(bytes(onedrive_link, "utf-8"))
        data_bytes64_string = (
            data_bytes64.decode("utf-8").replace("/", "_").replace("+", "-").rstrip("=")
        )
        return f"https://api.onedrive.com/v1.0/shares/u!{data_bytes64_string}/root/content"
    except Exception as e:
        logger.error(f"Erro ao converter link do OneDrive: {e}")
        return onedrive_link

def safe_to_datetime(series: pd.Series) -> pd.Series:
    """Converte série para datetime com segurança para o formato brasileiro."""
    try:
        return pd.to_datetime(series, errors="coerce", dayfirst=True)
    except Exception as e:
        logger.warning(f"Erro na conversão de data: {e}")
        return pd.Series([pd.NA] * len(series))

def clear_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Limpa strings (remove ; e \n) para evitar quebra de estrutura no CSV."""
    # Seleciona apenas colunas de texto (object)
    str_cols = df.select_dtypes(include=["object"]).columns
    for col in str_cols:
        df.loc[:, col] = (
            df[col]
            .astype(str)
            .str.replace(r"[\r\n;]+", " ", regex=True)
            .str.strip()
            .replace({"nan": None, "None": None, "<NA>": None})
        )
    return df

def clean_currency(series: pd.Series) -> pd.Series:
    """Limpa valores monetários (Ex: R$ 1.234,56 -> 1234.56) e garante tipo float."""
    if series is None or series.empty:
        return pd.Series(dtype=float)

    try:
        clean_series = (
            series.astype(str)
            .str.replace("R$", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.replace(r"\s+", "", regex=True)
            .str.strip()
        )
        # Substitui vazios por 0.0 antes de converter para evitar erros de tipo
        return pd.to_numeric(clean_series, errors="coerce").fillna(0.0).astype(float)
    except Exception as e:
        logger.warning(f"Erro ao limpar coluna monetária: {e}")
        return pd.Series([0.0] * len(series), dtype=float)

def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Remove espaços extras nos nomes das colunas e aplica mapeamento padrão."""
    df.columns = [col.strip() for col in df.columns]
    mapping = {
        "Val.líq.": "VALOR_LIQUIDO",
        "VALOR LIQUIDO": "VALOR_LIQUIDO",
        "DATA ENVIO": "DATA_ENVIO",
        "DATA DOC": "DATA_DOC",
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
    """Função principal para processar fontes do Google Sheets (CSV)."""
    logger.info(f"Processando fonte Google Sheets: {source_name}")
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
    # Aplicar filtros específicos
    df = apply_specific_filters(df, source_name, discards)
    
    # Conversões de data
    if "DATA_ENVIO" in df.columns:
        df.loc[:, "DATA_ENVIO"] = safe_to_datetime(df["DATA_ENVIO"])
    if "DATA_DOC" in df.columns:
        df.loc[:, "DATA_DOC"] = safe_to_datetime(df["DATA_DOC"])

    # Conversões numéricas
    try:
        if "VALOR_LIQUIDO" in df.columns:
            df.loc[:, "VALOR_LIQUIDO"] = clean_currency(df["VALOR_LIQUIDO"])
        if "PEDIDO" in df.columns:
            df.loc[:, "PEDIDO"] = pd.to_numeric(df["PEDIDO"], errors="coerce").fillna(0).astype(int)
        if "CONTRATO" in df.columns:
            df.loc[:, "CONTRATO"] = pd.to_numeric(df["CONTRATO"], errors="coerce").fillna(0).astype(int)
    except Exception as e:
        logger.error(f"Erro ao converter tipos numéricos em {source_name}: {e}")

    # Metadados
    df.loc[:, "CATEGORIA"] = "OBRA" if "obra" in source_name.lower() else "MANUT"
    # FONTE ORIGEM é a junção da BASE e CATEGORIA
    base_val = df["BASE"].astype(str).str.upper() if "BASE" in df.columns else "DESCONHECIDO"
    df.loc[:, "FONTE_ORIGEM"] = base_val + "_" + df["CATEGORIA"]
    return df

def process_cif_source(discards: Dict[str, int]) -> pd.DataFrame:
    """Função específica para processar a fonte fServiço CIF (Excel/OneDrive) seguindo lógica do Power Query."""
    logger.info("Processando fonte OneDrive: fServico_CIF")
    
    try:
        # Baixa o conteúdo do arquivo usando requests para maior robustez
        response = requests.get(CIF_URL, timeout=30)
        response.raise_for_status()
        
        # header=1 equivale ao Table.PromoteHeaders feito duas vezes no Power Query
        df = pd.read_excel(BytesIO(response.content), header=1)
    except Exception as e:
        logger.error(f"Erro ao ler planilha CIF do OneDrive: {e}")
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    total_bruto = len(df)
    # 1. Limpeza inicial de linhas vazias
    df = df.dropna(how="all")
    
    # 2. Remover colunas CTE e STATUS conforme Power Query
    cols_to_drop = ["CTE", "PAGO-VERDE-PENDENTE-VERMELHO"]
    df = df.drop(columns=[c for c in cols_to_drop if c in df.columns])

    # 3. Substituir vazios/strings vazias por NaN para o FillDown
    df = df.replace(r'^\s*$', pd.NA, regex=True)

    # 4. FillDown (Preenchimento para baixo) conforme Power Query
    fill_cols = [
        "DEPOSITO DESTINO", "SERVIÇOS REALIZADO", "MOTORISTA", "FABRICA", 
        "NF", "PEDIDO", "MATERIAL", "QNT", "VALOR UND", "VALOR TOTAL"
    ]
    fill_cols = [c for c in fill_cols if c in df.columns]
    df.loc[:, fill_cols] = df[fill_cols].ffill()

    # 5. Filtrar linhas onde DATA é nulo (conforme Power Query)
    df = df[df["DATA"].notna()]
    
    # 6. Lógica condicional de VALOR (VALOR FATO)
    # #"Coluna Condicional Adicionada" = if [DEPOSITO DESTINO] = "622" then 1960 ...
    def calculate_valor_fato(row):
        dep = str(row.get("DEPOSITO DESTINO", "")).strip()
        if dep == "622": return 1960
        if dep == "654": return 600
        if dep == "725": return 2856
        return None

    # #"Coluna Condicional Adicionada1" = if [SERVIÇOS REALIZADO] = "TRANSPORTE" then [VALOR FATO] else [VALOR TOTAL]
    def calculate_final_valor(row):
        serv = str(row.get("SERVIÇOS REALIZADO", "")).strip().upper()
        valor_total = row.get("VALOR TOTAL", 0)
        if serv == "TRANSPORTE":
            v_fato = calculate_valor_fato(row)
            return v_fato if v_fato is not None else valor_total
        return valor_total

    df.loc[:, "VALOR TOTAL"] = df.apply(calculate_final_valor, axis=1)

    # 7. Mapeamento de DEPOSITO DESTINO (BASE)
    base_map = {
        "654": "Juazeiro",
        "725": "Remanso",
        "622": "Bonfim",
        "724": "Jacobina",
        "Jacobina-JACOBINA": "Jacobina"
    }
    df.loc[:, "DEPOSITO DESTINO"] = df["DEPOSITO DESTINO"].astype(str).replace(base_map)

    # 8. Substituições de texto finais (NÃO ESPECIFICADO / Não especificado)
    if "SERVIÇOS REALIZADO" in df.columns:
        df.loc[:, "SERVIÇOS REALIZADO"] = df["SERVIÇOS REALIZADO"].fillna("NÃO ESPECIFICADO").replace("", "NÃO ESPECIFICADO")
    if "DEPOSITO DESTINO" in df.columns:
        df.loc[:, "DEPOSITO DESTINO"] = df["DEPOSITO DESTINO"].fillna("Não especificado").replace("", "Não especificado")
    if "MATERIAL" in df.columns:
        df.loc[:, "MATERIAL"] = df["MATERIAL"].fillna("Não especificado").replace("", "Não especificado")

    # --- INTEGRAÇÃO COM PADRÕES DO PROJETO ---
    
    # Renomeação específica solicitada pelo usuário
    rename_map = {
        "SERVIÇOS REALIZADO": "TIPO",
        "DEPOSITO DESTINO": "BASE",
        "VALOR TOTAL": "VALOR LIQUIDO",
        "PEDIDO": "PEDIDO"
    }
    df = df.rename(columns=rename_map)
    
    # A coluna DATA vira tanto DATA ENVIO quanto DATA DOC
    if "DATA" in df.columns:
        df.loc[:, "DATA ENVIO"] = df["DATA"]
        df.loc[:, "DATA DOC"] = df["DATA"]
        # Extrair nome do mês para a coluna CICLO (apenas para CIF)
        try:
            temp_date = pd.to_datetime(df["DATA"], errors="coerce", dayfirst=True)
            df.loc[:, "CICLO"] = temp_date.dt.strftime('%B')
        except Exception as e:
            logger.warning(f"Erro ao extrair mês para CICLO em CIF: {e}")

    # Padronização de colunas (converte espaços em underscores, etc)
    df = standardize_columns(df)
    
    # Tratamento de RESPONSAVEL e PEP (regras de negócio do pipeline)
    if "RESPONSAVEL" in df.columns:
        df.loc[:, "RESPONSAVEL"] = df["RESPONSAVEL"].fillna("Logística").replace(["nan", ""], "Logística")
    else:
        df.loc[:, "RESPONSAVEL"] = "Logística"

    if "PEP" in df.columns:
        df.loc[:, "PEP"] = df["PEP"].fillna("CIF - 00000").replace(["nan", ""], "CIF - 00000")
    else:
        df.loc[:, "PEP"] = "CIF - 00000"

    # Conversões finais de tipo
    if "DATA_ENVIO" in df.columns:
        df.loc[:, "DATA_ENVIO"] = safe_to_datetime(df["DATA_ENVIO"])
    if "DATA_DOC" in df.columns:
        df.loc[:, "DATA_DOC"] = safe_to_datetime(df["DATA_DOC"])

    try:
        if "VALOR_LIQUIDO" in df.columns:
            # pd.read_excel já pode ter interpretado como float, mas garantimos
            if df["VALOR_LIQUIDO"].dtype == object:
                df.loc[:, "VALOR_LIQUIDO"] = clean_currency(df["VALOR_LIQUIDO"])
            else:
                df.loc[:, "VALOR_LIQUIDO"] = pd.to_numeric(df["VALOR_LIQUIDO"], errors="coerce").fillna(0.0)
        
        if "PEDIDO" in df.columns:
            df.loc[:, "PEDIDO"] = pd.to_numeric(df["PEDIDO"], errors="coerce").fillna(0).astype(int)
    except Exception as e:
        logger.error(f"Erro ao converter tipos numéricos em fServico_CIF: {e}")

    # Metadados finais
    df.loc[:, "CATEGORIA"] = "CIF"
    base_val = df["BASE"].astype(str).str.upper() if "BASE" in df.columns else "DESCONHECIDO"
    df.loc[:, "FONTE_ORIGEM"] = base_val + "_" + df["CATEGORIA"]
    
    # Salvar alteração da CIF em data raw para auditoria/debug
    try:
        raw_dir = MODULE_ROOT / "data" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        cif_raw_path = raw_dir / "fServico_CIF_processado.csv"
        df.to_csv(cif_raw_path, index=False, sep=";", encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
        logger.info(f"Dados processados do CIF salvos em: {cif_raw_path}")
    except Exception as e:
        logger.warning(f"Erro ao salvar arquivo raw do CIF: {e}")

    discards["Linhas Completamente Vazias"] += (total_bruto - len(df))
    return df

def main() -> None:
    """Ponto de entrada do pipeline de ETL de Pedidos."""
    logger.info("--- Iniciando Pipeline de Pedidos (Obra + Manut + CIF) ---")

    processed_dfs = []
    discards_global = {
        "Linhas Completamente Vazias": 0,
        "Filtro PEP Vazio": 0,
        "Filtro BASE (Não Jacobina)": 0
    }

    # 1. Processar fontes Google Sheets
    for name, sheet_id in IDS_PLANILHAS.items():
        gid = GIDS[name]
        df = process_source(name, sheet_id, gid, discards_global)
        if not df.empty:
            processed_dfs.append(df)
            logger.info(f"Sucesso: {name} ({len(df)} linhas úteis)")

    # 2. Processar fonte CIF (OneDrive)
    df_cif = process_cif_source(discards_global)
    if not df_cif.empty:
        processed_dfs.append(df_cif)
        logger.info(f"Sucesso: fServico_CIF ({len(df_cif)} linhas úteis)")

    if not processed_dfs:
        logger.error("Nenhuma fonte de dados foi processada. Encerrando.")
        return

    logger.info("Consolidando bases (Table.Combine)...")
    df_final = pd.concat(processed_dfs, ignore_index=True)

    # Limpezas e transformações pós-consolidação
    df_final = df_final.dropna(how="all")

    if "RESPONSAVEL" in df_final.columns:
        df_final.loc[:, "RESPONSAVEL"] = df_final["RESPONSAVEL"].astype(str).str.replace("LOGISTICA ", "LOGISTICA", regex=False)

    if "TIPO" in df_final.columns:
        df_final.loc[:, "TIPO"] = df_final["TIPO"].astype(str).replace({
            "Uso Mutuo": "USO MUTUO",
            "Linha Viva Preventiva": "LINHA VIVA"
        })

    if "PEP" in df_final.columns:
        df_final.loc[:, "TEXTO_APOS_DELIMITADOR"] = df_final["PEP"].astype(str).str.split("-", n=1).str[1]
    else:
        df_final.loc[:, "TEXTO_APOS_DELIMITADOR"] = pd.NA

    # Seleção e ordenação final das colunas
    colunas_finais = [
        "DATA_ENVIO", "DATA_DOC", "RESPONSAVEL", "TIPO", "PEP", "TEXTO_APOS_DELIMITADOR",
        "DEFINICAO", "PEDIDO", "VALOR_LIQUIDO", "CONTRATO", "MUNICIPIO", "BASE", "CICLO",
        "DESCRICAO", "SETOR", "TEXTO_BREVE", "FONTE_ORIGEM", "CATEGORIA"
    ]
    for col in colunas_finais:
        if col not in df_final.columns:
            df_final.loc[:, col] = pd.NA

    df_final = df_final[colunas_finais].copy()
    df_final = clear_dataframe(df_final)

    # Formatação final de datas para CSV
    df_final.loc[:, "DATA_ENVIO"] = pd.to_datetime(df_final["DATA_ENVIO"]).dt.date
    df_final.loc[:, "DATA_DOC"] = pd.to_datetime(df_final["DATA_DOC"]).dt.date

    # Salvar output
    output_dir = MODULE_ROOT / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "fPedidos.csv"

    df_final.to_csv(
        output_path,
        index=False,
        sep=";",
        encoding="utf-8-sig",
        date_format="%Y-%m-%d",
        quoting=csv.QUOTE_ALL
    )
    
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

import io
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

# --- Configuração de Logging conforme PADROES_PROJETO.md ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Configurações & Constantes ---
SPREADSHEET_ID_MAIN: str = "1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4"
SPREADSHEET_ID_NOV25: str = "1UCpxyV_pd2TUet6JnefEi9_z80Z_1-8PQxS230soATo"

MODULE_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = MODULE_ROOT / "data" / "raw"
PROCESSED_DIR = MODULE_ROOT / "data" / "processed"
AUDIT_DIR = MODULE_ROOT / "data" / "monthly_audit"
OUTPUT_FILE = PROCESSED_DIR / "carteira_juazeiro_consolidada.csv"
RAW_FILE = RAW_DIR / "carteira_juazeiro_raw.csv"

# Lista base de status para exclusão (o código aplicará strip() e upper() automaticamente)
STATUS_EXCLUIR_GLOBAL = [
    "CANCELADA",  "RETIRADA", "RETIRADA COELBA", 
    "RETIRADA PROGRAMAÇÃO", "SEM CAPACIDADE EXECUTIVA", 
    "ENCERRADA", "PARALIZADA"
]

# Estatísticas globais para o relatório final
stats_descarte: Dict[str, int] = {}
total_bruto_processado: int = 0


def registrar_descarte(motivo: str, quantidade: int) -> None:
    """Registra a quantidade de linhas descartadas por um motivo específico."""
    if quantidade > 0:
        stats_descarte[motivo] = stats_descarte.get(motivo, 0) + quantidade


def save_audit_report(df: pd.DataFrame, label: str) -> None:
    """Salva um relatório de auditoria individual para o mês."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    filename = label.replace(" ", "_").replace("/", "_") + ".csv"
    audit_file = AUDIT_DIR / filename
    try:
        df.to_csv(audit_file, index=False, sep=";", encoding="utf-8-sig")
        logger.info(f"Relatório de auditoria mensal salvo: {audit_file}")
    except Exception as e:
        logger.error(f"Erro ao salvar auditoria de {label}: {e}")


def apply_audit(df: pd.DataFrame, label: str, mask_descarte: pd.Series, motivo: str) -> pd.DataFrame:
    """
    Classifica as linhas como Consolidado/Descartado, salva o relatório mensal
    e retorna apenas as linhas consolidadas para o fluxo principal.
    """
    df_audit = df.copy()
    df_audit.loc[:, "STATUS_AUDITORIA"] = "Consolidado"
    df_audit.loc[:, "MOTIVO_DESCARTE"] = "N/A"

    if mask_descarte.any():
        df_audit.loc[mask_descarte, "STATUS_AUDITORIA"] = "Descartado"
        df_audit.loc[mask_descarte, "MOTIVO_DESCARTE"] = motivo
        registrar_descarte(f"{motivo} ({label})", mask_descarte.sum())

    save_audit_report(df_audit, label)
    return df[~mask_descarte].copy()


def apply_status_filter(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Aplica o descarte global de status indesejados em qualquer coluna que contenha os termos."""
    # Normalizar a lista de exclusão: remover espaços extras e converter para maiúsculas
    status_excluir_limpos = [re.sub(r"\s+", " ", str(s).strip().upper()) for s in STATUS_EXCLUIR_GLOBAL]
    
    mask_total = pd.Series(False, index=df.index)
    
    # Varre todas as colunas do DataFrame para garantir que nenhum status passe, independente do nome da coluna
    for col in df.columns:
        # Tenta aplicar a limpeza e filtro apenas em colunas de texto/objeto
        series_limpa = df[col].astype(str).apply(lambda x: re.sub(r"\s+", " ", str(x).strip().upper()))
        mask_status = series_limpa.isin(status_excluir_limpos)
        mask_total = mask_total | mask_status
        
    if mask_total.any():
        return apply_audit(df, label, mask_total, "Status Excluído (Filtro Agressivo Global)")
    return df


# --- Funções de Extração ---

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Limpa e normaliza os nomes das colunas do DataFrame."""
    df.columns = [str(col).replace("\n", " ").strip() for col in df.columns]
    df.columns = [re.sub(r"\s+", " ", col) for col in df.columns]
    return df


def download_csv(spreadsheet_id: str, gid: str) -> Optional[pd.DataFrame]:
    """Baixa um CSV do Google Sheets via URL pública."""
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"
        df = pd.read_csv(io.StringIO(response.text), dtype=str)
        return normalize_columns(df)
    except Exception as e:
        logger.error(f"Erro ao baixar GID {gid} da planilha {spreadsheet_id}: {e}")
        return None


# --- Funções de Transformação Auxiliares ---

def drop_cols_safe(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Remove colunas do DataFrame apenas se elas existirem."""
    return df.drop(columns=[c for c in cols if c in df.columns], errors="ignore")


# --- Funções de Transformação Específicas (Mensais) ---

def transform_janeiro_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Janeiro 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    df.loc[:, "COORD"] = "JUAZEIRO"
    df.loc[:, "Carteira"] = "01/01/2025"
    crit_col = "CRITÉRIO" if "CRITÉRIO" in df.columns else "CRITERIO"
    mask_descarte = df[crit_col].isna() | (df[crit_col].astype(str).str.strip() == "")
    df = apply_audit(df, label, mask_descarte, "Erro/Nulo em CRITÉRIO")
    if "PROJETO" in df.columns:
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
    cols_to_remove = [
        "PROJETO", "CRITÉRIO", "CRITERIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", 
        "VALOR 30%", "SITUAÇÃO", "SITUACAO", "CARTEIRA", "OBRAS SIMPLIFICADAS", 
        "TECNICO FECHAMENTO", "VISITA PRÉVIA", "VISITA PREVIA", "PRÉ FECHAMENTO", 
        "PRE FECHAMENTO", "SITUAÇÃO_1", "SITUACAO_1", "SITUAÇÃO.1", "SI PG", 
        "PG INICIAL", "PG FINAL", "V. PROJETO"
    ]
    return drop_cols_safe(df, cols_to_remove)


def transform_fevereiro_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Fevereiro 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    df.loc[:, "COORD"] = "JUAZEIRO"
    df.loc[:, "Carteira"] = "01/02/2025"
    crit_col = "CRITÉRIO" if "CRITÉRIO" in df.columns else "CRITERIO"
    mask_descarte = df[crit_col].isna() | (df[crit_col].astype(str).str.strip() == "")
    df = apply_audit(df, label, mask_descarte, "Erro/Nulo em CRITÉRIO")
    if "PROJETO" in df.columns:
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
    cols_to_remove = [
        "PROJETO", "CRITÉRIO", "CRITERIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", 
        "CARTEIRA", "OBRAS SIMPLIFICADAS", "TECNICO FECHAMENTO", "VISITA PRÉVIA", 
        "VISITA PREVIA", "PRÉ FECHAMENTO", "PRE FECHAMENTO", "SI PG", 
        "PG INICIAL", "PG FINAL", "VALOR 25%", "LINK MAPS", "V. PROJETO"
    ]
    return drop_cols_safe(df, cols_to_remove)


def transform_marco_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Março 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    df.loc[:, "COORD"] = "JUAZEIRO"
    df.loc[:, "Carteira"] = "01/03/2025"
    mask_descarte = df["PROJETO"].isna() | (df["PROJETO"].astype(str).str.strip() == "")
    df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO")
    df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
        lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
    )
    cols_to_remove = [
        "PROJETO", "CRITÉRIO", "CRITERIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", 
        "CARTEIRA", "OBRAS SIMPLIFICADAS", "TECNICO FECHAMENTO", "VISITA PRÉVIA", 
        "VISITA PREVIA", "PRÉ FECHAMENTO", "PRE FECHAMENTO", "SI PG", 
        "PG INICIAL", "PG FINAL", "VALOR 25%", "PRE FECHAMENTO", "OBS", "V. PROJETO"
    ]
    return drop_cols_safe(df, cols_to_remove)


def transform_abril_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Abril 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    df.loc[:, "COORD"] = "JUAZEIRO"
    df.loc[:, "Carteira"] = "01/04/2025"
    mask_descarte = df["PROJETO"].isna() | (df["PROJETO"].astype(str).str.strip() == "")
    df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO")
    df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
        lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
    )
    df = df.rename(columns={"TITULO": "TÍTULO"})
    cols_to_remove = [
        "PROJETO", "CRITÉRIO", "CRITERIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", 
        "CARTEIRA", "OBRAS SIMPLIFICADAS", "TECNICO FECHAMENTO", "VISITA PRÉVIA", 
        "VISITA PREVIA", "PRÉ FECHAMENTO", "PRE FECHAMENTO", "SI PG", 
        "PG INICIAL", "PG FINAL", "VALOR 25%", "PRE FECHAMENTO", "OBS", "V. PROJETO"
    ]
    return drop_cols_safe(df, cols_to_remove)


def transform_maio_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Maio 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    df.loc[:, "COORD"] = "JUAZEIRO"
    df.loc[:, "Carteira"] = "01/05/2025"
    mask_descarte = df["PROJETO"].isna() | (df["PROJETO"].astype(str).str.strip() == "")
    df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO")
    df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
        lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
    )
    cols_to_remove = [
        "PROJETO", "CRITÉRIO", "CRITERIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", 
        "CARTEIRA", "OBRAS SIMPLIFICADAS", "SI PG", "PG INICIAL", "PG FINAL", 
        "PRE FECHAMENTO", "V. PROJETO", "STATUS 1"
    ]
    df = drop_cols_safe(df, cols_to_remove)
    rename_map = {"TITULO": "TÍTULO"}
    if "STATUS 1_1" in df.columns: rename_map["STATUS 1_1"] = "STATUS 1"
    elif "STATUS 1.1" in df.columns: rename_map["STATUS 1.1"] = "STATUS 1"
    return df.rename(columns=rename_map)


def transform_junho_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Junho 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    df.loc[:, "COORD"] = "JUAZEIRO"
    df.loc[:, "Carteira"] = "01/06/2025"
    mask_descarte = df["PROJETO"].isna() | (df["PROJETO"].astype(str).str.strip() == "")
    df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO")
    df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
        lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
    )
    cols_to_remove = [
        "PROJETO", "CRITÉRIO", "CRITERIO", "NOTA", "SEPARAR MATERIAL", "CARTEIRA", 
        "OBRAS SIMPLIFICADAS", "SI PG", "PG INICIAL", "PG FINAL", "PRE FECHAMENTO", 
        "V. PROJETO", "STATUS 1"
    ]
    df = drop_cols_safe(df, cols_to_remove)
    rename_map = {"TITULO": "TÍTULO"}
    if "STATUS 1_2" in df.columns: rename_map["STATUS 1_2"] = "STATUS 1"
    elif "STATUS 1.2" in df.columns: rename_map["STATUS 1.2"] = "STATUS 1"
    return df.rename(columns=rename_map)


def transform_julho_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Julho 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    df.loc[:, "COORD"] = "JUAZEIRO"
    df.loc[:, "Carteira"] = "01/07/2025"
    mask_descarte = df["PROJETO"].isna() | (df["PROJETO"].astype(str).str.strip() == "")
    df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO")
    df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
        lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
    )
    cols_to_remove = [
        "PROJETO", "CRITÉRIO", "CRITERIO", "NOTA", "SEPARAR MATERIAL", 
        "OBRAS SIMPLIFICADAS", "SI PG", "PG INICIAL", "PG FINAL", "PRE FECHAMENTO", 
        "V. PROJETO", "STATUS 1"
    ]
    df = drop_cols_safe(df, cols_to_remove)
    rename_map = {"TITULO": "TÍTULO"}
    if "STATUS 1_1" in df.columns: rename_map["STATUS 1_1"] = "STATUS 1"
    elif "STATUS 1.1" in df.columns: rename_map["STATUS 1.1"] = "STATUS 1"
    return df.rename(columns=rename_map)


def transform_agosto_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Agosto 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    df.loc[:, "COORD"] = "JUAZEIRO"
    df.loc[:, "Carteira"] = "01/08/2025"
    mask_descarte = df["PROJETO"].isna() | (df["PROJETO"].astype(str).str.strip() == "")
    df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO")
    df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
        lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
    )
    cols_to_remove = [
        "PROJETO", "CRITÉRIO", "CRITERIO", "NOTA", "SEPARAR MATERIAL", 
        "OBRAS SIMPLIFICADAS", "SI PG", "PG INICIAL", "PG FINAL", "PRE FECHAMENTO", 
        "V. PROJETO", "STATUS 1"
    ]
    df = drop_cols_safe(df, cols_to_remove)
    rename_map = {"TITULO": "TÍTULO"}
    if "STATUS 1_2" in df.columns: rename_map["STATUS 1_2"] = "STATUS 1"
    elif "STATUS 1.2" in df.columns: rename_map["STATUS 1.2"] = "STATUS 1"
    return df.rename(columns=rename_map)


def transform_setembro_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Setembro 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    df.loc[:, "COORD"] = "JUAZEIRO"
    df.loc[:, "Carteira"] = "01/09/2025"
    mask_descarte = df["PROJETO"].isna() | (df["PROJETO"].astype(str).str.strip() == "")
    df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO")
    df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
        lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
    )
    cols_to_remove = [
        "PROJETO", "CRITÉRIO", "CRITERIO", "NOTA", "SEPARAR MATERIAL", 
        "OBRAS SIMPLIFICADAS", "SI PG", "PG INICIAL", "PG FINAL", "PRE FECHAMENTO", 
        "V. PROJETO", "STATUS 1"
    ]
    df = drop_cols_safe(df, cols_to_remove)
    rename_map = {"TITULO": "TÍTULO"}
    if "STATUS 1_2" in df.columns: rename_map["STATUS 1_2"] = "STATUS 1"
    elif "STATUS 1.2" in df.columns: rename_map["STATUS 1.2"] = "STATUS 1"
    return df.rename(columns=rename_map)


def transform_novembro_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Novembro 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    mask_filtro_mes = (
        df["CARTEIRA"].isna() | 
        (df["CARTEIRA"].astype(str).str.strip() == "") |
        df["CARTEIRA"].astype(str).str.upper().isin(["AGOSTO", "JULHO"])
    )
    df = apply_audit(df, label, mask_filtro_mes, "Filtro CARTEIRA (Vazio/Agosto/Julho)")
    df.loc[:, "COORD"] = "JUAZEIRO"
    df = df.rename(columns={"STATUS": "STATUS 1"})

    def parse_dynamic_date(val: Any) -> Any:
        try:
            dt = pd.to_datetime(val, dayfirst=True, errors="raise")
            return dt.replace(day=1).strftime("%Y-%m-%d")
        except:
            try:
                texto = str(val).strip().title()
                meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
                         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
                partes = texto.split()
                nome_mes = partes[0]
                ano = int(partes[1]) if len(partes) > 1 else 2025
                num_mes = meses.index(nome_mes) + 1
                return f"{ano}-{num_mes:02d}-01"
            except:
                return None

    df.loc[:, "Carteira"] = df["CARTEIRA"].apply(parse_dynamic_date)
    mask_erro_proj = df["PROJETO"].isna() | (df["PROJETO"].astype(str).str.strip() == "")
    df = apply_audit(df, label, mask_erro_proj, "Erro/Nulo em PROJETO")
    df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
        lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
    )
    df = df.rename(columns={
        "PSTP INICIAL": "PSTP", "ENERGIZAÇÃO": "DATA DE ENERG.", "PSTP FINAL": "PST REALZ"
    })
    
    if "STATUS 1" in df.columns:
        df.loc[:, "STATUS 1"] = df["STATUS 1"].astype(str).str.replace("CONCLUÍDA", "CONCLUIDA", case=False)
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])


# --- Orquestração Final ---

def apply_final_business_rules(df: pd.DataFrame) -> pd.DataFrame:
    final_df = df.copy()
    if "STATUS 1" in final_df.columns:
        if "STATUS" in final_df.columns:
            final_df.loc[:, "STATUS"] = final_df["STATUS"].fillna(final_df["STATUS 1"])
            final_df = final_df.drop(columns=["STATUS 1"])
        else:
            final_df = final_df.rename(columns={"STATUS 1": "STATUS"})
    final_df = final_df.loc[:, ~final_df.columns.duplicated()].copy()
    if "STATUS" in final_df.columns:
        final_df.loc[:, "STATUS"] = final_df["STATUS"].fillna("NÃO DEFINIDO").replace("", "NÃO DEFINIDO")
        # Normalização agressiva para garantir remoção de variações com espaços/quebras de linha
        status_excluir_limpos = [re.sub(r"\s+", " ", str(s).strip().upper()) for s in STATUS_EXCLUIR_GLOBAL]
        status_series_limpa = final_df["STATUS"].astype(str).apply(lambda x: re.sub(r"\s+", " ", str(x).strip().upper()))
        final_df = final_df[~status_series_limpa.isin(status_excluir_limpos)].copy()
        
    # Remover linhas sem projeto válido ou zerado (0000000) que podem ter passado
    if "PROJETO_FATO" in final_df.columns:
        mask_proj_invalido = (
            final_df["PROJETO_FATO"].astype(str).str.strip() == "0000000"
        )
        final_df = final_df[~mask_proj_invalido].copy()
    if "PST REALZ" in final_df.columns:
        final_df.loc[:, "PST REALZ"] = final_df["PST REALZ"].astype(str).replace("MANTER", "").replace("nan", "")
        if "PST EXEC" in final_df.columns:
            mask = (final_df["PST REALZ"].notna()) & (final_df["PST REALZ"].astype(str).str.strip() != "")
            final_df.loc[mask, "PST EXEC"] = final_df.loc[mask, "PST REALZ"]
        else:
            final_df.loc[:, "PST EXEC"] = final_df["PST REALZ"]
        final_df = final_df.drop(columns=["PST REALZ"])
    final_df = final_df.rename(columns={"AVANÇO": "AVNP"})
    if "PROJETO_FATO" in final_df.columns:
        final_df.loc[:, "PROJETO_FATO"] = final_df["PROJETO_FATO"].astype(str).str.strip()
    final_df.loc[:, "Carteira"] = pd.to_datetime(final_df["Carteira"], errors="coerce").dt.strftime("%d/%m/%Y")
    cols_priority = ["PROJETO_FATO", "Carteira", "COORD"]
    other_cols = [c for c in final_df.columns if c not in cols_priority]
    final_df = final_df[cols_priority + other_cols]
    return final_df


def main() -> None:
    global total_bruto_processado
    logger.info("=== Pipeline ETL: Carteira Juazeiro Iniciado ===")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    config: List[Tuple[Any, str, str, str]] = [
        (transform_janeiro_25, SPREADSHEET_ID_MAIN, "1548756285", "Janeiro 25"),
        (transform_fevereiro_25, SPREADSHEET_ID_MAIN, "1626411524", "Fevereiro 25"),
        (transform_marco_25, SPREADSHEET_ID_MAIN, "126446266", "Março 25"),
        (transform_abril_25, SPREADSHEET_ID_MAIN, "1840046184", "Abril 25"),
        (transform_maio_25, SPREADSHEET_ID_MAIN, "1785994027", "Maio 25"),
        (transform_junho_25, SPREADSHEET_ID_MAIN, "303077464", "Junho 25"),
        (transform_julho_25, SPREADSHEET_ID_MAIN, "1154290852", "Julho 25"),
        (transform_agosto_25, SPREADSHEET_ID_MAIN, "1144098908", "Agosto 25"),
        (transform_setembro_25, SPREADSHEET_ID_MAIN, "161592956", "Setembro 25"),
        (transform_novembro_25, SPREADSHEET_ID_NOV25, "168881969", "Novembro 25"),
    ]

    all_dfs_raw = []
    all_dfs_proc = []

    for func, sid, gid, label in config:
        logger.info(f"Extraindo: {label}")
        df_downloaded = download_csv(sid, gid)
        if df_downloaded is not None:
            total_bruto_processado += len(df_downloaded)
            df_tag = df_downloaded.copy()
            df_tag.loc[:, "ORIGEM_ETL"] = label
            all_dfs_raw.append(df_tag)
            try:
                df_proc = func(df_downloaded)
                all_dfs_proc.append(df_proc)
            except Exception as e:
                logger.error(f"Falha na transformação de {label}: {e}", exc_info=True)

    if all_dfs_raw:
        df_raw_consolidated = pd.concat(all_dfs_raw, ignore_index=True)
        try:
            df_raw_consolidated.to_csv(RAW_FILE, index=False, sep=";", encoding="utf-8-sig")
            logger.info(f"Arquivo RAW salvo com sucesso: {RAW_FILE}")
        except Exception as e:
            logger.warning(f"Não foi possível salvar o arquivo RAW: {e}")

    if all_dfs_proc:
        final_df = pd.concat(all_dfs_proc, ignore_index=True)
        final_df = apply_final_business_rules(final_df)
        try:
            final_df.to_csv(OUTPUT_FILE, index=False, sep=";", encoding="utf-8-sig")
            logger.info(f"Arquivo PROCESSED salvo com sucesso: {OUTPUT_FILE}")
        except Exception as e:
            logger.critical(f"Erro ao salvar arquivo final: {e}")
            return

        total_removidas = sum(stats_descarte.values())
        logger.info("=== BALANÇO FINAL DO PROCESSAMENTO ===")
        logger.info(f"Total Bruto: {total_bruto_processado}")
        logger.info(f"Total Removido: {total_removidas}")
        logger.info(f"Total Final: {len(final_df)}")
        for motivo, qtd in stats_descarte.items():
            logger.info(f"  - {motivo}: {qtd}")
        logger.info("=======================================")


if __name__ == "__main__":
    main()

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
# ID identificada no test_gids.py
SPREADSHEET_ID_MAIN: str = "1cMU4ncHlk2vIkPGreMvYZUJuLdTQyFrKLxKfR2q2T6I"
# ID Específico para Abril/25 conforme instrução
SPREADSHEET_ID_ABRIL_25: str = "1DOD3vr0dLY2uccTfie4gbFz4Bg0qKL8yzEYdT3XpytM"

# Caminho para arquivos locais no OneDrive
ONEDRIVE_BASE_PATH = Path(r"C:\Users\sipel\OneDrive - sipel.com.br\Dashboard - Tecnico\Base de Dados")

MODULE_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = MODULE_ROOT / "data" / "raw"
PROCESSED_DIR = MODULE_ROOT / "data" / "processed"
AUDIT_DIR = MODULE_ROOT / "data" / "monthly_audit"
OUTPUT_FILE = PROCESSED_DIR / "carteira_bonfim_consolidada.csv"
RAW_FILE = RAW_DIR / "carteira_bonfim_raw.csv"

# Lista base de status para exclusão (seguindo padrão Juazeiro)
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
    """Salva um relatório de auditoria individual para o mês em Bonfim."""
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
    status_excluir_limpos = [re.sub(r"\s+", " ", str(s).strip().upper()) for s in STATUS_EXCLUIR_GLOBAL]
    mask_total = pd.Series(False, index=df.index)
    
    for col in df.columns:
        if df[col].dtype == 'object':
            series_limpa = df[col].astype(str).apply(lambda x: re.sub(r"\s+", " ", str(x).strip().upper()))
            mask_status = series_limpa.isin(status_excluir_limpos)
            mask_total = mask_total | mask_status
        
    if mask_total.any():
        return apply_audit(df, label, mask_total, "Status Excluído (Filtro Global)")
    return df


# --- Funções de Extração ---

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Limpa e normaliza os nomes das colunas do DataFrame."""
    df.columns = [str(col).replace("\n", " ").strip() for col in df.columns]
    df.columns = [re.sub(r"\s+", " ", col) for col in df.columns]
    return df


def extract_excel_local(file_path: Path, sheet_name: str = "Planilha1") -> Optional[pd.DataFrame]:
    """Extrai dados de um arquivo Excel local."""
    try:
        if not file_path.exists():
            logger.error(f"Arquivo não encontrado: {file_path}")
            return None
        
        df = pd.read_excel(file_path, sheet_name=sheet_name, dtype=str)
        logger.info(f"Extração local concluída: {file_path.name} ({len(df)} linhas)")
        return normalize_columns(df)
    except Exception as e:
        logger.error(f"Erro ao extrair Excel local {file_path}: {e}")
        return None


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


def drop_cols_safe(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Remove colunas do DataFrame apenas se elas existirem."""
    return df.drop(columns=[c for c in cols if c in df.columns], errors="ignore")


# --- Funções de Extração Específicas ---

def extract_janeiro_25() -> Optional[pd.DataFrame]:
    """Extração específica para Janeiro 2025 (Arquivo Local OneDrive)."""
    file_path = ONEDRIVE_BASE_PATH / "BKP - CARTEIRA JANEIRO 2025 - SBF.xlsx"
    return extract_excel_local(file_path, sheet_name="Planilha1")


def extract_fevereiro_25() -> Optional[pd.DataFrame]:
    """Extração específica para Fevereiro 2025 (Arquivo Local OneDrive)."""
    file_path = ONEDRIVE_BASE_PATH / "BKP - CARTEIRA FEVEREIRO 2025 - SBF.xlsx"
    return extract_excel_local(file_path, sheet_name="Planilha1")


def extract_marco_25() -> Optional[pd.DataFrame]:
    """Extração específica para Março 2025 (Arquivo Local OneDrive)."""
    file_path = ONEDRIVE_BASE_PATH / "BKP - CARTEIRA MARÇO 2025 - SBF.xlsx"
    return extract_excel_local(file_path, sheet_name="Planilha1")


# --- Funções de Transformação Específicas (Bonfim - 14 Meses) ---

def transform_mes_padrao(df: pd.DataFrame, label: str, dt_carteira: str) -> pd.DataFrame:
    """Transformação base para os meses de Bonfim."""
    df = df.copy()
    df = apply_status_filter(df, label)
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = dt_carteira
    
    # Lógica de Projeto (Padrão 7 dígitos)
    if "PROJETO" in df.columns:
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
    
    return df

# --- 2025 ---
def transform_janeiro_25(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tratamento específico para Janeiro 2025 conforme Power Query fornecido.
    - Renomeia colunas para o padrão da Fato.
    - Adiciona COORD=BONFIM e Carteira=01/01/2025.
    - Extrai ID do projeto após o hifen.
    """
    label = "Janeiro 25"
    df = df.copy()
    
    # Renomeações conforme Power Query
    rename_map = {
        "POSTES REAL": "PST EXEC",
        "MUNICÍPIO": "MUNICIPIO",
        "POSTES PREV": "PSTP",
        "CRITÉRIO": "CRITERIO",
        "INICIO": "PV. INICIO",
        "FIM": "PV. FIM"
    }
    df = df.rename(columns=rename_map)
    
    # Adição de Colunas Fixas
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-01-01"
    df.loc[:, "STATUS 1"] = "INDEFINIDO"
    
    # Lógica de Projeto: Text.AfterDelimiter(_, "-")
    if "PROJETO" in df.columns:
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        
        # Auditoria de Projetos Inválidos (Equivale a RemoveRowsWithErrors)
        mask_descarte = (df["PROJETO_FATO"].isna()) | (df["PROJETO_FATO"].astype(str).str.strip() == "")
        df = apply_audit(df, label, mask_descarte, "Erro em PROJETO")
        
    return df

def transform_fevereiro_25(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tratamento específico para Fevereiro 2025 conforme Power Query fornecido.
    - Renomeia colunas (PST EXEC, MUNICIPIO, PSTP).
    - Adiciona COORD=BONFIM e Carteira=01/02/2025.
    - Extrai ID do projeto após o hifen.
    - Filtra linhas onde PROJETO_FATO não é vazio.
    - Adiciona STATUS 1=INDEFINIDO.
    """
    label = "Fevereiro 25"
    df = df.copy()
    
    # Renomeações conforme Power Query
    rename_map = {
        "POSTES REAL": "PST EXEC",
        "MUNICÍPIO": "MUNICIPIO",
        "POSTES PREV": "PSTP",
        "CRITÉRIO": "CRITERIO"
    }
    df = df.rename(columns=rename_map)
    
    # Adição de Colunas Fixas
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-02-01"
    df.loc[:, "STATUS 1"] = "INDEFINIDO"
    
    # Lógica de Projeto: Text.AfterDelimiter(_, "-")
    if "PROJETO" in df.columns:
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        
        # Auditoria e Filtro (PROJETO_FATO <> "")
        mask_descarte = (
            (df["PROJETO_FATO"].isna()) | 
            (df["PROJETO_FATO"].astype(str).str.strip() == "") |
            (df["PROJETO_FATO"].astype(str).str.upper() == "NAN")
        )
        df = apply_audit(df, label, mask_descarte, "Projeto Vazio/Inválido")
        
    return df


def transform_marco_25(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tratamento específico para Março 2025 conforme Power Query fornecido.
    - Renomeia colunas (PST EXEC, MUNICIPIO, PSTP).
    - Adiciona COORD=BONFIM e Carteira=01/03/2025.
    - Extrai ID do projeto após o hifen.
    - Filtra linhas onde PROJETO_FATO não é vazio.
    - Adiciona STATUS 1=INDEFINIDO.
    """
    label = "Março 25"
    df = df.copy()
    
    # Renomeações conforme Power Query
    rename_map = {
        "POSTES REAL": "PST EXEC",
        "MUNICÍPIO": "MUNICIPIO",
        "POSTES PREV": "PSTP",
        "CRITÉRIO": "CRITERIO"
    }
    df = df.rename(columns=rename_map)
    
    # Adição de Colunas Fixas
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-03-01"
    df.loc[:, "STATUS 1"] = "INDEFINIDO"
    
    # Lógica de Projeto: Text.AfterDelimiter(_, "-")
    if "PROJETO" in df.columns:
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        
        # Auditoria e Filtro (PROJETO_FATO <> "")
        mask_descarte = (
            (df["PROJETO_FATO"].isna()) | 
            (df["PROJETO_FATO"].astype(str).str.strip() == "") |
            (df["PROJETO_FATO"].astype(str).str.upper() == "NAN")
        )
        df = apply_audit(df, label, mask_descarte, "Projeto Vazio/Inválido")
        
    return df


def transform_abril_25(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tratamento específico para Abril 2025 conforme Power Query fornecido.
    - Renomeações (STATUS 1, OBRAS SIMPLIFICADAS, PST EXEC, AVANÇO, CARTEIRA, TÍTULO).
    - Adiciona COORD=BONFIM e Carteira=01/04/2025.
    - Lógica de delimitador no PROJETO.
    """
    label = "Abril 25"
    df = df.copy()
    
    # Renomeações conforme Power Query
    rename_map = {
        "STATUS": "STATUS 1",
        "SIMPLIFICADA": "OBRAS SIMPLIFICADAS",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "MUNICIPIO": "MUNICIPIO",
        "CART.": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    # Adição de Colunas Fixas
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-04-01"
    
    if "PROJETO" in df.columns:
        # Lógica: Texto após o delimitador '-'
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        
        # Auditoria de Projetos Inválidos (Equivale a RemoveRowsWithErrors e SelectRows)
        mask_descarte = (
            (df["PROJETO_FATO"].isna()) | 
            (df["PROJETO_FATO"].astype(str).str.strip() == "")
        )
        df = apply_audit(df, label, mask_descarte, "Projeto Vazio/Erro")
        
        # Normalização opcional para 7 dígitos para manter consistência na Fato
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip().isdigit() else str(x)
        )
    
    # Aplicar filtros globais de status
    df = apply_status_filter(df, label)
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])


def transform_maio_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Maio 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    
    # Renomeações conforme Power Query (Idêntico a Abril)
    rename_map = {
        "STATUS": "STATUS 1",
        "SIMPLIFICADA": "OBRAS SIMPLIFICADAS",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "CART.": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-05-01"
    
    if "PROJETO" in df.columns:
        # Lógica: Texto após o delimitador '-'
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        # Normalização para 7 dígitos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
        
        # Auditoria de Projetos Inválidos
        mask_descarte = (df["PROJETO_FATO"] == "0000000") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO_FATO")
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])

def transform_junho_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Junho 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    
    # Renomeações conforme Power Query (Idêntico a Maio)
    rename_map = {
        "STATUS": "STATUS 1",
        "SIMPLIFICADA": "OBRAS SIMPLIFICADAS",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "CART.": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-06-01"
    
    if "PROJETO" in df.columns:
        # Lógica: Texto após o delimitador '-'
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        # Normalização para 7 dígitos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
        
        # Auditoria de Projetos Inválidos
        mask_descarte = (df["PROJETO_FATO"] == "0000000") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO_FATO")
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])

def transform_julho_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Julho 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    
    # Renomeações conforme Power Query (Idêntico aos meses anteriores)
    rename_map = {
        "STATUS": "STATUS 1",
        "SIMPLIFICADA": "OBRAS SIMPLIFICADAS",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "CART.": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-07-01"
    
    if "PROJETO" in df.columns:
        # Lógica: Texto após o delimitador '-'
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        # Normalização para 7 dígitos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
        
        # Auditoria de Projetos Inválidos
        mask_descarte = (df["PROJETO_FATO"] == "0000000") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO_FATO")
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])

def transform_agosto_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Agosto 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    
    # Renomeações conforme Power Query
    rename_map = {
        "STATUS": "STATUS 1",
        "SIMPLIFICADA": "OBRAS SIMPLIFICADAS",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "CART.": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-08-01"
    
    if "PROJETO" in df.columns:
        # Lógica: Texto após o delimitador '-'
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        # Normalização para 7 dígitos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
        
        # Auditoria de Projetos Inválidos
        mask_descarte = (df["PROJETO_FATO"] == "0000000") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO_FATO")
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])

def transform_setembro_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Setembro 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    
    # Renomeações conforme Power Query
    rename_map = {
        "STATUS": "STATUS 1",
        "SIMPLIFICADA": "OBRAS SIMPLIFICADAS",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "CART.": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-09-01"
    
    if "PROJETO" in df.columns:
        # Lógica: Texto após o delimitador '-'
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        # Normalização para 7 dígitos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
        
        # Auditoria de Projetos Inválidos
        mask_descarte = (df["PROJETO_FATO"] == "0000000") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO_FATO")
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])

def transform_outubro_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Outubro 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    
    # Renomeações conforme Power Query
    rename_map = {
        "STATUS": "STATUS 1",
        "SIMPLIFICADA": "OBRAS SIMPLIFICADAS",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "CART.": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-10-01"
    
    if "PROJETO" in df.columns:
        # Lógica: Texto após o delimitador '-'
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        # Normalização para 7 dígitos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
        
        # Auditoria de Projetos Inválidos
        mask_descarte = (df["PROJETO_FATO"] == "0000000") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO_FATO")
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])

def transform_novembro_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Novembro 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    
    # Renomeações conforme Power Query Novembro
    rename_map = {
        "STATUS": "STATUS 1",
        "SIMPLIFICADA": "OBRAS SIMPLIFICADAS",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "CAT": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-11-01"
    
    if "PROJETO" in df.columns:
        # Lógica Power Query: Text.AfterDelimiter(_, "-")
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        # Normalização para 7 dígitos (Padrão do Projeto)
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
        
        # Auditoria de Projetos Inválidos (Equivale a RemoveRowsWithErrors)
        mask_descarte = (df["PROJETO_FATO"] == "0000000") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO_FATO")
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])

def transform_dezembro_25(df: pd.DataFrame) -> pd.DataFrame:
    label = "Dezembro 25"
    df = df.copy()
    df = apply_status_filter(df, label)
    
    # Renomeações conforme Power Query Dezembro
    rename_map = {
        "STATUS": "STATUS 1",
        "SIMPLIFICADA": "OBRAS SIMPLIFICADAS",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "CAT": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2025-12-01"
    
    if "PROJETO" in df.columns:
        # Lógica: Texto após o delimitador '-'
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        # Normalização para 7 dígitos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
        
        # Auditoria de Projetos Inválidos
        mask_descarte = (df["PROJETO_FATO"] == "0000000") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO_FATO")
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])

# --- 2026 ---
def transform_janeiro_26(df: pd.DataFrame) -> pd.DataFrame:
    label = "Janeiro 26"
    df = df.copy()
    df = apply_status_filter(df, label)
    
    # Renomeações conforme Power Query Janeiro 26
    rename_map = {
        "STATUS": "STATUS 1",
        "SIMPLIFICADA": "OBRAS SIMPLIFICADAS",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "CART": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2026-01-01"
    
    if "PROJETO" in df.columns:
        # Lógica: Texto após o delimitador '-'
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        # Normalização para 7 dígitos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
        
        # Auditoria de Projetos Inválidos
        mask_descarte = (df["PROJETO_FATO"] == "0000000") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO_FATO")
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])

def transform_fevereiro_26(df: pd.DataFrame) -> pd.DataFrame:
    label = "Fevereiro 26"
    df = df.copy()
    df = apply_status_filter(df, label)
    
    # Renomeações conforme Power Query Fevereiro 26
    rename_map = {
        "STATUS": "STATUS 1",
        "PSTR": "PST EXEC",
        "AVNP": "AVANÇO",
        "CART": "CARTEIRA",
        "TITULO": "TÍTULO"
    }
    df = df.rename(columns=rename_map)
    
    df.loc[:, "COORD"] = "SENHOR DO BONFIM"
    df.loc[:, "Carteira"] = "2026-02-01"
    
    if "PROJETO" in df.columns:
        # Lógica: Texto após o delimitador '-'
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].apply(
            lambda x: str(x).split("-")[-1].strip() if pd.notna(x) and "-" in str(x) else str(x)
        )
        # Normalização para 7 dígitos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if pd.notna(x) and str(x).strip() != "" else "0000000"
        )
        
        # Auditoria de Projetos Inválidos
        mask_descarte = (df["PROJETO_FATO"] == "0000000") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_descarte, "Erro/Nulo em PROJETO_FATO")
    
    return drop_cols_safe(df, ["PROJETO", "CARTEIRA"])


# --- Orquestração Final ---

def apply_final_business_rules(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica regras de negócio finais e limpa o dataset consolidado."""
    final_df = df.copy()
    
    # Padronização de STATUS (Unificação de colunas)
    status_cols = ["STATUS", "STATUS 1", "SITUAÇÃO", "SITUACAO"]
    for col in status_cols:
        if col in final_df.columns and col != "STATUS":
            if "STATUS" not in final_df.columns:
                final_df["STATUS"] = final_df[col]
            else:
                # Preencher nulos de STATUS com valores das outras colunas mapeadas
                final_df.loc[:, "STATUS"] = final_df["STATUS"].fillna(final_df[col])
            final_df = final_df.drop(columns=[col])

    # Remover duplicidade de colunas se houver
    final_df = final_df.loc[:, ~final_df.columns.duplicated()].copy()
    
    if "STATUS" in final_df.columns:
        # Limpeza de Status (Remover espaços, converter para maiúsculas para comparação)
        final_df.loc[:, "STATUS"] = final_df["STATUS"].astype(str).str.strip()
        
        # Unificar "INDEFINIDO" e "NÃO DEFINIDO" para "NÃO DEFINIDO"
        mask_indefinido = final_df["STATUS"].str.upper().isin(["INDEFINIDO", "NÃO DEFINIDO", "NAN", "NONE", ""])
        final_df.loc[mask_indefinido, "STATUS"] = "NÃO DEFINIDO"
        
        # Remover status espúrios (comprimento <= 1, como "s")
        mask_lixo = final_df["STATUS"].str.len() <= 1
        if mask_lixo.any():
            logger.info(f"Removendo {mask_lixo.sum()} linhas com status inválido (lixo).")
            final_df = final_df[~mask_lixo].copy()
        
    # Limpeza de projetos inválidos
    if "PROJETO_FATO" in final_df.columns:
        mask_proj_invalido = (final_df["PROJETO_FATO"].astype(str).str.strip() == "0000000")
        final_df = final_df[~mask_proj_invalido].copy()
        final_df.loc[:, "PROJETO_FATO"] = final_df["PROJETO_FATO"].astype(str).str.strip()

    # Formatação de Data
    final_df.loc[:, "Carteira"] = pd.to_datetime(final_df["Carteira"], errors="coerce").dt.strftime("%d/%m/%Y")
    
    # Ordenação Final
    cols_priority = ["PROJETO_FATO", "Carteira", "COORD"]
    other_cols = sorted([c for c in final_df.columns if c not in cols_priority])
    final_df = final_df[cols_priority + other_cols]
    
    return final_df


def main() -> None:
    global total_bruto_processado
    logger.info("=== Pipeline ETL: Carteira Senhor do Bonfim Iniciado ===")
    
    # Garantir pastas
    for d in [RAW_DIR, PROCESSED_DIR, AUDIT_DIR]: d.mkdir(parents=True, exist_ok=True)

    # Configuração de Meses (Suporta Extração Local ou Google Sheets)
    config: List[Dict[str, Any]] = [
        {"label": "Janeiro 25", "func": transform_janeiro_25, "extract": extract_janeiro_25},
        {"label": "Fevereiro 25", "func": transform_fevereiro_25, "extract": extract_fevereiro_25},
        {"label": "Março 25", "func": transform_marco_25, "extract": extract_marco_25},
        {"label": "Abril 25", "func": transform_abril_25, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "352572915"},
        {"label": "Maio 25", "func": transform_maio_25, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "1538973229"},
        {"label": "Junho 25", "func": transform_junho_25, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "154253023"},
        {"label": "Julho 25", "func": transform_julho_25, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "802629941"},
        {"label": "Agosto 25", "func": transform_agosto_25, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "1055481720"},
        {"label": "Setembro 25", "func": transform_setembro_25, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "154144771"},
        {"label": "Outubro 25", "func": transform_outubro_25, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "918006793"},
        {"label": "Novembro 25", "func": transform_novembro_25, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "1996567493"},
        {"label": "Dezembro 25", "func": transform_dezembro_25, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "727674487"},
        {"label": "Janeiro 26", "func": transform_janeiro_26, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "309796070"},
        {"label": "Fevereiro 26", "func": transform_fevereiro_26, "sid": SPREADSHEET_ID_ABRIL_25, "gid": "1832293104"},
    ]

    all_dfs_raw = []
    all_dfs_proc = []

    for item in config:
        label = item["label"]
        func = item["func"]
        logger.info(f"Processando: {label}")
        
        # Lógica de Extração Flexível
        if "extract" in item:
            df_downloaded = item["extract"]()
        else:
            df_downloaded = download_csv(item["sid"], item["gid"])
            
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
        pd.concat(all_dfs_raw, ignore_index=True).to_csv(RAW_FILE, index=False, sep=";", encoding="utf-8-sig")

    if all_dfs_proc:
        final_df = pd.concat(all_dfs_proc, ignore_index=True)
        final_df = apply_final_business_rules(final_df)
        final_df.to_csv(OUTPUT_FILE, index=False, sep=";", encoding="utf-8-sig")

        logger.info("=== BALANÇO FINAL DO PROCESSAMENTO (BONFIM) ===")
        logger.info(f"Total Bruto: {total_bruto_processado} | Final: {len(final_df)}")
        for motivo, qtd in stats_descarte.items():
            logger.info(f"  - {motivo}: {qtd}")


if __name__ == "__main__":
    main()

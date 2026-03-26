import io
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

import pandas as pd
import requests

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# --- Configurações & Constantes ---
SPREADSHEET_ID_MAIN: str = "1cMU4ncHlk2vIkPGreMvYZUJuLdTQyFrKLxKfR2q2T6I" 
SPREADSHEET_ID_ABR_SET: str = "1YZB4ZryV_22BJ__4pekdGD7cz5i9HNy27Th-XfmdtDM"

MODULE_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = MODULE_ROOT / "data" / "raw"
PROCESSED_DIR = MODULE_ROOT / "data" / "processed"
AUDIT_DIR = MODULE_ROOT / "data" / "monthly_audit"
OUTPUT_FILE = PROCESSED_DIR / "carteira_jacobina_consolidada.csv"
RAW_FILE = RAW_DIR / "carteira_jacobina_raw.csv"

STATUS_EXCLUIR_GLOBAL = [
    "CANCELADA", "RETIRADA", "RETIRADA COELBA", "RETIRADA PROGRAMAÇÃO", "SEM CAPACIDADE EXECUTIVA", "ENCERRADA",
    "CANCELADA - OBRAS AGEIS STC", "CANCELADA - OBRAS AGEIS STC - ENERGIZADA", "CANCELADA - SOLICITAR REVISÃO",
    "CANCELADA - TRANSFERIDA PARA OUTRA EPS", "CANCELADA SERVIÇO POSTO GASOLINA", "CANCELADO"
]

stats_descarte: Dict[str, int] = {}
total_bruto_processado: int = 0

def registrar_descarte(motivo: str, quantidade: int) -> None:
    if quantidade > 0: stats_descarte[motivo] = stats_descarte.get(motivo, 0) + quantidade

def save_audit_report(df: pd.DataFrame, label: str) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    filename = label.replace(" ", "_").replace("/", "_") + ".csv"
    try: df.to_csv(AUDIT_DIR / filename, index=False, sep=";", encoding="utf-8-sig")
    except Exception as e: logger.error(f"Erro ao salvar auditoria de {label}: {e}")

def apply_audit(df: pd.DataFrame, label: str, mask_descarte: pd.Series, motivo: str) -> pd.DataFrame:
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
    """Filtra o DataFrame baseado em status indesejados de forma robusta."""
    status_excluir_limpos = [re.sub(r"\s+", " ", str(s).strip().upper()) for s in STATUS_EXCLUIR_GLOBAL]
    
    linhas_descarte = set()
    
    # Itera sobre todas as colunas de texto para buscar status proibidos
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]):
            # Normalização rigorosa: remove espaços múltiplos e converte para maiúsculas
            mask = df[col].astype(str).str.strip().str.upper().apply(
                lambda x: re.sub(r"\s+", " ", x)
            ).isin(status_excluir_limpos)
            linhas_descarte.update(df.index[mask].tolist())
    
    if linhas_descarte:
        mask_total = df.index.isin(linhas_descarte)
        return apply_audit(df, label, pd.Series(mask_total, index=df.index), "Status Excluído (Filtro Global)")
    return df

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [re.sub(r"\s+", " ", str(col).replace("\n", " ").strip()) for col in df.columns]
    return df

def download_csv(spreadsheet_id: str, gid: str) -> Optional[pd.DataFrame]:
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        # Força UTF-8 para evitar caracteres corrompidos
        response.encoding = "utf-8"
        df = pd.read_csv(io.StringIO(response.text), dtype=str)
        
        # Limpeza agressiva e normalização Unicode usando .loc para evitar avisos
        for col in df.columns:
            if df[col].dtype == "object":
                df.loc[:, col] = df[col].astype(str).str.normalize("NFKC").str.strip()
        
        return normalize_columns(df)
    except Exception as e:
        logger.error(f"Erro ao baixar GID {gid}: {e}")
        return None

def drop_cols_safe(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    return df.drop(columns=[c for c in cols if c in df.columns], errors="ignore")

def process_projeto_fato(df: pd.DataFrame) -> pd.DataFrame:
    """Garante a criação da coluna PROJETO_FATO de forma segura."""
    if "PROJETO" in df.columns:
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].astype(str).apply(
            lambda x: str(x).split("-")[-1].strip() if "-" in str(x) else str(x).strip()
        ).apply(lambda x: str(x).zfill(7) if x not in ["", "nan", "None"] else "0000000")
    else:
        # Se não houver coluna projeto, cria uma padrão para evitar KeyError
        df.loc[:, "PROJETO_FATO"] = "0000000"
    return df

def search_header_and_normalize(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Busca dinâmica de cabeçalho e registra linhas puladas na auditoria."""
    if not df.empty:
        for i in range(min(15, len(df))):
            row = df.iloc[i].astype(str).str.upper().tolist()
            if "CRITERIO" in row or "STATUS" in row:
                # Registra as linhas que ficaram para trás como "Lixo de Cabeçalho"
                if i > 0:
                    registrar_descarte(f"Lixo de Cabeçalho/Metadados ({label})", i)
                
                # A linha i vira o cabeçalho, os dados começam em i+1
                df.columns = df.iloc[i].astype(str).str.strip()
                df = normalize_columns(df[i+1:].copy().reset_index(drop=True))
                # Registra a própria linha do cabeçalho como processada (não-dado)
                registrar_descarte(f"Linha de Título/Header ({label})", 1)
                return df
    return df

def transform_mes_padrao(df: pd.DataFrame, label: str, date: str, rename_map: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """Função base de transformação para reduzir repetição de código."""
    # Garante índice limpo desde o início
    df = df.copy().reset_index(drop=True)
    
    # Busca dinâmica de cabeçalho se necessário
    if not df.empty and ("STATUS" not in df.columns and "CRITERIO" not in df.columns):
        df = search_header_and_normalize(df, label)

    if rename_map:
        df = df.rename(columns=rename_map)
    
    # Remove colunas duplicadas após rename para evitar erros no concat final
    df = df.loc[:, ~df.columns.duplicated()].copy()
    
    df.loc[:, "COORD"], df.loc[:, "Carteira"] = "JACOBINA", date
    df = apply_status_filter(df, label)
    df = process_projeto_fato(df)
    
    # Auditoria de Projetos Inválidos
    mask_invalido = (df["PROJETO_FATO"] == "0000000") | df["PROJETO_FATO"].isna()
    return drop_cols_safe(apply_audit(df, label, mask_invalido, "Projeto Vazio/Inválido"), ["PROJETO"])

# --- Funções de Transformação Específicas por Mês ---

RENAME_MAP_2025 = {
    "CRITERIO": "CRITÉRIO", "STATUS": "STATUS 1", "CLIENTES": "CLIET.", 
    "PREVISTOS": "PSTP", "REALIZADO": "PST EXEC", "INCIO ": "PV. INÍCIO", 
    "FIM": "PV. FIM", "DATA ENERG REAL": "ENERGIZAÇÃO", "AVNP": "AVANÇO", 
    "VALOR DE PROJETO": "V. PROJETO"
}

def transform_janeiro_25(df: pd.DataFrame) -> pd.DataFrame:
    label, date = "Janeiro 25", "01/01/2025"
    df = df.copy().reset_index(drop=True)
    
    # Busca dinâmica de cabeçalho lida com os múltiplos 'PromoteHeaders'
    df = search_header_and_normalize(df, label)
    
    df = df.rename(columns=RENAME_MAP_2025)
    df = df.loc[:, ~df.columns.duplicated()].copy()
    
    df.loc[:, "COORD"], df.loc[:, "Carteira"] = "JACOBINA", date
    df = apply_status_filter(df, label)
    
    if "PROJETO" in df.columns:
        # Lógica Fiel ao Power Query: Text.AfterDelimiter(_, "-")
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].astype(str).apply(
            lambda x: str(x).split("-")[-1].strip() if "-" in str(x) else ""
        )
        
        # Filtro Power Query: [PROJETO] <> ""
        mask_vazio = (df["PROJETO_FATO"] == "") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_vazio, "Projeto Vazio ou sem sufixo '-' (Filtro PQ Janeiro)")
        
        # Normalização dos válidos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if x != "" else "0000000"
        )
    else:
        df.loc[:, "PROJETO_FATO"] = "0000000"
        
    return drop_cols_safe(df, ["PROJETO"])

def transform_fevereiro_25(df: pd.DataFrame) -> pd.DataFrame:
    return transform_mes_padrao(df, "Fevereiro 25", "01/02/2025", RENAME_MAP_2025)

def transform_marco_25(df: pd.DataFrame) -> pd.DataFrame:
    return transform_mes_padrao(df, "Março 25", "01/03/2025", RENAME_MAP_2025)

def transform_abril_25(df: pd.DataFrame) -> pd.DataFrame:
    return transform_mes_padrao(df, "Abril 25", "01/04/2025", RENAME_MAP_2025)

def transform_maio_25(df: pd.DataFrame) -> pd.DataFrame:
    return transform_mes_padrao(df, "Maio 25", "01/05/2025", RENAME_MAP_2025)

def transform_junho_25(df: pd.DataFrame) -> pd.DataFrame:
    return transform_mes_padrao(df, "Junho 25", "01/06/2025", RENAME_MAP_2025)

def transform_julho_25(df: pd.DataFrame) -> pd.DataFrame:
    return transform_mes_padrao(df, "Julho 25", "01/07/2025", RENAME_MAP_2025)

def transform_agosto_25(df: pd.DataFrame) -> pd.DataFrame:
    label, date = "Agosto 25", "01/08/2025"
    df = df.copy().reset_index(drop=True)
    
    # Busca dinâmica de cabeçalho lida com os múltiplos 'PromoteHeaders' e 'Skip' do PQ
    df = search_header_and_normalize(df, label)
    
    df = df.rename(columns=RENAME_MAP_2025)
    df = df.loc[:, ~df.columns.duplicated()].copy()
    
    df.loc[:, "COORD"], df.loc[:, "Carteira"] = "JACOBINA", date
    df = apply_status_filter(df, label)
    
    if "PROJETO" in df.columns:
        # Lógica Fiel ao Power Query: Text.AfterDelimiter(_, "-")
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].astype(str).apply(
            lambda x: str(x).split("-")[-1].strip() if "-" in str(x) else ""
        )
        
        # Filtro Power Query: [PROJETO] <> ""
        mask_vazio = (df["PROJETO_FATO"] == "") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_vazio, "Projeto Vazio ou sem sufixo '-' (Filtro PQ Agosto)")
        
        # Normalização dos válidos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if x != "" else "0000000"
        )
    else:
        df.loc[:, "PROJETO_FATO"] = "0000000"
        
    return drop_cols_safe(df, ["PROJETO"])

def transform_setembro_25(df: pd.DataFrame) -> pd.DataFrame:
    label, date = "Setembro 25", "01/09/2025"
    df = df.copy().reset_index(drop=True)
    
    # A busca dinâmica de cabeçalho lida com os múltiplos 'PromoteHeaders' e 'Skip' do PQ
    df = search_header_and_normalize(df, label)
    
    rename = {
        "CRITERIO": "CRITÉRIO", "STATUS": "STATUS 1", "CLIENTES": "CLIET.", 
        "PREVISTOS": "PSTP", "REALIZADO": "PST EXEC", "INCIO ": "PV. INÍCIO", 
        "FIM": "PV. FIM", "AVNP": "AVANÇO"
    }
    df = df.rename(columns=rename)
    df = df.loc[:, ~df.columns.duplicated()].copy()
    
    df.loc[:, "COORD"], df.loc[:, "Carteira"] = "JACOBINA", date
    df = apply_status_filter(df, label)
    
    if "PROJETO" in df.columns:
        # Lógica Fiel ao Power Query: Text.AfterDelimiter(_, "-") 
        # Em M, se o delimitador não existe, o padrão é retornar vazio ou erro dependendo do contexto.
        # O filtro posterior [PROJETO] <> "" confirma que apenas os que têm o sufixo interessam.
        df.loc[:, "PROJETO_FATO"] = df["PROJETO"].astype(str).apply(
            lambda x: str(x).split("-")[-1].strip() if "-" in str(x) else ""
        )
        
        # Filtro Power Query: [PROJETO] <> "" (SelectRows)
        mask_vazio = (df["PROJETO_FATO"] == "") | (df["PROJETO_FATO"].isna())
        df = apply_audit(df, label, mask_vazio, "Projeto Vazio ou sem sufixo '-' (Filtro PQ)")
        
        # Normalização dos válidos
        df.loc[:, "PROJETO_FATO"] = df["PROJETO_FATO"].apply(
            lambda x: str(x).zfill(7) if x != "" else "0000000"
        )
    else:
        df.loc[:, "PROJETO_FATO"] = "0000000"
        
    return drop_cols_safe(df, ["PROJETO"])

def transform_outubro_25(df: pd.DataFrame) -> pd.DataFrame:
    rename = RENAME_MAP_2025.copy()
    rename.update({"MUNICÍPIO": "MUNICIPIO"})
    rename.pop("VALOR DE PROJETO", None)
    rename.pop("DATA ENERG REAL", None)
    return transform_mes_padrao(df, "Outubro 25", "01/10/2025", rename)

def transform_novembro_25(df: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "CRITERIO": "CRITÉRIO", "STATUS": "STATUS 1", "CLIENTES": "CLIET.", 
        "PREVISTOS": "PSTP", "REALIZADO": "PST EXEC", "INCIO PREVISTO": "PV. INÍCIO", 
        "FIM PREVISTO": "PV. FIM", "AVNP": "AVANÇO"
    }
    return transform_mes_padrao(df, "Novembro 25", "01/11/2025", rename)

def transform_dezembro_25(df: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "STATUS": "STATUS 1", "CLIENTES": "CLIET.", "PREVISTOS": "PSTP", 
        "REALIZADO": "PST EXEC", "DT I PROG": "PV. INÍCIO", "DT F PROG": "PV. FIM", 
        "AR": "AR COELBA"
    }
    df_proc = transform_mes_padrao(df, "Dezembro 25", "01/12/2025", rename)
    for col in ["LATITUDE", "LONGITUDE"]:
        if col in df_proc.columns: df_proc.loc[:, col] = df_proc[col].astype(str).str.strip()
    return df_proc

def transform_janeiro_26(df: pd.DataFrame) -> pd.DataFrame:
    label, date = "Janeiro 26", "01/01/2026"
    if "PSTP" in df.columns: df = df.drop(columns=["PSTP"])
    rename = {
        "STATUS": "STATUS 1", "CLIENTES": "CLIET.", "PREVISTOS": "PSTP", 
        "REALIZADO": "PST EXEC", "DT I PROG": "PV. INÍCIO", "DT F PROG": "PV. FIM", 
        "AR": "AR COELBA"
    }
    df_proc = transform_mes_padrao(df, label, date, rename)
    for col in ["LATITUDE", "LONGITUDE"]:
        if col in df_proc.columns: df_proc.loc[:, col] = df_proc[col].astype(str).str.strip()
    return df_proc

def transform_fevereiro_26(df: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "STATUS": "STATUS 1", "CLIENTES": "CLIET.", "PREVISTOS": "PSTP", 
        "REALIZADO": "PST EXEC", "DT I PROG": "PV. INÍCIO", "DT F PROG": "PV. FIM", 
        "AR": "AR COELBA"
    }
    df_proc = transform_mes_padrao(df, "Fevereiro 26", "01/02/2026", rename)
    for col in ["LATITUDE", "LONGITUDE"]:
        if col in df_proc.columns: df_proc.loc[:, col] = df_proc[col].astype(str).str.strip()
    return df_proc

# --- Orquestração Final ---

def apply_final_business_rules(df: pd.DataFrame) -> pd.DataFrame:
    final_df = df.loc[:, ~df.columns.duplicated()].copy()
    
    # Validação Final de Projetos para Auditoria (Garante que o balanço bata)
    if "PROJETO_FATO" in final_df.columns:
        mask_invalido = final_df["PROJETO_FATO"].astype(str).str.strip() == "0000000"
        if mask_invalido.any():
            final_df = apply_audit(final_df, "Limpeza Final Jacobina", mask_invalido, "Projeto Inválido (Zeroed)")
            
    if "Carteira" in final_df.columns:
        final_df.loc[:, "Carteira"] = pd.to_datetime(final_df["Carteira"], errors="coerce").dt.strftime("%d/%m/%Y")
        
    cols_priority = ["PROJETO_FATO", "Carteira", "COORD"]
    return final_df[cols_priority + [c for c in final_df.columns if c not in cols_priority]]

def main() -> None:
    global total_bruto_processado
    logger.info("=== Pipeline ETL: Carteira Jacobina Iniciado ===")
    for d in [RAW_DIR, PROCESSED_DIR, AUDIT_DIR]: d.mkdir(parents=True, exist_ok=True)

    config: List[Tuple[Callable, str, str, str]] = [
        (transform_janeiro_25, SPREADSHEET_ID_MAIN, "272386891", "Janeiro 25"),
        (transform_fevereiro_25, SPREADSHEET_ID_MAIN, "2104757113", "Fevereiro 25"),
        (transform_marco_25, SPREADSHEET_ID_MAIN, "1809527246", "Março 25"),
        (transform_abril_25, SPREADSHEET_ID_ABR_SET, "71593441", "Abril 25"),
        (transform_maio_25, SPREADSHEET_ID_ABR_SET, "1258452865", "Maio 25"),
        (transform_junho_25, SPREADSHEET_ID_ABR_SET, "2083299855", "Junho 25"),
        (transform_julho_25, SPREADSHEET_ID_ABR_SET, "986873351", "Julho 25"),
        (transform_agosto_25, SPREADSHEET_ID_ABR_SET, "761036313", "Agosto 25"),
        (transform_setembro_25, SPREADSHEET_ID_ABR_SET, "233663434", "Setembro 25"),
        (transform_outubro_25, SPREADSHEET_ID_ABR_SET, "509954415", "Outubro 25"),
        (transform_novembro_25, SPREADSHEET_ID_ABR_SET, "495252520", "Novembro 25"),
        (transform_dezembro_25, SPREADSHEET_ID_ABR_SET, "837084913", "Dezembro 25"),
        (transform_janeiro_26, SPREADSHEET_ID_ABR_SET, "814368214", "Janeiro 26"),
        (transform_fevereiro_26, SPREADSHEET_ID_ABR_SET, "1940386946", "Fevereiro 26"),
    ]

    all_dfs_raw, all_dfs_proc = [], []
    for func, sid, gid, label in config:
        logger.info(f"Extraindo: {label}")
        df = download_csv(sid, gid)
        if df is not None:
            total_bruto_processado += len(df)
            df_tag = df.copy(); df_tag.loc[:, "ORIGEM_ETL"] = label; all_dfs_raw.append(df_tag)
            try: all_dfs_proc.append(func(df))
            except Exception as e: logger.error(f"Erro em {label}: {e}", exc_info=True)

    if all_dfs_raw: pd.concat(all_dfs_raw, ignore_index=True).to_csv(RAW_FILE, index=False, sep=";", encoding="utf-8-sig")
    if all_dfs_proc:
        final_df = apply_final_business_rules(pd.concat(all_dfs_proc, ignore_index=True))
        final_df.to_csv(OUTPUT_FILE, index=False, sep=";", encoding="utf-8-sig")
        
        total_descartado = sum(stats_descarte.values())
        
        logger.info("=== BALANÇO FINAL DO PROCESSAMENTO (JACOBINA) ===")
        logger.info(f"Total Bruto Extraído:  {total_bruto_processado}")
        logger.info(f"Total de Consolidados: {len(final_df)}")
        logger.info(f"Total de Descartados:  {total_descartado}")
        
        if stats_descarte:
            logger.info("--- Detalhamento de Descartes por Motivo/Mês ---")
            # Ordena por mês para facilitar a leitura
            for motivo_rotulo, qtd in sorted(stats_descarte.items()):
                logger.info(f"  - {motivo_rotulo}: {qtd} linhas")
        logger.info("==================================================")

if __name__ == "__main__":
    main()

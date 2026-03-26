import logging
import re
from pathlib import Path
from typing import List, Optional

import pandas as pd
import numpy as np

# --- Configuração de Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Configurações & Caminhos ---
MODULE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = MODULE_ROOT.parent.parent
CARTEIRA_ROOT = MODULE_ROOT.parent

# Arquivos Regionais (Entrada)
INPUT_FILES = [
    CARTEIRA_ROOT / "bonfim" / "data" / "processed" / "carteira_bonfim_consolidada.csv",
    CARTEIRA_ROOT / "jacobina" / "data" / "processed" / "carteira_jacobina_consolidada.csv",
    CARTEIRA_ROOT / "juazeiro" / "data" / "processed" / "carteira_juazeiro_consolidada.csv",
]

# Tabelas Auxiliares para Joins
PATH_PEDIDOS = PROJECT_ROOT / "pedidos_obra" / "data" / "processed" / "pedidos_consolidados.csv"
PATH_FECHAMENTO = PROJECT_ROOT / "faturamento_comercial" / "data" / "processed" / "faturamentos_tratados.csv"

OUTPUT_FILE = MODULE_ROOT / "data" / "processed" / "carteira_fato_consolidada.csv"

def safe_to_numeric(series: pd.Series) -> pd.Series:
    """Converte série para numérico tratando erros e nulos."""
    return pd.to_numeric(series.astype(str).str.replace(",", "."), errors="coerce").fillna(0)

def safe_to_datetime(series: pd.Series) -> pd.Series:
    """Converte série para datetime tratando formatos brasileiros."""
    return pd.to_datetime(series, errors="coerce", dayfirst=True)

def apply_power_query_logic(df: pd.DataFrame) -> pd.DataFrame:
    """Implementa a lógica do Editor Avançado do Power Query em Pandas."""
    
    logger.info("Iniciando transformações do Power Query...")
    fdf = df.copy()

    # 1. Remoção de colunas vazias
    cols_to_drop = [" ", ""]
    fdf = fdf.drop(columns=[c for c in cols_to_drop if c in fdf.columns])

    # 2. Conversão de Tipos e Limpezas Iniciais (Usando .loc para evitar warnings)
    fdf.loc[:, "V. PROJETO"] = safe_to_numeric(fdf.get("V. PROJETO", 0))
    fdf.loc[:, "PV. FIM"] = safe_to_datetime(fdf.get("PV. FIM"))
    fdf.loc[:, "PV. INÍCIO"] = safe_to_datetime(fdf.get("PV. INÍCIO"))
    fdf.loc[:, "Carteira"] = safe_to_datetime(fdf.get("Carteira"))
    fdf.loc[:, "ENERGIZAÇÃO"] = safe_to_datetime(fdf.get("ENERGIZAÇÃO"))
    
    # 3. Correção PST EXEC
    if "PST EXEC" in fdf.columns:
        fdf.loc[:, "PST EXEC"] = fdf["PST EXEC"].astype(str).str.upper().replace(["RETIRAR", "MANTER", "NAN"], "0")
        fdf.loc[:, "PST EXEC"] = safe_to_numeric(fdf["PST EXEC"]).astype(int)
    
    if "PSTP" in fdf.columns:
        fdf.loc[:, "PSTP"] = safe_to_numeric(fdf["PSTP"]).astype(int)

    # 4. Fim do Mês Calculado
    fdf.loc[:, "Carteira"] = fdf["Carteira"] + pd.offsets.MonthEnd(0)

    # 5. Filtro PROJETO_FATO <> "0"
    if "PROJETO_FATO" in fdf.columns:
        fdf = fdf[fdf["PROJETO_FATO"].astype(str).str.strip() != "0"].copy()

    # 6. Joins com Tabelas Auxiliares
    # Join dPedidos (Mapeado com base no cabeçalho real)
    if PATH_PEDIDOS.exists():
        logger.info("Realizando Join com dPedidos...")
        df_pedidos = pd.read_csv(PATH_PEDIDOS, sep=";", encoding="utf-8-sig", dtype=str)
        # Mapeamento: PEP -> PROJETO_FATO, VALOR_LIQUIDO -> FATURAMENTO
        df_pedidos = df_pedidos[["PEP", "DATA_DOC", "VALOR_LIQUIDO", "RESPONSAVEL"]].rename(columns={
            "PEP": "PEP_JOIN",
            "DATA_DOC": "DATA FATURAMENTO",
            "VALOR_LIQUIDO": "FATURAMENTO",
            "RESPONSAVEL": "RESPONSAVEL"
        }).drop_duplicates("PEP_JOIN")
        fdf = fdf.merge(df_pedidos, left_on="PROJETO_FATO", right_on="PEP_JOIN", how="left")
        fdf = fdf.drop(columns=["PEP_JOIN"])
    else:
        logger.warning("Base dPedidos não encontrada para Join.")

    # Join fFechamento (Power Query: Table.NestedJoin ... fFechamento)
    if PATH_FECHAMENTO.exists():
        logger.info("Realizando Join com fFechamento...")
        df_fech = pd.read_csv(PATH_FECHAMENTO, sep=";", encoding="utf-8-sig", dtype=str)
        # PQ expande "VALOR Á FATURAR LM" -> "VALOR PRODUZIDO"
        if "PROJETO_FATO" in df_fech.columns:
            df_fech = df_fech[["PROJETO_FATO", "VALOR Á FATURAR LM"]].rename(columns={"VALOR Á FATURAR LM": "VALOR PRODUZIDO"})
            df_fech = df_fech.drop_duplicates("PROJETO_FATO")
            fdf = fdf.merge(df_fech, on="PROJETO_FATO", how="left")
    else:
        logger.warning("Base fFechamento não encontrada para Join.")

    # 7. Lógica de Colunas _FATO (Comparativos e Max)
    # Simulando colunas .1 do PQ (caso existissem do join fCarteira)
    # Como não temos fCarteira aqui, vamos garantir que as colunas base existam
    for col in ["PSTP.1", "PSTR", "AVNP.1", "AVNR.1", "PLANO.1", "PV. INÍCIO.1", "PV. FIM.1", "DT. ENGZ"]:
        if col not in fdf.columns: 
            fdf.loc[:, col] = np.nan

    # Fillna(0) para colunas de cálculo
    calc_cols = ["PSTP", "PSTP.1", "PST EXEC", "PSTR", "AVNP", "AVNP.1", "AVNR", "AVNR.1"]
    for c in calc_cols:
        if c in fdf.columns: 
            fdf.loc[:, c] = safe_to_numeric(fdf[c])

    fdf.loc[:, "PSTP_FATO"] = np.where(fdf["PSTP"] < fdf["PSTP.1"], fdf["PSTP.1"], fdf["PSTP"])
    fdf.loc[:, "PSTE_FATO"] = np.where(fdf["PST EXEC"] < fdf["PSTR"], fdf["PSTR"], fdf["PST EXEC"])
    
    fdf.loc[:, "AVNR_corrigido"] = np.where(fdf["AVNR"] > 1, 1, fdf["AVNR"])
    fdf.loc[:, "AVNP_FATO"] = np.where(fdf["AVNP"] <= fdf["AVNP.1"], fdf["AVNP.1"], fdf["AVNP"])
    fdf.loc[:, "AVNR_FATO"] = np.where(fdf["AVNR_corrigido"] < fdf["AVNR.1"], fdf["AVNR.1"], fdf["AVNR_corrigido"])
    
    fdf.loc[:, "PLANO_FATO"] = fdf["PLANO.1"].fillna(fdf.get("PLANO", "NÃO DEFINIDO"))
    fdf.loc[:, "PV. INICIO_FATO"] = fdf["PV. INÍCIO"].fillna(fdf["PV. INÍCIO.1"]).infer_objects(copy=False)
    fdf.loc[:, "PV. FINAL_FATO"] = fdf["PV. FIM"].fillna(fdf["PV. FIM.1"]).infer_objects(copy=False)
    fdf.loc[:, "DT. ENERGIZACAO_FATO"] = fdf["ENERGIZAÇÃO"].fillna(fdf["DT. ENGZ"]).infer_objects(copy=False)

    # 8. Filtros de Status (Exclusão de Canceladas e Retiradas)
    logger.info("Aplicando filtros de exclusão de Status...")
    
    # Filtro Progressivo (Power Query: many SelectRows)
    if "STATUS" in fdf.columns:
        fdf.loc[:, "STATUS_UPPER"] = fdf["STATUS"].astype(str).str.upper().str.strip()
        
        # Filtros Exatos e StartsWith
        exclude_starts = ["CANCELADA", "RETIRADA", "RETIRADDA"]
        exclude_exact = [
            "OBRA CANCELADA, JÁ ATENDIDA PELO PROJETO Y-0707543",
            "OBRA DIRECIOANDA PARA A DINAMO", "PARALISADA", "PARALIZADA",
            "SIPEL BONFIM", "SUBST. PELA OBRA B-1077783",
            "CLIENTE SE ENCONTRA LIGADO NO MEDIDOR 1218743818",
            "EXECUTADA POR OUTRA EPS", "EXECUTAR PELA SIPEL BONFIM",
            "OBRA CANCELADA CONFORME E-MAIL 18/02/2025",
            "OBRA JÁ EXECUTADA PELA EQUIPE DE SENHOR DO BONFIM",
            "OBRA JÁ EXECUTADA PELO PROJETO B1156370",
            "SAIU DA CARTEIRA DE FEVEREIRO"
        ]
        
        mask_exclude = fdf["STATUS_UPPER"].apply(
            lambda x: any(x.startswith(s) for s in exclude_starts) or x in exclude_exact
        )
        fdf = fdf[~mask_exclude].copy()
        
        # Linhas Filtradas2 (CANC, AGEIS, AGIL, RETIR)
        mask_filter2 = fdf["STATUS_UPPER"].str.contains("CANC|AGEIS|AGIL|RETIR", na=False)
        fdf = fdf[~mask_filter2].copy()
        
        fdf = fdf.drop(columns=["STATUS_UPPER"])

    # 9. Colunas de Tempo e Subtipo
    if "PV. INICIO_FATO" in fdf.columns:
        fdf.loc[:, "PV. INICIO_FATO"] = pd.to_datetime(fdf["PV. INICIO_FATO"])
        fdf.loc[:, "SEMANA PV.INICIO"] = fdf["PV. INICIO_FATO"].dt.day.map(lambda d: (d-1)//7 + 1 if pd.notna(d) else 0)
        
    if "PV. FINAL_FATO" in fdf.columns:
        fdf.loc[:, "PV. FINAL_FATO"] = pd.to_datetime(fdf["PV. FINAL_FATO"])
        fdf.loc[:, "SEMANA PV.FIM"] = fdf["PV. FINAL_FATO"].dt.day.map(lambda d: (d-1)//7 + 1 if pd.notna(d) else 0)

    if "TÍTULO" in fdf.columns:
        fdf.loc[:, "SUBTIPO OBRA"] = fdf["TÍTULO"].astype(str).str[:2]

    # 10. Limpeza Final e Índice
    cols_to_remove = [
        "V. PROJETO", "REFERÊNCIA", "CAVA REALIZADA", "ENERGIZAÇÃO", "PSTP.1", 
        "PSTR", "AVNP.1", "AVNR.1", "PLANO.1", "DT. ENGZ", "PV. INÍCIO", 
        "PV. FIM", "PV. INÍCIO.1", "PV. FIM.1", "AVNR_corrigido"
    ]
    fdf = fdf.drop(columns=[c for c in cols_to_drop if c in fdf.columns])
    fdf = fdf.drop(columns=[c for c in cols_to_remove if c in fdf.columns])
    
    # Índice
    fdf.insert(0, "Índice", range(1, len(fdf) + 1))
    
    return fdf

def main() -> None:
    logger.info("=== ETL FATO: Consolidação com Lógica Power Query ===")
    
    try:
        all_dfs = []
        for file in INPUT_FILES:
            if file.exists():
                logger.info(f"Lendo {file.name}")
                all_dfs.append(pd.read_csv(file, sep=";", encoding="utf-8-sig", dtype=str))
        
        if not all_dfs:
            logger.error("Nenhum dado de entrada encontrado.")
            return

        df_bruto = pd.concat(all_dfs, ignore_index=True)
        
        # Aplicar toda a lógica do Power Query
        df_final = apply_power_query_logic(df_bruto)
        
        # Garantir diretório e salvar
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        df_final.to_csv(OUTPUT_FILE, index=False, sep=";", encoding="utf-8-sig")
        
        logger.info(f"Sucesso! Base consolidada com {len(df_final)} registros.")
        logger.info(f"Arquivo salvo: {OUTPUT_FILE}")

    except Exception as e:
        logger.error(f"Erro no processamento: {e}", exc_info=True)

if __name__ == "__main__":
    main()

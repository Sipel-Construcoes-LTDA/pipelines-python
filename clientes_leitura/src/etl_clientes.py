import os
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict

# Configuração de Logging Profissional
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configurações de Mapeamento
# O dicionário mapeia o nome Final (modelo) para os possíveis nomes encontrados nas planilhas
COLUMN_MAPPING_VARIANTS = {
    "instalacao": ["Instal", "Instalação", "instalacao"],
    "conta_contrato": ["Cta.contr.", "Conta Contrato", "conta_contrato"],
    "numero_serie": ["Nº Serie", "Nº Série", "numero_serie"],
    "numero_poste": ["Nº Poste", "numero_poste"],
    "nome_cliente": ["NomeCliente", "Nome Cliente", "nome_cliente"],
    "latitude": ["Latitude localiz.geográfica", "         Latitude", "latitude"],
    "longitude": ["Longitude localiz.geográfica", "        Longitude", "longitude"]
}

def identify_and_rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identifica as colunas baseando-se em variantes conhecidas e padroniza para o modelo.
    """
    rename_map = {}
    
    # Limpa espaços em branco dos nomes das colunas (comum no arquivo DB JANEIRO 2026)
    df.columns = [str(c).strip() for c in df.columns]
    
    for target_name, variants in COLUMN_MAPPING_VARIANTS.items():
        # Limpa as variantes para comparação
        clean_variants = [v.strip() for v in variants]
        
        # Encontra qual coluna do DF atual corresponde à variante
        found = False
        for col in df.columns:
            if col in clean_variants:
                rename_map[col] = target_name
                found = True
                break
        
        if not found:
            logger.warning(f"Coluna correspondente a '{target_name}' não encontrada no arquivo.")

    return df.rename(columns=rename_map)

def process_files():
    """
    Lê todos os arquivos XLSX, padroniza e consolida.
    """
    data_dir = Path("clientes_leitura/data")
    processed_dir = data_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    # Lista todos os arquivos .xlsx ignorando arquivos temporários ou de saída
    xlsx_files = [f for f in data_dir.glob("*.xlsx") if not f.name.startswith("~$")]
    
    if not xlsx_files:
        logger.error("Nenhum arquivo .xlsx encontrado para processamento.")
        return

    all_dfs = []

    for file_path in xlsx_files:
        logger.info(f"Processando arquivo: {file_path.name}")
        try:
            # Lê o arquivo
            df = pd.read_excel(file_path)
            
            # Padroniza colunas
            df_standardized = identify_and_rename_columns(df)
            
            # Mantém apenas as colunas do modelo
            cols_to_keep = [c for c in COLUMN_MAPPING_VARIANTS.keys() if c in df_standardized.columns]
            df_final = df_standardized[cols_to_keep].copy()
            
            all_dfs.append(df_final)
            logger.info(f"  -> {len(df_final)} registros lidos.")
            
        except Exception as e:
            logger.error(f"  -> Erro ao processar {file_path.name}: {e}")

    if not all_dfs:
        return

    # Consolidar
    logger.info("Consolidando dados e removendo duplicatas...")
    df_consolidated = pd.concat(all_dfs, ignore_index=True)
    
    # --- TRATAMENTO DE TIPAGEM (REMOVER .0) ---
    cols_to_fix = ['instalacao', 'conta_contrato', 'numero_serie']
    for col in cols_to_fix:
        if col in df_consolidated.columns:
            logger.info(f"Formatando coluna {col} como inteiro...")
            # Converte para numérico (coerce transforma lixo em NaN) e depois para Int64 (suporta NaN e remove .0)
            df_consolidated[col] = pd.to_numeric(df_consolidated[col], errors='coerce').round().astype('Int64')

    # Remove duplicatas baseadas na coluna 'instalacao'
    initial_count = len(df_consolidated)
    df_consolidated.drop_duplicates(subset=['instalacao'], keep='first', inplace=True)
    final_count = len(df_consolidated)
    
    logger.info(f"Removidas {initial_count - final_count} duplicatas.")
    logger.info(f"Total final: {final_count} registros únicos.")

    # Salva o resultado
    output_path = processed_dir / "clientes_consolidados.csv"
    df_consolidated.to_csv(output_path, index=False, sep=',', encoding='utf-8')
    logger.info(f"Arquivo salvo com sucesso em: {output_path}")

if __name__ == "__main__":
    logger.info("=== Início do Pipeline de Clientes ===")
    process_files()
    logger.info("=== Fim do Pipeline ===")

import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict

# Configuração de Logging Profissional
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Configurações & Constantes ---
MODULE_ROOT = Path(__file__).resolve().parent.parent
COLUMN_MAPPING_VARIANTS: Dict[str, List[str]] = {
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
    df.columns = [str(c).strip() for c in df.columns]

    for target_name, variants in COLUMN_MAPPING_VARIANTS.items():
        clean_variants = [v.strip() for v in variants]
        found = False
        for col in df.columns:
            if col in clean_variants:
                rename_map[col] = target_name
                found = True
                break
        if not found:
            logger.warning(
                f"Coluna correspondente a '{target_name}' não encontrada.")

    return df.rename(columns=rename_map)


def process_files() -> None:
    """
    Lê todos os arquivos XLSX, padroniza e consolida.
    """
    data_dir = MODULE_ROOT / "data"
    processed_dir = data_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    xlsx_files = [f for f in data_dir.glob(
        "*.xlsx") if not f.name.startswith("~$")]

    if not xlsx_files:
        logger.error("Nenhum arquivo .xlsx encontrado para processamento.")
        return

    all_dfs: List[pd.DataFrame] = []

    for file_path in xlsx_files:
        logger.info(f"Processando arquivo: {file_path.name}")
        try:
            df = pd.read_excel(file_path)
            df_standardized = identify_and_rename_columns(df)

            cols_to_keep = [
                c for c in COLUMN_MAPPING_VARIANTS.keys() if c in df_standardized.columns]
            df_final = df_standardized[cols_to_keep].copy()

            all_dfs.append(df_final)
            logger.info(f"  -> {len(df_final)} registros lidos.")

        except Exception as e:
            logger.error(f"  -> Erro ao processar {file_path.name}: {e}")

    if not all_dfs:
        return

    logger.info("Consolidando dados e removendo duplicatas...")
    df_consolidated = pd.concat(all_dfs, ignore_index=True)

    cols_to_fix = ['instalacao', 'conta_contrato', 'numero_serie']
    for col in cols_to_fix:
        if col in df_consolidated.columns:
            logger.info(f"Formatando coluna {col} como inteiro...")
            df_consolidated[col] = pd.to_numeric(
                df_consolidated[col], errors='coerce').round().astype('Int64')

    initial_count = len(df_consolidated)
    df_consolidated.drop_duplicates(
        subset=['instalacao'], keep='first', inplace=True)
    final_count = len(df_consolidated)

    logger.info(f"Removidas {initial_count - final_count} duplicatas.")
    logger.info(f"Total final: {final_count} registros únicos.")

    output_path = processed_dir / "clientes_consolidados.csv"
    df_consolidated.to_csv(output_path, index=False, sep=',', encoding='utf-8')
    logger.info(f"Arquivo salvo com sucesso em: {output_path}")


if __name__ == "__main__":
    logger.info("=== Início do Pipeline de Clientes ===")
    process_files()
    logger.info("=== Fim do Pipeline ===")

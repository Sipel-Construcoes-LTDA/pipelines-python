import pandas as pd
import requests
import io
import re
import logging
import os
from typing import List, Optional, Any

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configurações & Constantes ---
SPREADSHEET_ID: str = "1RbdE7CPmHrV3Z-HsWHVY2UfWBD-SlBDmknCfI6V0BfA"
GIDS: List[str] = [
    "604361021", "1090094802", "85077049", "1927088907", "0",
    "563947352", "1410869809", "1540399676", "2071167239",
    "203226281", "516940634", "1296316494"
]
# O diretório de saída agora é relativo ao script, dentro de data/processed
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'processed')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'faturamentos_tratados.csv')


def clean_value(val: Any) -> Optional[str]:
    """
    Trata o valor individual da célula.
    """
    if pd.isna(val) or val == "":
        return None

    s_val = str(val).strip().upper()

    # Remover Prefixos (B-, X-, Y-, SOL, etc) e manter apenas dígitos
    digits_only = re.sub(r'\D', '', s_val)

    if not digits_only:
        return None

    # Normalizar para 7 caracteres (preencher com zeros à esquerda se necessário)
    final_val = digits_only.zfill(7)

    if len(final_val) > 7:
        return None

    return final_val


def fetch_and_process(gid: str) -> pd.DataFrame:
    """
    Busca os dados de uma GID específica, processa e retorna um DataFrame limpo.
    """
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"

    try:
        response = requests.get(url)
        response.raise_for_status()

        df = pd.read_csv(io.StringIO(response.text), header=1, dtype=str)

        if df.shape[1] < 2:
            return pd.DataFrame()

        raw_series = df.iloc[:, 1]
        cleaned_series = raw_series.apply(
            clean_value).dropna().drop_duplicates()

        count = len(cleaned_series)
        logger.info(f"GID {gid}: {count} registros encontrados.")

        if count == 0:
            return pd.DataFrame()

        ret_df = pd.DataFrame({'ID_EXTRAIDO': cleaned_series})
        return ret_df

    except Exception as e:
        logger.error(f"Erro ao processar GID {gid}: {e}")
        return pd.DataFrame()


def main() -> None:
    """
    Orquestra o pipeline de busca e tratamento dos dados de faturamento.
    """
    logger.info("Iniciando Pipeline de Tratamento de Faturamento...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_data: List[pd.DataFrame] = []

    for gid in GIDS:
        df_part = fetch_and_process(gid)
        if not df_part.empty:
            logger.info(
                f"GID {gid} -> Adicionando {len(df_part)} linhas ao dataset principal.")
            all_data.append(df_part)
        else:
            logger.info(f"GID {gid} -> DataFrame vazio.")

    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        initial_count = len(final_df)
        final_df = final_df.drop_duplicates()
        final_count = len(final_df)

        logger.info(
            f"Total Bruto: {initial_count} | Total Único: {final_count}")

        final_df.to_csv(OUTPUT_FILE, index=False)
        logger.info(f"ARQUIVO GERADO: {OUTPUT_FILE}")
    else:
        logger.error("ERRO CRÍTICO: Nenhum dado foi consolidado.")


if __name__ == "__main__":
    main()

import pandas as pd
import requests
import io
import re
import logging
from typing import Optional

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações do Projeto
SPREADSHEET_ID = "1RbdE7CPmHrV3Z-HsWHVY2UfWBD-SlBDmknCfI6V0BfA"
GIDS = [
    "604361021", "1090094802", "85077049", "1927088907", "0",
    "563947352", "1410869809", "1540399676", "2071167239",
    "203226281", "516940634", "1296316494"
]

def clean_value(val: any) -> Optional[str]:
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
    # Ex: "1234" -> "0001234"
    # Ex: "1234567" -> "1234567"
    final_val = digits_only.zfill(7)
    
    # Opcional: Se quiser garantir que não estourou 7 (ex: 8 digitos), pode truncar ou validar
    if len(final_val) > 7:
        # Se for maior que 7, vamos manter para análise ou retornar None?
        # O pedido foi "todos os valores extraidos tenham o total 7 caracteres"
        # Vamos assumir que se passar de 7 é erro, ou pegar os últimos 7?
        # Por segurança, vamos manter apenas se tiver exatamente 7 após o zfill.
        return None 
        
    return final_val

def fetch_and_process(gid: str) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        # dtype=str garante que zeros à esquerda não sejam perdidos na leitura
        df = pd.read_csv(io.StringIO(response.text), header=1, dtype=str)
        
        if df.shape[1] < 2:
            return pd.DataFrame()
            
        # Coluna B
        raw_series = df.iloc[:, 1]
        cleaned_series = raw_series.apply(clean_value).dropna().drop_duplicates()
        
        count = len(cleaned_series)
        logger.info(f"GID {gid}: {count} registros encontrados.")
        
        if count == 0:
             return pd.DataFrame()

        # Construtor explícito por dicionário
        ret_df = pd.DataFrame({'ID_EXTRAIDO': cleaned_series})
        return ret_df
        
    except Exception as e:
        logger.error(f"Erro ao processar GID {gid}: {e}")
        return pd.DataFrame()

def main():
    logger.info("Iniciando Pipeline de Tratamento (v2)...")
    
    all_data = []
    
    for gid in GIDS:
        df_part = fetch_and_process(gid)
        if not df_part.empty:
            logger.info(f"GID {gid} -> Adicionando {len(df_part)} linhas ao dataset principal.")
            all_data.append(df_part)
        else:
            logger.info(f"GID {gid} -> DataFrame vazio.")
            
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        initial_count = len(final_df)
        final_df = final_df.drop_duplicates()
        final_count = len(final_df)
        
        logger.info(f"Total Bruto: {initial_count} | Total Único: {final_count}")
        
        output_file = "faturamentos_tratados.csv"
        final_df.to_csv(output_file, index=False)
        logger.info(f"ARQUIVO GERADO: {output_file}")
    else:
        logger.error("ERRO CRÍTICO: Nenhum dado foi consolidado.")

if __name__ == "__main__":
    main()
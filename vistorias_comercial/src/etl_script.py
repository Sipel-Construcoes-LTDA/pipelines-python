import pandas as pd
import logging
import os
from datetime import datetime

# Configuração de Logging conforme PADROES_PROJETO.md
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações / Constantes
IDS_PLANILHAS = {
    "Bonfim": "1gNr558RS_DHwv8PjaSdwOvDI0mqlVVY3GEKFFXKsU5U",
    "Jacobina": "19OdT08BBNJqQwU4GNyYySNlpTj6p7UVW66xFYyd5B5I",
    "Juazeiro": "1Q9-OHTSZG7IRoZ2zocmLjv934_fTwOB7FhCFXbzECG0"
}

# GIDs identificados
GIDS = {
    "Bonfim": "1164135827",
    "Jacobina": "1906289711",
    "Juazeiro": "1923088500"
}

OUTPUT_PATH = "vistorias_comercial/data/processed/vistorias_consolidadas.csv"

def get_url(spreadsheet_id: str, gid: str) -> str:
    """Gera a URL de exportação CSV para o Google Sheets."""
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"

def safe_to_datetime(series: pd.Series) -> pd.Series:
    """Converte série para datetime com segurança para o formato brasileiro."""
    return pd.to_datetime(series, errors='coerce', dayfirst=True)

def clean_nota(df: pd.DataFrame) -> pd.DataFrame:
    """Garante que a coluna NOTA seja numérica e inteira, removendo inválidos."""
    if 'NOTA' not in df.columns:
        logger.warning("Coluna 'NOTA' não encontrada.")
        return df
    
    # Converte para numérico
    df.loc[:, 'NOTA'] = pd.to_numeric(df['NOTA'], errors='coerce')
    # Remove nulos e converte para int
    df = df.dropna(subset=['NOTA']).copy()
    df.loc[:, 'NOTA'] = df['NOTA'].astype(int)
    return df

def process_bonfim(spreadsheet_id: str, gid: str) -> pd.DataFrame:
    """Extrai e trata os dados de Senhor do Bonfim."""
    logger.info("Processando base: Bonfim")
    try:
        url = get_url(spreadsheet_id, gid)
        df = pd.read_csv(url)
        
        df = clean_nota(df)
        
        # Datas
        df.loc[:, 'PRAZO DA NOTA'] = safe_to_datetime(df.get('PRAZO DA NOTA'))
        df.loc[:, 'DATA DO CONTATO'] = safe_to_datetime(df.get('DATA DO CONTATO'))
        df.loc[:, 'DATA DO RETORNO'] = safe_to_datetime(df.get('DATA DO RETORNO'))
        
        # Renomeação
        df = df.rename(columns={
            'COLABORADOR': 'RESPONSAVEL',
            'STATUS': 'TEMP_STATUS',
            'CONFORMIDADE': 'STATUS'
        })
        df = df.rename(columns={'TEMP_STATUS': 'CONFORMIDADE'})
        
        df.loc[:, 'MUNICIPIO'] = 'SENHOR DO BONFIM'
        return df
    except Exception as e:
        logger.error(f"Erro ao processar Bonfim: {e}")
        return pd.DataFrame()

def process_jacobina(spreadsheet_id: str, gid: str) -> pd.DataFrame:
    """Extrai e trata os dados de Jacobina."""
    logger.info("Processando base: Jacobina")
    try:
        url = get_url(spreadsheet_id, gid)
        df = pd.read_csv(url)
        df = df.dropna(how='all')
        
        df = clean_nota(df)
        
        # Jacobina pode ter 'DATA CONTATO' ou 'DATA DO CONTATO'
        col_contato = 'DATA CONTATO' if 'DATA CONTATO' in df.columns else 'DATA DO CONTATO'
        col_retorno = 'DATA RETORNO' if 'DATA RETORNO' in df.columns else 'DATA DO RETORNO'
        
        df.loc[:, 'DATA DO CONTATO'] = safe_to_datetime(df.get(col_contato))
        df.loc[:, 'DATA DO RETORNO'] = safe_to_datetime(df.get(col_retorno))
        
        # Renomeação
        df = df.rename(columns={
            'LOCAL': 'MUNICIPIO',
            'STATUS': 'TEMP_STATUS',
            'CONFORMIDADE': 'STATUS'
        })
        df = df.rename(columns={'TEMP_STATUS': 'CONFORMIDADE'})
        
        return df
    except Exception as e:
        logger.error(f"Erro ao processar Jacobina: {e}")
        return pd.DataFrame()

def process_juazeiro(spreadsheet_id: str, gid: str) -> pd.DataFrame:
    """Extrai e trata os dados de Juazeiro."""
    logger.info("Processando base: Juazeiro")
    try:
        url = get_url(spreadsheet_id, gid)
        df = pd.read_csv(url)
        
        # Se não encontrar colunas esperadas, tenta pular a primeira linha
        if 'UTEP' not in df.columns and 'NOTA' not in df.columns:
            df = pd.read_csv(url, skiprows=1)

        # Mapeamento flexível para Juazeiro
        rename_map = {
            'UTEP': 'MUNICIPIO',
            'COLABORADOR': 'RESPONSAVEL',
            'DATA CONTATO': 'DATA DO CONTATO',
            'DATA RETORNO': 'DATA DO RETORNO',
            'RETORNO': 'CONFORMIDADE'
        }
        df = df.rename(columns=rename_map)
        
        df = clean_nota(df)
        
        df.loc[:, 'DATA DO CONTATO'] = safe_to_datetime(df.get('DATA DO CONTATO'))
        df.loc[:, 'DATA DO RETORNO'] = safe_to_datetime(df.get('DATA DO RETORNO'))
        
        return df
    except Exception as e:
        logger.error(f"Erro ao processar Juazeiro: {e}")
        return pd.DataFrame()

def main():
    logger.info("Iniciando Pipeline de Vistorias Comercial")
    
    df_bonfim = process_bonfim(IDS_PLANILHAS["Bonfim"], GIDS["Bonfim"])
    df_jacobina = process_jacobina(IDS_PLANILHAS["Jacobina"], GIDS["Jacobina"])
    df_juazeiro = process_juazeiro(IDS_PLANILHAS["Juazeiro"], GIDS["Juazeiro"])
    
    logger.info("Consolidando bases...")
    df_final = pd.concat([df_bonfim, df_jacobina, df_juazeiro], ignore_index=True)
    
    if df_final.empty:
        logger.error("Dataframe final vazio.")
        return

    colunas_finais = [
        'NOTA', 'DATA DO CONTATO', 'DATA DO RETORNO', 
        'MUNICIPIO', 'RESPONSAVEL', 'STATUS', 'CONFORMIDADE'
    ]
    
    for col in colunas_finais:
        if col not in df_final.columns:
            df_final.loc[:, col] = pd.NA
            
    df_final = df_final[colunas_finais].copy()
    
    # Limpeza final de datas
    df_final.loc[:, 'DATA DO CONTATO'] = pd.to_datetime(df_final['DATA DO CONTATO'], errors='coerce').dt.date
    df_final.loc[:, 'DATA DO RETORNO'] = pd.to_datetime(df_final['DATA DO RETORNO'], errors='coerce').dt.date
    
    # Remove sem data de contato
    df_final = df_final.dropna(subset=['DATA DO CONTATO'])
    
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df_final.to_csv(OUTPUT_PATH, index=False, sep=';', encoding='utf-8-sig')
    
    logger.info(f"Pipeline concluído! Salvo em: {OUTPUT_PATH}")
    logger.info(f"Total: {len(df_final)} vistorias.")

if __name__ == "__main__":
    main()

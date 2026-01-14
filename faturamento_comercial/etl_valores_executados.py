import pandas as pd
import os
import glob
import logging
import warnings
from typing import Optional, Dict

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress specific warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=UserWarning)

# Diretórios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VALORES_DIR = os.path.join(BASE_DIR, "valores_executados")
DIMENSOES_DIR = os.path.join(VALORES_DIR, "dimensões")
ZRM_DIR = os.path.join(VALORES_DIR, "ZRM")

def clean_text(text: any) -> str:
    if pd.isna(text):
        return ""
    return str(text).strip()

def find_header_row(file_path: str, encoding: str = 'utf-16') -> int:
    """Encontra a linha de cabeçalho baseada nas colunas esperadas."""
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            for i, line in enumerate(f):
                if "Nota" in line and "GrCoAt" in line:
                    return i
    except Exception as e:
        logger.warning(f"Erro ao ler linhas para encontrar header em {file_path}: {e}")
    return 0

def load_dim_ct() -> pd.DataFrame:
    path = os.path.join(DIMENSOES_DIR, "dim_Ct.xlsx")
    logger.info(f"Carregando dim_Ct de {path}")
    df = pd.read_excel(path)
    # Colunas esperadas: 'NOMECLATURA_BD_IW69', 'BASE OPERACIONAL'
    df = df[['NOMECLATURA_BD_IW69', 'BASE OPERACIONAL']].copy()
    df['NOMECLATURA_BD_IW69'] = df['NOMECLATURA_BD_IW69'].apply(clean_text)
    return df

def load_fato_zrm_map() -> pd.DataFrame:
    """
    Carrega fato_zrm e cria um mapa de Serv.R/3 (Clean) -> Chave composta (FK).
    """
    path = os.path.join(ZRM_DIR, "fato_zrm.xlsx")
    logger.info(f"Carregando fato_zrm de {path}")
    # Lê a sheet ' BASE ZRM'
    df = pd.read_excel(path, sheet_name=' BASE ZRM')
    
    # Lógica M:
    # Chave composta (FK) = Grp.Ação + Serv.CCS
    df['Grp.Ação'] = df['Grp.Ação'].fillna('').astype(str)
    df['Serv.CCS'] = df['Serv.CCS'].fillna('').astype(str)
    df['Chave composta (FK)'] = df['Grp.Ação'] + df['Serv.CCS']
    
    # Remove duplicatas pela chave composta (conforme M code)
    df = df.drop_duplicates(subset=['Chave composta (FK)'])
    
    # Limpa Serv.R/3
    df['Serv.R/3'] = df['Serv.R/3'].astype(str).str.strip()
    df['Limpar'] = df['Serv.R/3'].apply(clean_text) # Replicando Text.Clean(Text.Trim(...))
    
    # Retorna apenas colunas necessárias para o join
    return df[['Limpar', 'Chave composta (FK)']]

def load_dim_values(zrm_map: pd.DataFrame, year_label: str) -> pd.DataFrame:
    """
    Carrega valores de serviços (2024 ou 2025) e prepara tabela de lookup.
    """
    path = os.path.join(DIMENSOES_DIR, "dim_valor_servicos.xlsx")
    sheet_name = "Valores antigos" if year_label == "2024" else "Valores novos"
    
    logger.info(f"Carregando dim_valor_servicos ({sheet_name}) de {path}")
    df = pd.read_excel(path, sheet_name=sheet_name)
    
    # Limpeza
    df['COD PAGAMENTO'] = df['COD PAGAMENTO'].astype(str).str.strip()
    df['Limpar'] = df['COD PAGAMENTO'].apply(clean_text)
    
    # Join com ZRM
    # M code: NestedJoin na coluna 'Limpar'
    merged = pd.merge(df, zrm_map, on='Limpar', how='left')
    
    # FK_FINAL = BASE + BASE ZRM.Chave composta (FK)
    merged['BASE'] = merged['BASE'].fillna('').astype(str)
    merged['Chave composta (FK)'] = merged['Chave composta (FK)'].fillna('').astype(str)
    merged['FK_FINAL'] = merged['BASE'] + merged['Chave composta (FK)']
    
    # Filtro de bases
    bases_to_exclude = ["BONFIM", "JACOBINA", "JUAZEIRO", "REMANSO"]
    merged = merged[~merged['FK_FINAL'].isin(bases_to_exclude)]
    
    # Select cols and rename Value
    if 'Valor Total' not in merged.columns:
        # Tenta calcular ou achar a coluna
        if 'VALOR' in merged.columns and 'Fator K' in merged.columns:
             merged['Valor Total'] = merged['VALOR'] * merged['Fator K'] # Suposição, se não existir
    
    col_valor = f'Valor Total {year_label}'
    merged = merged.rename(columns={'Valor Total': col_valor})
    
    # Deduplicar por FK_FINAL para garantir 1:1 no join final
    # O M code faz distinct em FK_FINAL
    merged = merged.drop_duplicates(subset=['FK_FINAL'])
    
    return merged[['FK_FINAL', col_valor]]

def process_pipeline():
    # 1. Carregar Dimensões e Mapas
    dim_ct = load_dim_ct()
    zrm_map = load_fato_zrm_map()
    
    dim_val_2024 = load_dim_values(zrm_map, "2024")
    dim_val_2025 = load_dim_values(zrm_map, "2025")
    
    # 2. Encontrar e Processar Arquivos Mensais
    all_files = glob.glob(os.path.join(VALORES_DIR, "**", "*.XLS"), recursive=True)
    logger.info(f"Encontrados {len(all_files)} arquivos para processar.")
    
    dfs = []
    
    for file_path in all_files:
        try:
            # Pula arquivos que não são dados mensais (como os próprios arquivos de sistema se estiverem lá)
            filename = os.path.basename(file_path)
            if filename.lower().endswith('.xlsx'): continue # Ignora xlsx se pego pelo glob (case insensitive no windows) 
            
            # Detectar header
            header_row = find_header_row(file_path)
            
            # Ler arquivo 'fake XLS' (Tab delimited, UTF-16)
            # skiprows ignora as primeiras N linhas. Se header_row=6, ignoramos 0..5.
            df_temp = pd.read_csv(file_path, sep='\t', encoding='utf-16', skiprows=header_row)
            
            # Verificar se colunas essenciais existem
            # O arquivo tem coluna vazia no inicio geralmente
            if 'Unnamed: 0' in df_temp.columns:
                df_temp = df_temp.drop(columns=['Unnamed: 0'])
            
            # Normalizar colunas (strip whitespace)
            df_temp.columns = [c.strip() for c in df_temp.columns]
            
            required_cols = ['GrCoAt', 'CódA', 'CenTrabRes', 'Nota', 'Data'] # 'Fim avaria' etc.
            missing = [c for c in required_cols if c not in df_temp.columns]
            if missing:
                logger.warning(f"Arquivo {filename} ignorado. Colunas faltantes: {missing}")
                continue
                
            dfs.append(df_temp)
            
        except Exception as e:
            logger.error(f"Erro ao processar arquivo {file_path}: {e}")

    if not dfs:
        logger.error("Nenhum dado carregado.")
        return

    # 3. Combinar Fatos
    full_df = pd.concat(dfs, ignore_index=True)
    logger.info(f"Total de registros brutos: {len(full_df)}")
    
    # 4. Transformações
    # ChaveFK = GrCoAt + CódA
    full_df['GrCoAt'] = full_df['GrCoAt'].fillna('').astype(str).str.strip()
    full_df['CódA'] = full_df['CódA'].fillna('').astype(str).str.strip()
    full_df['ChaveFK'] = full_df['GrCoAt'] + full_df['CódA']
    
    # Join Dim CT
    full_df['CenTrabRes'] = full_df['CenTrabRes'].fillna('').astype(str).str.strip()
    full_df = pd.merge(full_df, dim_ct, left_on='CenTrabRes', right_on='NOMECLATURA_BD_IW69', how='left')
    
    # PK = BASE OPERACIONAL + ChaveFK
    full_df['BASE OPERACIONAL'] = full_df['BASE OPERACIONAL'].fillna('').astype(str).str.strip()
    full_df['PK'] = full_df['BASE OPERACIONAL'] + full_df['ChaveFK']
    
    # Join Valores 2024
    full_df = pd.merge(full_df, dim_val_2024, left_on='PK', right_on='FK_FINAL', how='left')
    
    # Join Valores 2025
    full_df = pd.merge(full_df, dim_val_2025, left_on='PK', right_on='FK_FINAL', how='left')
    
    # Seleção final e Agrupamento (Soma por Nota)
    # Definir colunas chave para a nota (removendo detalhes do item como GrCoAt e CódA)
    group_cols = ["Nota", "Data", "BASE OPERACIONAL"]
    if "Fim avaria" in full_df.columns:
        group_cols.append("Fim avaria")
    
    # Preencher NaNs com 0 para garantir soma correta
    cols_vals = ["Valor Total 2024", "Valor Total 2025"]
    for c in cols_vals:
        if c not in full_df.columns:
            full_df[c] = 0.0
        full_df[c] = full_df[c].fillna(0.0)

    # Agrupar e Somar
    final_df = full_df.groupby(group_cols, as_index=False)[cols_vals].sum()
    
    # Remover linhas onde ambos os valores são zero (antigos nulos)
    initial_len = len(final_df)
    final_df = final_df[~((final_df['Valor Total 2024'] == 0) & (final_df['Valor Total 2025'] == 0))]
    logger.info(f"Linhas removidas (valores zerados): {initial_len - len(final_df)}")
    
    # Output
    output_path = os.path.join(BASE_DIR, "faturamentos_executados_consolidado.csv")
    final_df.to_csv(output_path, index=False, sep=';', encoding='utf-8-sig', decimal=',') # CSV Excel friendly
    logger.info(f"Pipeline concluído. Arquivo salvo em: {output_path}")
    logger.info(f"Linhas finais: {len(final_df)}")

if __name__ == "__main__":
    process_pipeline()

import pandas as pd
import os
import glob
import re
import logging
from typing import List, Dict, Optional

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações de Diretório
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Diretórios de ano dentro de produtividade_comercial
YEAR_DIRS = ["2024", "2025", "2026"] 

def parse_filename(filename: str) -> dict:
    """
    Analisa o nome do arquivo para extrair mês, ano e se é 'Abertas'.
    Formatos esperados:
    - "1 2025 Abertas.XLS"
    - "1 2025.XLS"
    - "1.XLS" (assumir ano da pasta se não houver no nome)
    """
    basename = os.path.basename(filename)
    name_no_ext = os.path.splitext(basename)[0]
    
    # Verifica se é Abertas
    is_abertas = "abertas" in name_no_ext.lower()
    
    # Tenta extrair números
    # Padrão: inicio com digitos (mes), opcionalmente ano, opcionalmente texto
    parts = name_no_ext.split()
    
    month = 0
    year = 0
    
    try:
        if parts:
            month = int(parts[0])
            
        # Tenta achar o ano nos tokens seguintes
        for part in parts[1:]:
            if part.isdigit() and len(part) == 4:
                year = int(part)
                break
        
        # Se não achou ano no nome, tenta pegar do diretório pai
        if year == 0:
            parent_dir = os.path.basename(os.path.dirname(filename))
            if parent_dir.isdigit() and len(parent_dir) == 4:
                year = int(parent_dir)
                
    except Exception:
        pass
        
    return {
        "filepath": filename,
        "month": month,
        "year": year,
        "is_abertas": is_abertas,
        "sort_key": year * 100 + month # Ex: 202501 para ordenação
    }

def get_files_to_process() -> List[str]:
    """
    Seleciona todos os arquivos fechados e APENAS o arquivo 'Abertas' mais recente.
    """
    all_files = []
    for year_dir in YEAR_DIRS:
        path = os.path.join(BASE_DIR, year_dir, "*.XLS")
        all_files.extend(glob.glob(path))
    
    parsed_files = [parse_filename(f) for f in all_files]
    
    regular_files = [f for f in parsed_files if not f['is_abertas']]
    abertas_files = [f for f in parsed_files if f['is_abertas']]
    
    final_list = [f['filepath'] for f in regular_files]
    
    if abertas_files:
        # Ordena por ano/mes decrescente para pegar o ultimo
        abertas_files.sort(key=lambda x: x['sort_key'], reverse=True)
        latest_abertas = abertas_files[0]
        final_list.append(latest_abertas['filepath'])
        logger.info(f"Arquivo 'Abertas' selecionado: {os.path.basename(latest_abertas['filepath'])}")
    
    return final_list

def convert_custom_date(val):
    """
    Converte string para datetime.
    Suporta formatos: 'dd.mm.yyyy' (prioritário) e 'ddMMyyyy' (legado/numérico).
    Retorna NaT se falhar.
    """
    if pd.isna(val) or val == "":
        return pd.NaT
    
    s_val = str(val).strip()
    
    try:
        # Tenta formato com pontos: 24.12.2025
        if '.' in s_val:
            return pd.to_datetime(s_val, format='%d.%m.%Y', errors='coerce')
            
        # Tenta formato numérico colado: 01012025
        # Garante 8 digitos com zeros a esquerda
        s_val_clean = re.sub(r'\D', '', s_val).zfill(8) 
        if len(s_val_clean) == 8:
            return pd.to_datetime(s_val_clean, format='%d%m%Y', errors='coerce')
            
        return pd.NaT
    except:
        return pd.NaT

def read_file(filepath: str) -> pd.DataFrame:
    """
    Lê o arquivo .XLS (Texto Tabulado UTF-16).
    """
    try:
        # Pula as primeiras 3 linhas para pegar o cabeçalho na linha 4
        # engine='python' é mais robusto para separadores
        df = pd.read_csv(filepath, sep='\t', encoding='utf-16', skiprows=3, on_bad_lines='skip')
        
        # Limpeza básica de nomes de colunas (strip whitespace)
        df.columns = df.columns.str.strip()
        
        # Verifica se a coluna 'Nota' existe, se não, tentamos ler sem skip ou ajustando
        if 'Nota' not in df.columns:
            logger.warning(f"'Nota' não encontrada em {os.path.basename(filepath)}. Tentando autodetect...")
            # Tentativa de fallback seria ler com header=None e procurar a linha
            return pd.DataFrame()
            
        return df
    except Exception as e:
        logger.error(f"Erro ao ler {filepath}: {e}")
        return pd.DataFrame()

def transform_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica as regras de negócio.
    """
    if df.empty:
        return df

    # --- Tipagem Inicial e Conversão de Datas ---
    # Converte 'Nota' para numérico, forçando erros para NaN
    if 'Nota' in df.columns:
        df['Nota'] = pd.to_numeric(df['Nota'], errors='coerce')
    
    # Mapeamento colunas de data (Source -> Target)
    date_cols_map = {
        "InícioAvar": "Inicio da Nota",
        "Fim avaria": "Finalização da nota",
        "Concl.desj": "Conc. desejada",
        # "InícioAvar": "Criação da nota", # Repetido no M, mas lógica é a mesma
        "Encerram.": "Encerramento da nota"
    }
    
    # Criação das colunas de data
    for src, target in date_cols_map.items():
        if src in df.columns:
            df[target] = df[src].apply(convert_custom_date)
        else:
            df[target] = pd.NaT
            
    # Criação específica "Criação da nota" (cópia de InícioAvar)
    if "InícioAvar" in df.columns:
        df["Criação da nota"] = df["InícioAvar"].apply(convert_custom_date)
    else:
        df["Criação da nota"] = pd.NaT

    # --- Filtragem de Linhas Vazias ---
    # Remove linhas onde tudo é nulo ou string vazia
    # Simplificação: Remove se 'Nota' for nulo, pois é a chave principal
    df = df.dropna(subset=['Nota'])
    
    # --- Pedido Corrigido ---
    if "Nº do pedido" in df.columns:
        df["Nº do pedido"] = df["Nº do pedido"].fillna("Vazio")
    else:
        df["Nº do pedido"] = "Vazio"

    # --- Nota Vistoriada ---
    def check_vistoria(pedido):
        if pd.isna(pedido): return "Não vistoriada"
        p = str(pedido)
        if any(x in p for x in ["vv", "vv.", "v v"]) or p.startswith("VV"):
            return "Vistoriada"
        if p in ["Vazio", "NRD"]:
            return "Não vistoriada"
        return "Não vistoriada"

    df["Nota vistoriada"] = df["Nº do pedido"].apply(check_vistoria)

    # --- Renomear Série ---
    df.rename(columns={"Nr. Série Equip.": "Nr. Série"}, inplace=True)

    # --- Data Finalização Unificada ---
    # Prioriza "Finalização da nota", senão "Encerramento da nota"
    df["Data de Finalização"] = df["Finalização da nota"].fillna(df["Encerramento da nota"])

    # --- Remover Colunas Desnecessárias ---
    cols_to_remove = [
        "Concl.desj", "ContContr.", "Instalação", "Dt.criação", "H fim des.", "TensFornec", 
        "Code", "Data", "Hora", "Poste", "Grp.cod", "UnLeit.", "Ordenação", "TensMed", 
        "CNAE", "EqMedVizAn", "EqMedVizPo", "MedVizPos", "MedVizAnt", "Posto", 
        "InícioAvar", "Fim avaria", "HFimAvar", "Encerram.", "HEnc.", "Modif.em", 
        "Ordem", "C", "HInícAv.", "Centro cst", "Den.exec.", "Den.exec._1", 
        "Exec.por", "Execução", "P", "Rg", "Localiz.", "Cen.", "Bairro de", 
        "   DiasExec", "QtdHorExec", "Centro de Resultado", "Municípo", 
        "Nome do parceiro", " DiasExec", "  DiasExec", "TpPri", "Cliente", 
        "Texto breve", "Ctg.tar.", "NºEndereço", "Column14", "DiasExec"
    ]
    # Remove apenas as que existem
    existing_cols_remove = [c for c in cols_to_remove if c in df.columns]
    df.drop(columns=existing_cols_remove, inplace=True)

    # --- Duplicatas ---
    df.drop_duplicates(subset=["Nota"], inplace=True)

    # --- Tratamento Urbano/Rural ---
    if "Urbano/Rur" in df.columns:
        df["Urbano/Rur"] = df["Urbano/Rur"].fillna("Info.")
        df["Urbano/Rur"] = df["Urbano/Rur"].replace({"R": "Rural", "U": "Urbano"})
    
    # --- Ordenação ---
    df.sort_values(by="Nota", ascending=True, inplace=True)

    # --- Limpeza Final ---
    # Remove colunas 'Unnamed'
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # Converte Nota para Int
    df["Nota"] = df["Nota"].astype('int64')

    return df

def main():
    logger.info("Iniciando ETL Produtividade Comercial...")
    
    files = get_files_to_process()
    logger.info(f"{len(files)} arquivos identificados para processamento.")
    
    dfs = []
    for f in files:
        logger.info(f"Lendo: {os.path.basename(f)}")
        df_part = read_file(f)
        if not df_part.empty:
            dfs.append(df_part)
            
    if not dfs:
        logger.error("Nenhum dado lido.")
        return
        
    logger.info("Consolidando dados...")
    full_df = pd.concat(dfs, ignore_index=True)
    
    logger.info("Aplicando transformações...")
    final_df = transform_data(full_df)
    
    output_path = os.path.join(BASE_DIR, "produtividade_tratada.csv")
    final_df.to_csv(output_path, index=False, sep=';', encoding='utf-8-sig') # Separador ; para excel BR
    
    logger.info(f"Processo concluído. Arquivo gerado: {output_path}")
    logger.info(f"Total de registros: {len(final_df)}")

if __name__ == "__main__":
    main()

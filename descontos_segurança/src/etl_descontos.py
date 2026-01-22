import pandas as pd
import os
import logging
from thefuzz import process as fuzzy_process

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Constantes de Caminhos ---
BASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data')
INPUT_PATH = os.path.join(BASE_PATH, 'auxiliary')
OUTPUT_PATH = os.path.join(BASE_PATH, 'processed')
COLABORADORES_FILES = {
    'bonfim': os.path.join(INPUT_PATH, 'aux_colaboradores_bonfim.xlsx'),
    'jacobina': os.path.join(INPUT_PATH, 'aux_colaboradores_jacobina.xlsx'),
    'juazeiro': os.path.join(INPUT_PATH, 'aux_colaboradores_juazeiro.xlsx')
}
DESCONTOS_FILE = os.path.join(INPUT_PATH, 'aux_descontos.csv')
OUTPUT_FILE = os.path.join(OUTPUT_PATH, 'descontos_consolidados.csv')


def extract_and_clean_bonfim(file_path: str) -> pd.DataFrame:
    """Extrai e limpa os dados de colaboradores de Bonfim."""
    logging.info(f"Processando arquivo: {file_path}")
    df = pd.read_excel(file_path, sheet_name='Planilha1', skiprows=1)
    df.rename(columns={
        'Gestor no Tangerino': 'Gestor',
        'Departamento': 'Setor',
        'Cód. ': 'Cód.'
    }, inplace=True)
    df['Base'] = 'Bonfim'
    df = df.dropna(subset=['Cód.'])
    df['Setor'] = df['Setor'].str.split(' ').str[0]
    return df[['Cód.', 'Nome', 'Admissão', 'Cargo', 'Nascimento', 'STATUS', 'Setor', 'Gestor', 'Base']]

def extract_and_clean_jacobina(file_path: str) -> pd.DataFrame:
    """Extrai e limpa os dados de colaboradores de Jacobina."""
    logging.info(f"Processando arquivo: {file_path}")
    df = pd.read_excel(file_path, sheet_name='Planilha1', header=None)
    
    # Lógica para remover linhas em branco no início e promover cabeçalhos
    first_valid_row = df.notna().any(axis=1).idxmax()
    df = pd.read_excel(file_path, sheet_name='Planilha1', skiprows=first_valid_row)

    df.rename(columns={
        'Gestor no Tangerino': 'Gestor',
        'Cód. ': 'Cód.'
    }, inplace=True)
    df['Base'] = 'Jacobina'
    df = df.dropna(subset=['Cód.'])
    df['Setor'] = df['Setor'].str.split(' ').str[0]
    # Remove colunas desnecessárias para manter a consistência
    df = df[['Cód.', 'Nome', 'STATUS', 'Admissão', 'Setor', 'Gestor', 'Base']]
    return df

def extract_and_clean_juazeiro(file_path: str) -> pd.DataFrame:
    """Extrai e limpa os dados de colaboradores de Juazeiro."""
    logging.info(f"Processando arquivo: {file_path}")
    df = pd.read_excel(file_path, sheet_name='Planilha1')
    df.rename(columns={
        'GESTOR': 'Gestor',
        'STATUS ': 'STATUS',
        'Código Sistema': 'Cód.'
    }, inplace=True)
    df['Base'] = 'Juazeiro'
    df = df.dropna(subset=['Cód.'])
    return df[['Cód.', 'Setor', 'Gestor', 'STATUS', 'Nome', 'Nascimento', 'Admissão', 'Cargo', 'Base']]

def unify_colaboradores() -> pd.DataFrame:
    """Unifica e padroniza as bases de dados de colaboradores."""
    logging.info("Iniciando a unificação das bases de colaboradores.")
    
    df_bonfim = extract_and_clean_bonfim(COLABORADORES_FILES['bonfim'])
    df_jacobina = extract_and_clean_jacobina(COLABORADORES_FILES['jacobina'])
    df_juazeiro = extract_and_clean_juazeiro(COLABORADORES_FILES['juazeiro'])

    # Unifica os dataframes
    df_colaboradores = pd.concat([df_bonfim, df_jacobina, df_juazeiro], ignore_index=True, sort=False)
    
    logging.info("Bases de colaboradores unificadas com sucesso.")
    
    # Padroniza os tipos de dados e nomes
    df_colaboradores['Nome'] = df_colaboradores['Nome'].str.strip()
    df_colaboradores['Gestor'] = df_colaboradores['Gestor'].str.strip()
    
    return df_colaboradores

from thefuzz import process as fuzzy_process
from collections import defaultdict

def process_descontos(df_colaboradores: pd.DataFrame) -> pd.DataFrame:
    """
    Processa o arquivo de descontos usando uma estratégia de matching em cascata:
    1. Fuzzy match no nome do colaborador (limiar alto).
    2. Fallback para fuzzy match dentro da equipe do Supervisor.
    3. Fallback para fuzzy match dentro da equipe do Coordenador.
    """
    logging.info(f"Processando arquivo de descontos com Fuzzy Matching em cascata: {DESCONTOS_FILE}")
    df_descontos = pd.read_csv(DESCONTOS_FILE, sep=';', encoding='utf-8')

    # --- Padronização de Nomes ---
    df_descontos.rename(columns={'Funcionário': 'Nome_Original'}, inplace=True)
    df_descontos['Nome_Original'] = df_descontos['Nome_Original'].str.strip().str.title()
    df_colaboradores['Nome'] = df_colaboradores['Nome'].str.strip().str.title()
    df_colaboradores['Gestor'] = df_colaboradores['Gestor'].str.strip().str.title()
    df_descontos['Supervisor'] = df_descontos['Supervisor'].str.strip().str.title()
    df_descontos['Coordenador'] = df_descontos['Coordenador'].str.strip().str.title()

    # --- 1. Fuzzy Matching Primário (Nome do Colaborador) ---
    logging.info("Iniciando 1ª Etapa: Correspondência aproximada por nome (Limiar 96).")
    
    nomes_descontos = df_descontos['Nome_Original'].dropna().unique()
    nomes_colaboradores = df_colaboradores['Nome'].dropna().unique()
    
    SIMILARITY_THRESHOLD = 96
    nome_map = {}
    unmatched_after_primary = []

    for nome_desconto in nomes_descontos:
        best_match = fuzzy_process.extractOne(nome_desconto, nomes_colaboradores)
        if best_match and best_match[1] >= SIMILARITY_THRESHOLD:
            nome_map[nome_desconto] = best_match[0]
            if nome_desconto != best_match[0]:
                logging.info(f"[ETAPA 1] Correspondência: '{nome_desconto}' -> '{best_match[0]}' (Score: {best_match[1]})")
        else:
            unmatched_after_primary.append(nome_desconto)
            
    # --- 2. Fallback com Supervisor e Coordenador ---
    logging.info("Iniciando 2ª Etapa: Fallback via Supervisor/Coordenador.")
    
    # Prepara um mapa de gestor -> lista de nomes da sua equipe
    gestor_map = df_colaboradores.groupby('Gestor')['Nome'].apply(list).to_dict()
    
    df_unmatched = df_descontos[df_descontos['Nome_Original'].isin(unmatched_after_primary)]
    final_unmatched = []

    for _, row in df_unmatched.iterrows():
        nome_desconto = row['Nome_Original']
        supervisor = row['Supervisor']
        coordenador = row['Coordenador']
        
        found_match = False
        
        # Tenta com o Supervisor
        if pd.notna(supervisor) and supervisor in gestor_map:
            equipe = gestor_map[supervisor]
            best_match = fuzzy_process.extractOne(nome_desconto, equipe)
            if best_match and best_match[1] >= SIMILARITY_THRESHOLD:
                nome_map[nome_desconto] = best_match[0]
                logging.info(f"[ETAPA 2-S] '{nome_desconto}' -> '{best_match[0]}' via Supervisor '{supervisor}' (Score: {best_match[1]})")
                found_match = True
        
        # Se não achou, tenta com o Coordenador
        if not found_match and pd.notna(coordenador) and coordenador in gestor_map:
            equipe = gestor_map[coordenador]
            best_match = fuzzy_process.extractOne(nome_desconto, equipe)
            if best_match and best_match[1] >= SIMILARITY_THRESHOLD:
                nome_map[nome_desconto] = best_match[0]
                logging.info(f"[ETAPA 2-C] '{nome_desconto}' -> '{best_match[0]}' via Coordenador '{coordenador}' (Score: {best_match[1]})")
                found_match = True
        
        if not found_match:
            final_unmatched.append(nome_desconto)

    # --- Análise Final de Não Encontrados ---
    if final_unmatched:
        logging.warning("Após todas as etapas, os seguintes colaboradores NÃO foram encontrados:")
        for name in sorted(list(set(final_unmatched))):
            logging.warning(f" - {name}")
    else:
        logging.info("Todos os colaboradores foram correspondidos com sucesso após todas as etapas!")

    # --- Merge Final ---
    df_descontos['Nome'] = df_descontos['Nome_Original'].map(nome_map)
    df_merged = pd.merge(df_descontos, df_colaboradores, on='Nome', how='left')

    # ---- Transformações Finais ----
    df_processed = df_merged.dropna(subset=['Cód.']).copy() # Usa Cód. como proxy de um merge bem sucedido
    
    df_processed['Data Ocorrência'] = pd.to_datetime(df_processed['Data Ocorrência'], format='%d/%m/%Y', errors='coerce')
    df_processed = df_processed[df_processed['Data Ocorrência'] > '2024-12-31']
    
    setor_replacements = {
        "Linha Viva Juazeiro 1": "Linha Viva", "Manutenção Pesada": "Manutenção",
        "Comercial Juazeiro": "Comercial", "Comercial C. Alegre": "Comercial",
        "Turma Rubem": "Construção", "Comercial Remanso": "Comercial",
        "Linha": "Linha Viva", "Linha Viva Viva": "Linha Viva"
    }
    df_processed['Setor'] = df_processed['Setor'].replace(setor_replacements)

    df_processed = df_processed[df_processed['Supervisor'] != "SUPERVISOR_TRM"]
    
    cols_to_capitalize = ["Origem", "Tipo", "Grupo Item", "Item", "Gestor", "Setor"]
    for col in cols_to_capitalize:
        if col in df_processed.columns:
            df_processed[col] = df_processed[col].astype(str).str.title().str.strip()

    df_processed['Grupo Item'] = df_processed['Grupo Item'].replace("", "Não Especificado")
    df_processed['Item'] = df_processed['Item'].replace("", "Não Especificado")
    
    logging.info("Transformações finais aplicadas.")
    
    return df_processed

def main():
    """Função principal para orquestrar o pipeline de ETL."""
    logging.info("Iniciando pipeline de ETL de Descontos de Segurança.")
    
    try:
        # Garante que o diretório de saída exista
        os.makedirs(OUTPUT_PATH, exist_ok=True)
        
        df_colaboradores_unificado = unify_colaboradores()
        df_final = process_descontos(df_colaboradores_unificado)
        
        # Salva o resultado
        df_final.to_csv(OUTPUT_FILE, index=False, sep=';', encoding='utf-8-sig')
        logging.info(f"Pipeline concluído com sucesso. Arquivo salvo em: {OUTPUT_FILE}")
        
    except FileNotFoundError as e:
        logging.error(f"Erro: Arquivo não encontrado - {e}")
    except Exception as e:
        logging.error(f"Ocorreu um erro inesperado: {e}")

if __name__ == "__main__":
    main()

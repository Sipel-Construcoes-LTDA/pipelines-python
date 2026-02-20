import pandas as pd
import os
import logging
from thefuzz import process as fuzzy_process
from collections import defaultdict
from typing import Dict, List, Any

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Constantes de Caminhos ---
BASE_PATH: str = os.path.join(os.path.dirname(__file__), '..', 'data')
INPUT_PATH: str = os.path.join(BASE_PATH, 'auxiliary')
OUTPUT_PATH: str = os.path.join(BASE_PATH, 'processed')
COLABORADORES_FILES: Dict[str, str] = {
    'bonfim': os.path.join(INPUT_PATH, 'aux_colaboradores_bonfim.xlsx'),
    'jacobina': os.path.join(INPUT_PATH, 'aux_colaboradores_jacobina.xlsx'),
    'juazeiro': os.path.join(INPUT_PATH, 'aux_colaboradores_juazeiro.xlsx')
}
DESCONTOS_FILE: str = os.path.join(INPUT_PATH, 'aux_descontos.csv')
GESTORES_FILE: str = os.path.join(INPUT_PATH, 'aux_gestores.xlsx')
OUTPUT_FILE: str = os.path.join(OUTPUT_PATH, 'descontos_consolidados.csv')


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
    
    # Limpeza de Cód. e linhas inválidas
    df = df.dropna(subset=['Cód.'])
    df = df[~df['Cód.'].astype(str).isin(['VALOR', '0', 'Total', 'nan'])]
    
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
    
    # Limpeza de Cód. e linhas inválidas
    df = df.dropna(subset=['Cód.'])
    df = df[~df['Cód.'].astype(str).isin(['VALOR', '0', 'Total', 'nan'])]
    
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
    
    # Limpeza de Cód. e linhas inválidas
    df = df.dropna(subset=['Cód.'])
    df = df[~df['Cód.'].astype(str).isin(['VALOR', '0', 'Total', 'nan'])]
    
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

def load_and_prep_gestores() -> pd.DataFrame:
    """Carrega e prepara a tabela auxiliar de gestores."""
    logging.info(f"Carregando tabela auxiliar de gestores: {GESTORES_FILE}")
    try:
        df = pd.read_excel(GESTORES_FILE)
        # Limpa o nome do inspetor (remove CPF/Matrícula se houver, ex: 'NOME - 123...')
        df['Clean_Name'] = df['INSPETORES'].astype(str).str.split(' -').str[0].str.strip().str.title()
        # Garante que a coluna alvo está formatada
        df['PRIMEIRO E ULTIMO NOME'] = df['PRIMEIRO E ULTIMO NOME'].astype(str).str.title().str.strip()
        return df[['Clean_Name', 'PRIMEIRO E ULTIMO NOME']]
    except Exception as e:
        logging.error(f"Erro ao carregar aux_gestores: {e}")
        return pd.DataFrame()

def standardize_managers(df_processed: pd.DataFrame, df_gestores: pd.DataFrame) -> pd.DataFrame:
    """Padroniza os nomes dos gestores usando a tabela auxiliar."""
    if df_gestores.empty:
        logging.warning("Tabela de gestores vazia. Pulando padronização.")
        return df_processed

    logging.info("Padronizando nomes dos gestores...")
    
    # Cria lista de nomes de referência
    valid_managers: List[str] = list(df_gestores['Clean_Name'].unique())
    target_name_map: Dict[str, str] = dict(zip(df_gestores['Clean_Name'], df_gestores['PRIMEIRO E ULTIMO NOME']))
    
    # Mapeamento de cache para evitar processamento repetido
    manager_cache: Dict[str, str] = {}
    
    def get_standard_manager(name: Any) -> str:
        if pd.isna(name) or name == "" or name == "nan":
            return "Não Especificado"
        
        name_clean = str(name).strip().title()
        
        if name_clean in manager_cache:
            return manager_cache[name_clean]
            
        # 1. Tentativa de match exato no nome limpo
        if name_clean in valid_managers:
            standard_name = target_name_map[name_clean]
            manager_cache[name_clean] = standard_name
            return standard_name
            
        # 2. Fuzzy match
        best_match = fuzzy_process.extractOne(name_clean, valid_managers)
        if best_match and best_match[1] >= 80: # Limiar de 80% para variações como "Alan Moura" -> "Alan Santos De Moura"
            standard_name = target_name_map[best_match[0]]
            manager_cache[name_clean] = standard_name
            logging.info(f"[Gestor Match] '{name}' -> '{standard_name}' (Score: {best_match[1]})")
            return standard_name
            
        # Fallback: Mantém o original se não encontrar match
        manager_cache[name_clean] = name_clean
        return name_clean

    df_processed['Gestor_Padronizado'] = df_processed['Gestor'].apply(get_standard_manager)
    return df_processed

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
    
    SIMILARITY_THRESHOLD: int = 96
    nome_map: Dict[str, str] = {}
    unmatched_after_primary: List[str] = []

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
    gestor_map: Dict[str, List[str]] = df_colaboradores.groupby('Gestor')['Nome'].apply(list).to_dict()
    
    df_unmatched = df_descontos[df_descontos['Nome_Original'].isin(unmatched_after_primary)]
    final_unmatched: List[str] = []

    for _, row in df_unmatched.iterrows():
        nome_desconto = row['Nome_Original']
        supervisor = row['Supervisor']
        coordenador = row['Coordenador']
        
        found_match: bool = False
        
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
    # Filtra registros que não tiveram correspondência (Cód. é nulo)
    df_processed = df_merged.dropna(subset=['Cód.']).copy() 
    
    df_processed['Data Ocorrência'] = pd.to_datetime(df_processed['Data Ocorrência'], format='%d/%m/%Y', errors='coerce')
    df_processed = df_processed[df_processed['Data Ocorrência'] > '2024-12-31']
    
    setor_replacements: Dict[str, str] = {
        "Linha Viva Juazeiro 1": "Linha Viva", "Manutenção Pesada": "Manutenção",
        "Comercial Juazeiro": "Comercial", "Comercial C. Alegre": "Comercial",
        "Turma Rubem": "Construção", "Comercial Remanso": "Comercial",
        "Linha": "Linha Viva", "Linha Viva Viva": "Linha Viva"
    }
    df_processed['Setor'] = df_processed['Setor'].replace(setor_replacements)

    df_processed = df_processed[df_processed['Supervisor'] != "SUPERVISOR_TRM"]
    
    # --- Padronização de Gestores (NOVO) ---
    df_gestores = load_and_prep_gestores()
    df_processed = standardize_managers(df_processed, df_gestores)
    
    cols_to_capitalize: List[str] = ["Origem", "Tipo", "Grupo Item", "Item", "Setor"] # Gestor removido daqui pois já foi tratado
    for col in cols_to_capitalize:
        if col in df_processed.columns:
            # Preenche NA com string vazia antes de converter e capitalizar para evitar "Nan"
            df_processed[col] = df_processed[col].fillna("").astype(str).str.title().str.strip()

    df_processed['Grupo Item'] = df_processed['Grupo Item'].replace(["", "Nan"], "Não Especificado")
    df_processed['Item'] = df_processed['Item'].replace(["", "Nan"], "Não Especificado")
    
    logging.info("Transformações finais aplicadas.")
    
    return df_processed

def main() -> None:
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

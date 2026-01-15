import pandas as pd
import numpy as np
import os
import datetime
import requests
import io
import re
import logging

# ==========================================
# Configuration & Setup
# ==========================================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
AUX_DIR = os.path.join(DATA_DIR, 'auxiliary')
PROCESSED_DIR = os.path.join(DATA_DIR, 'processed')

# Create directories
os.makedirs(AUX_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Google Sheets URLs
SHEETS_MAP = {
    'jacobina': {
        'url': 'https://docs.google.com/spreadsheets/d/14YrO2leP08ddPMh1vx0WFT2oLqWiBDDAe6qlUNpYV2M/export?format=csv&gid=576710224',
        'coord': 'JACOBINA'
    },
    'bonfim_fechamento': {
        'url': 'https://docs.google.com/spreadsheets/d/14YrO2leP08ddPMh1vx0WFT2oLqWiBDDAe6qlUNpYV2M/export?format=csv&gid=1425364438',
        'coord': 'SENHOR DO BONFIM'
    },
    'bonfim_aceitas': {
        'url': 'https://docs.google.com/spreadsheets/d/14YrO2leP08ddPMh1vx0WFT2oLqWiBDDAe6qlUNpYV2M/export?format=csv&gid=1712361722',
        'coord': 'SENHOR DO BONFIM'
    },
    'bonfim_enviadas': {
        'url': 'https://docs.google.com/spreadsheets/d/14YrO2leP08ddPMh1vx0WFT2oLqWiBDDAe6qlUNpYV2M/export?format=csv&gid=800691815',
        'coord': 'SENHOR DO BONFIM'
    },
    'juazeiro_aceitas': {
        'url': 'https://docs.google.com/spreadsheets/d/1uO47jaWHLg1aNnRyTytP4DI7kcoTc2pyywZAK2IkH6U/export?format=csv&gid=824978689',
        'coord': 'JUAZEIRO'
    },
    'juazeiro_enviadas': {
        'url': 'https://docs.google.com/spreadsheets/d/1uO47jaWHLg1aNnRyTytP4DI7kcoTc2pyywZAK2IkH6U/export?format=csv&gid=190048177',
        'coord': 'JUAZEIRO'
    },
    'juazeiro_fechamento': {
        'url': 'https://docs.google.com/spreadsheets/d/1uO47jaWHLg1aNnRyTytP4DI7kcoTc2pyywZAK2IkH6U/export?format=csv&gid=1413339852',
        'coord': 'JUAZEIRO'
    }
}

COL_MAPPING = {
    r'(?i)VALOR\s*L\.?.V.?.?': 'VALOR MAO DE OBRA LV',
    r'(?i)VALOR\s*Á\s*FATURAR\s*LV': 'VALOR MAO DE OBRA LV',
    r'(?i)VALOR\s*MAO\s*DE\s*OBRA$': 'VALOR Á FATURAR LM',
    r'(?i)VALOR\s*L\.?.M': 'VALOR Á FATURAR LM',
    r'(?i)VALOR\s*Á\s*FATURAR\s*LM': 'VALOR Á FATURAR LM',
    # More flexible regex to avoid encoding issues with Ç and Ã
    r'(?i)DISTRIBUI.*DE\s*POSTE': 'VALOR Á FATURAR DISTRI. DE POSTES',
    r'(?i)ENTRADA\s*FECHAMENTO': 'ENTRADA',
    r'(?i)DT\s*DE\s*ENT\.\s*DE\s*AS\s*BUILT': 'ENTRADA',
    r'(?i)SUPERVISOR\s*/\s*TURMA': 'SUPERVISOR',
    r'(?i)CADASTRO': 'ESTAGIÁRIO',
    r'(?i)Ano': 'ANO'
}

# ==========================================
# Helper Functions
# ==========================================

def clean_currency(val):
    """
    Cleans Brazilian currency strings (e.g., 'R$ 1.234,56') to float (1234.56).
    Handles integers, floats, and strings.
    """
    if pd.isna(val):
        return 0.0
    
    s_val = str(val).strip()
    if not s_val:
        return 0.0
        
    # Remove R$, whitespace, and dots (thousands separators)
    # Be careful: if the input is already dot-decimal (1234.56), removing dot breaks it.
    # Assumption: Input is PT-BR format (dot=thousand, comma=decimal) OR simple int.
    
    # Heuristic: if contains ',' it's likely PT-BR decimal.
    # If it contains 'R$' it is definitely a string to clean.
    
    try:
        if 'R$' in s_val or ',' in s_val:
            s_val = s_val.replace('R$', '').replace(' ', '')
            s_val = s_val.replace('.', '') # Remove thousand separator
            s_val = s_val.replace(',', '.') # Replace decimal separator
        
        return float(s_val)
    except Exception:
        return 0.0

def load_google_sheet(key):
    config = SHEETS_MAP.get(key)
    try:
        logger.info(f"Downloading {key}...")
        response = requests.get(config['url'])
        response.raise_for_status()
        
        # Decode content to find the header row
        content_str = response.content.decode('utf-8')
        lines = content_str.splitlines()
        
        header_row = 0
        search_term = "PROJETO"
        
        # Search for the header row in the first 20 lines
        for i, line in enumerate(lines[:20]):
            # Simple check: splitting by comma or semicolon to see if "PROJETO" is a cell value
            # We check both case-insensitive just to be safe, though usually it's uppercase.
            if search_term.upper() in line.upper():
                header_row = i
                break
        
        if header_row > 0:
            logger.info(f"Found header for {key} at row {header_row}")
            
        # Read CSV skipping lines until the header
        df = pd.read_csv(io.StringIO(content_str), header=header_row)
        
        # Verify if PROJETO was actually found in columns (handling potential dirty characters)
        # Sometimes 'PROJETO' might be ' PROJETO' or 'PROJETO '
        df.columns = df.columns.astype(str).str.strip()
        
        # If PROJETO is not in columns after strip, try to find it in the first row of data 
        # (edge case where header detection might have been off by one or weird formatting)
        if 'PROJETO' not in df.columns:
             # Fallback: Try searching loosely
             for col in df.columns:
                 if 'PROJETO' in col.upper():
                     df.rename(columns={col: 'PROJETO'}, inplace=True)
                     break
        
        # Deduplicate columns: Keep first occurrence of each column name
        df = df.loc[:, ~df.columns.duplicated()]

        df['COORD'] = config['coord']
        return df
    except Exception as e:
        logger.error(f"Error loading {key}: {e}")
        return pd.DataFrame()

def normalize_columns(df):
    new_cols = {}
    for col in df.columns:
        clean_col = str(col).strip()
        matched = False
        for pattern, replacement in COL_MAPPING.items():
            if re.search(pattern, clean_col):
                new_cols[col] = replacement
                matched = True
                break
        if not matched:
            new_cols[col] = clean_col
    return df.rename(columns=new_cols)

def find_header_row(file_path, search_term="PROJETO", max_rows=15):
    """Finds the row index containing the search term."""
    try:
        # Load without header to scan rows
        df_preview = pd.read_excel(file_path, header=None, nrows=max_rows)
        for idx, row in df_preview.iterrows():
            if row.astype(str).str.contains(search_term, case=False, regex=False).any():
                return idx
    except Exception as e:
        logger.error(f"Error finding header in {os.path.basename(file_path)}: {e}")
    return 0

def load_excel_smart(file_path, search_term="PROJETO", sub_header_offset=0):
    """Loads excel finding the header row dynamically."""
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return pd.DataFrame()
    
    header_idx = find_header_row(file_path, search_term)
    actual_header = header_idx + sub_header_offset
    
    try:
        df = pd.read_excel(file_path, header=actual_header)
        
        # If we used an offset (e.g. for Encerramento Online), we might need to fix the Project column name
        # stored in the parent row (header_idx) which corresponds to Unnamed: X in actual_header
        if sub_header_offset > 0:
            # Re-read just the search row to find where PROJETO is
            df_search = pd.read_excel(file_path, header=None, nrows=header_idx+1)
            search_row = df_search.iloc[header_idx]
            # Find index of PROJETO
            proj_col_idx = -1
            for i, val in enumerate(search_row):
                if str(val).strip().upper() == search_term:
                    proj_col_idx = i
                    break
            
            if proj_col_idx != -1:
                # Rename the column at that index in the main df
                current_col_name = df.columns[proj_col_idx]
                df.rename(columns={current_col_name: 'PROJETO'}, inplace=True)

        # Cleanup column names
        df.columns = df.columns.astype(str).str.replace('\n', ' ').str.strip()
        return df
    except Exception as e:
        logger.error(f"Error loading {os.path.basename(file_path)}: {e}")
        return pd.DataFrame()

# ==========================================
# Main Processing Logic
# ==========================================

def main():
    logger.info("Starting ETL Process...")
    
    # 1. Load Google Sheets
    dfs = []
    for key in SHEETS_MAP.keys():
        df = load_google_sheet(key)
        if not df.empty:
            df = normalize_columns(df)
            # Deduplicate again because normalization might have mapped multiple cols to the same name
            df = df.loc[:, ~df.columns.duplicated()]
            dfs.append(df)
    
    if not dfs:
        logger.error("No data loaded. Exiting.")
        return

    main_df = pd.concat(dfs, ignore_index=True)
    
    # --- CLEANING COLUMNS & ROWS ---
    
    # 1. Drop rows where PROJETO is empty (removes Google Sheets empty rows and disconnected summaries)
    if 'PROJETO' in main_df.columns:
        initial_rows = len(main_df)
        main_df = main_df.dropna(subset=['PROJETO'])
        main_df = main_df[main_df['PROJETO'].astype(str).str.strip() != '']
        logger.info(f"Dropped {initial_rows - len(main_df)} empty/invalid rows based on 'PROJETO'.")

    # 2. Drop specific requested columns
    cols_to_drop = ['OBS. GSE', 'RESERVAS APP', 'Coluna 1']
    main_df.drop(columns=[c for c in cols_to_drop if c in main_df.columns], inplace=True)

    # 3. Drop "messy" columns:
    #    - Starting with 'Unnamed'
    #    - Headers that look like currency (e.g., '1276549,47', 'R$ ...')
    def is_garbage_column(col_name):
        s_col = str(col_name).strip()
        # Check for Unnamed
        if s_col.lower().startswith('unnamed'):
            return True
        # Check for currency-like headers (digits with comma/dot or R$)
        if re.search(r'^\d{1,3}(?:\.\d{3})*(?:,\d+)?$', s_col): # Matches 1.234,56
            return True
        if 'R$' in s_col:
            return True
        return False

    cols_to_remove = [c for c in main_df.columns if is_garbage_column(c)]
    if cols_to_remove:
        logger.info(f"Dropping garbage columns: {cols_to_remove}")
        main_df.drop(columns=cols_to_remove, inplace=True)

    # 4. Drop completely empty columns
    main_df.dropna(axis=1, how='all', inplace=True)
    
    # Save intermediate regional files
    for coord in main_df['COORD'].unique():
        regional_df = main_df[main_df['COORD'] == coord]
        safe_name = coord.lower().replace(' ', '_')
        output_regional = os.path.join(PROCESSED_DIR, f'aux_{safe_name}.csv')
        # Format as CSV with semicolon and comma decimal for Brazilian Excel
        regional_df.to_csv(output_regional, index=False, sep=';', decimal=',', encoding='utf-8-sig')

    # 2. Transformations
    fill_values = {
        "GSE": "Não Enviado", "ATESTO": "Não Enviado", "RESERVAS": "Não Enviado",
        "TECNICO": "NÃO DIRECIONADO", "GEOEX": "Não Postado", "CICLO DE POSTAGEM": "Não Postado"
    }
    for col, val in fill_values.items():
        if col not in main_df.columns: main_df[col] = np.nan
        main_df[col] = main_df[col].fillna(val).replace('', val)

    geoex_replacements = {
        "Não postado": "Não Postado", "ACEITA": "Aceita", "POSTADO": "Postado",
        "REJEITADA": "Rejeitada", "Rejeitada ": "Rejeitada", "REPostado": "Repostado",
        "VALIDADO": "Validado", "Á fechar": "Não Postado", "A postar": "Não Postado"
    }
    main_df['GEOEX'] = main_df['GEOEX'].replace(geoex_replacements)

    def extract_project(val):
        if pd.isna(val): return None
        parts = str(val).split('-')
        return parts[-1].strip() if len(parts) > 1 else str(val).strip()

    main_df['PROJETO_FATO'] = main_df['PROJETO'].apply(extract_project)
    
    # Numeric cleanup and formatting
    numeric_cols = [
        'VALOR MAO DE OBRA LV', 
        'VALOR Á FATURAR LM', 
        'VALOR Á FATURAR DISTRI. DE POSTES',
        'VALOR PENDENTE FATURAR',
        'VALOR PROJETO'
    ]
    for col in numeric_cols:
        if col in main_df.columns:
            main_df[col] = main_df[col].apply(clean_currency)
    
    if 'POSTES' in main_df.columns:
        main_df['POSTES'] = pd.to_numeric(main_df['POSTES'], errors='coerce').fillna(0).astype(int)

    # 3. Pendencies
    def calc_pendencies(row):
        pends = []
        # GSE
        g = row.get('GSE')
        if g in ["Desenhado"]:
            pends.append("Pendente conciliar")
        elif g in ["Em desenho"]:
            pends.append("Pendente finalizar desenho")
        elif g in ["Não enviado"]:
            pends.append("Pendente enviar GSE")
        elif g in ["Reprovado"]:
            pends.append("GSE Reprovado")
        elif g in ["Solic. p/ Retroagir"]:
            pends.append("Erro de cadastro no GSE")
        elif g in ["Solicitado"]:
            pends.append("GSE solicitado")
        elif g in ["Vazio", None, "", "Não Enviado"]:
            pends.append("GSE Não solicitado")
        
        # ATESTO
        a = row.get('ATESTO')
        if a == "Não enviado": pends.append("Pendente enviar atesto")
        elif a == "Solicitado": pends.append("Atesto solicitado")
        elif a == "Vazio": pends.append("Atesto não solicitado")

        # RESERVAS
        r = row.get('RESERVAS')
        if r == "Almoxarifado": pends.append("Pendencia no almoxarifado")
        elif r == "Consistindo": pends.append("Concistindo reservas")
        elif r == "Criação": pends.append("Pendente criação de reserva")
        elif r == "Não Enviado": pends.append("Pendente enviar reservas")
        elif r == "Vazio": pends.append("Pendente solicitar reserva")

        # AS BUILT
        if pd.isna(row.get('ENTRADA')) or row.get('ENTRADA') == "":
             pends.append('Pendente "As Built"')
        
        # EVIDENCIAS
        e = row.get('EVIDENCIAS BOOK')
        if e == "EVIDENCIA INSU. - GPM": pends.append("Evidencias insuficientes")
        elif e == "S/EVIDENCIA- GPM": pends.append("Sem evidences")

        return ", ".join(pends) if pends else "Sem pendência"

    main_df['Descrição de pendencias'] = main_df.apply(calc_pendencies, axis=1)

    # 4. Cycle Logic
    main_df['CICLO DE POSTAGEM'] = main_df['CICLO DE POSTAGEM'].astype(str).str.strip().str.title()
    months_pt = {1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho',
                 7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'}
    inv_months = {v: k for k, v in months_pt.items()}
    current_month_pt = months_pt[datetime.datetime.now().month]
    main_df['CICLO DE POSTAGEM'] = main_df['CICLO DE POSTAGEM'].replace({'Não Postado': current_month_pt})

    # 5. Aux Data Joins
    logger.info("Loading Auxiliary Data...")
    
    # LOAD AuxEncerramentoOnline
    aux_online_path = os.path.join(AUX_DIR, 'aux_encerramento_online.xlsx')
    # Offset=1 because headers like STATUS are in the row AFTER "PROJETO"
    aux_online = load_excel_smart(aux_online_path, search_term="PROJETO", sub_header_offset=1)
    
    if not aux_online.empty:
        aux_online['PROJETO_FATO'] = aux_online['PROJETO'].apply(extract_project)
        
        # Select target columns
        target_cols = ['PROJETO_FATO', 'STATUS', 'CONSISTÊNCIA', 'DT. ACEITO']
        if 'ANÁLISE 01' in aux_online.columns: target_cols.append('ANÁLISE 01')
        if 'DT DIREC.' in aux_online.columns: target_cols.append('DT DIREC.')
        
        # Find DT. ANALI columns
        dt_anali = [c for c in aux_online.columns if 'DT.' in c and 'ANALI' in c]
        if dt_anali:
            # Take the last one (often _2 in duplicate cases) or just the first found
            # M Code specifically looked for DT. ANALI._2 which suggests duplicates
            col_name = dt_anali[-1]
            aux_online['DT. ANALI._2'] = aux_online[col_name]
            target_cols.append('DT. ANALI._2')
            
        final_cols = [c for c in target_cols if c in aux_online.columns]
        aux_online = aux_online[final_cols].drop_duplicates(subset=['PROJETO_FATO'])
        
        main_df = pd.merge(main_df, aux_online, on='PROJETO_FATO', how='left', suffixes=('', '_Online'))
        main_df['STATUS'] = main_df['STATUS'].fillna("NÃO CRIADO")

    # LOAD AuxGSE
    aux_gse_path = os.path.join(AUX_DIR, 'aux_gse.xlsx')
    # GSE usually matches PROJETO row
    aux_gse = load_excel_smart(aux_gse_path, search_term="PROJETO", sub_header_offset=0)
    
    if not aux_gse.empty:
        aux_gse['PROJETO_FATO'] = aux_gse['PROJETO'].apply(extract_project)
        gse_cols = ['PROJETO_FATO', 'USUÁRIO/SOLIC.', 'DT. SOLIC.', 'DT. STATUS', 'STATUS']
        final_gse_cols = [c for c in gse_cols if c in aux_gse.columns]
        aux_gse = aux_gse[final_gse_cols].drop_duplicates(subset=['PROJETO_FATO'])
        
        main_df = pd.merge(main_df, aux_gse, on='PROJETO_FATO', how='left', suffixes=('', '_GSE'))
        # Fix Column Name if suffix created a mess or if M logic renamed it specific way
        if 'STATUS_GSE' in main_df.columns:
             main_df['AuxGSE.STATUS'] = main_df['STATUS_GSE'].fillna("N/A")
        elif 'STATUS' in aux_gse.columns:
             # If merging with same name, pandas produces STATUS_x and STATUS_y
             # We want GSE Status as AuxGSE.STATUS
             if 'STATUS_GSE' in main_df.columns:
                 main_df.rename(columns={'STATUS_GSE': 'AuxGSE.STATUS'}, inplace=True)
             elif 'STATUS' in final_gse_cols:
                  # Manual check for merged column
                  pass

    # LOAD Pastas Aceitas
    pastas_files = [f for f in os.listdir(AUX_DIR) if 'aux_pastas_aceitas' in f.lower() and f.endswith('.xlsx')]
    logger.info(f"Found {len(pastas_files)} Pastas Aceitas files.")
    
    dfs_pastas = []
    for f in pastas_files:
        p_path = os.path.join(AUX_DIR, f)
        # These files often have PROJETO in a lower row (e.g. index 3)
        df_p = load_excel_smart(p_path, search_term="PROJETO")
        if not df_p.empty and 'DT. BAIXA' in df_p.columns and 'PROJETO' in df_p.columns:
            dfs_pastas.append(df_p[['PROJETO', 'DT. BAIXA']])
    
    if dfs_pastas:
        aux_pastas = pd.concat(dfs_pastas, ignore_index=True)
        aux_pastas['PROJETO_FATO'] = aux_pastas['PROJETO'].apply(extract_project)
        # Drop duplicates, keep last or first? M Code just says Distinct.
        aux_pastas = aux_pastas.drop_duplicates(subset=['PROJETO_FATO'])
        main_df = pd.merge(main_df, aux_pastas[['PROJETO_FATO', 'DT. BAIXA']], on='PROJETO_FATO', how='left')

    # Final Cycle Date Calculation
    def calc_cycle(row):
        mes_nome = row.get('CICLO DE POSTAGEM')
        mes_num = inv_months.get(mes_nome)
        if not mes_num: return None

        # Manual Ano
        try:
            if not pd.isna(row.get('ANO')):
                return datetime.date(int(row['ANO']), mes_num, 1)
        except: pass

        # Auto
        dt_baixa = row.get('DT. BAIXA')
        try:
            if not pd.isna(dt_baixa):
                 dt_val = pd.to_datetime(dt_baixa)
                 ano_base = dt_val.year
            else:
                 ano_base = datetime.datetime.now().year
        except:
            ano_base = datetime.datetime.now().year
            
        dt = datetime.date(ano_base, mes_num, 1)
        if dt > datetime.date.today():
             dt = datetime.date(ano_base - 1, mes_num, 1)
        return dt

    main_df['Data do Ciclo'] = main_df.apply(calc_cycle, axis=1)

    # Save
    output_path = os.path.join(PROCESSED_DIR, 'faturamentos_encerramento.csv')
    main_df.to_csv(output_path, index=False, sep=';', decimal=',', encoding='utf-8-sig')
    logger.info(f"Pipeline complete. Saved to {output_path}")

if __name__ == "__main__":
    main()

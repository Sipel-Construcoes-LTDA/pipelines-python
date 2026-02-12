import pandas as pd
import logging
from pathlib import Path
import sys
import numpy as np

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ETL_Movimentacoes_Detalhada")

def enforce_strict_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica tipagem rigorosa baseada no Power Query (M Code) fornecido.
    """
    logger.info("Iniciando conversão rigorosa de tipos...")

    # 1. Tratamento Global de Strings Nulas e "<Na>"
    # Substitui <Na> por vazio e nan por vazio temporariamente para strings
    df = df.replace({'<Na>': np.nan, '<na>': np.nan})
    
    # 2. Definição do Schema (Baseado no M Code)
    
    # Inteiros (Int64 permite nulos)
    cols_int = [
        "obra", "CodMaterial", "TipoSolic", "IsDeleted", "CENTRO_MATERIAL",
        "idCoordenador", "idSupervisor"
    ]
    
    # Decimais/Floats
    cols_float = ["QuantSolic", "Quant_Confirmada"]
    
    # Datas (Datetime)
    cols_date = [
        "DataEstorno", "DataSolic", "DataCriacaoReserva", "Modified", 
        "DataPendencia", "DataRegularizacao", "Created", "DataSolicMod", 
        "DataSolicPrev", "DATA_CRIACAO", "DataSaqMod"
    ]
    
    # Strings (Texto)
    cols_str = [
        "MaterialSolic", "BaseOperacional", "StatusSolic", "MOTIVO_EXCLUSAO",
        "Coleborador_solicitante", "AVALIACAO_MATERIAL", "RECEBEDOR", "SUPR_MATR",
        "Observacao", "IdSolic", "Encarregado", "isUrgente", "titulo",
        "AgenteResponsavel", "Pendencias", "DescricaoPendencias", "UsuarioMovimentacao",
        "MotivoRejSolic", "EmailSolic", "UnidadeMedida", "Processo", 
        "ProjetoFilho", "Separacao", "Justificar"
    ]
    
    # Booleanos
    cols_bool = ["IsAvulso"]

    # --- APLICAÇÃO ---

    # Inteiros
    for col in cols_int:
        if col in df.columns:
            # Remove sufixos .0 ou caracteres não numéricos antes de converter
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')

    # Decimais
    for col in cols_float:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Datas
    for col in cols_date:
        if col in df.columns:
            # Errors='coerce' transforma falhas em NaT (Not a Time)
            # Usamos utc=True e tz_localize(None) para consistência com os outros scripts
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=False, utc=True).dt.tz_localize(None).dt.normalize()

    # Strings
    for col in cols_str:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            # Limpa 'nan', 'None', 'NaT' que viraram string
            replace_mask = df[col].str.lower().isin(['nan', 'nat', 'none', '<na>', ''])
            df.loc[replace_mask, col] = ""

    # Booleanos
    for col in cols_bool:
        if col in df.columns:
            # Mapeamento seguro
            df[col] = df[col].map({'True': True, 'False': False, True: True, False: False})
            df[col] = df[col].astype('boolean') # Permite nulos

    logger.info("Tipagem rigorosa aplicada.")
    return df

def main():
    try:
        root_dir = Path(__file__).resolve().parents[2]
        raw_dir = root_dir / "materiais_obra/data/raw"
        processed_dir = root_dir / "materiais_obra/data/processed"
        processed_dir.mkdir(parents=True, exist_ok=True)

        path_materiais = raw_dir / "materiais_obra_raw.csv"
        path_reservas = raw_dir / "tabela_reservas_raw.csv"

        if not path_materiais.exists() or not path_reservas.exists():
            logger.error("Arquivos RAW não encontrados. Execute etl_materiais.py e etl_reservas.py primeiro.")
            return

        logger.info("Lendo arquivos RAW...")
        # Lê tudo como string inicialmente para evitar inferências erradas do Pandas
        df_mat = pd.read_csv(path_materiais, sep=';', dtype=str, encoding='utf-8-sig')
        df_res = pd.read_csv(path_reservas, sep=';', dtype=str, encoding='utf-8-sig')

        # Normalização Pré-Merge (Alinhamento de Nomes)
        # O Power BI faz um Combine, então os nomes precisam bater
        mapping_mat = {
            'Quant_x002e_Confirmada': 'Quant_Confirmada',
            'DataRegularisado': 'DataRegularizacao'
        }
        df_mat = df_mat.rename(columns=mapping_mat)
        
        mapping_res = {
            'DataRegularisado': 'DataRegularizacao'
        }
        df_res = df_res.rename(columns=mapping_res)

        logger.info(f"Materiais: {df_mat.shape}, Reservas: {df_res.shape}")

        # Concatenação (Append)
        # ignore_index=True cria um index novo sequencial
        df_final = pd.concat([df_mat, df_res], ignore_index=True, sort=False)
        
        # --- UNIFICAÇÃO E VALIDAÇÃO CRÍTICA DE ID ---
        # SharePoint pode retornar 'Id' ou 'ID'. Unificamos para 'Id'.
        if 'ID' in df_final.columns and 'Id' in df_final.columns:
            logger.info("Unificando colunas 'ID' e 'Id'...")
            df_final['Id'] = df_final['Id'].fillna(df_final['ID'])
            df_final.drop(columns=['ID'], inplace=True)
        elif 'ID' in df_final.columns:
            df_final.rename(columns={'ID': 'Id'}, inplace=True)

        if 'Id' in df_final.columns:
            initial_rows = len(df_final)
            # Converte para string e limpa lixo
            df_final['Id'] = df_final['Id'].astype(str).str.strip().replace(['nan', 'NaN', 'None', 'nan', ''], np.nan)
            df_final.dropna(subset=['Id'], inplace=True)
            dropped_ids = initial_rows - len(df_final)
            if dropped_ids > 0:
                logger.warning(f"Removidas {dropped_ids} linhas com 'Id' inválido/vazio após o merge.")
        else:
            logger.error("COLUNA 'Id' NÃO ENCONTRADA APÓS O MERGE!")

        # Remove colunas totalmente vazias criadas pelo concat (se existirem apenas em um lado e forem vazias)
        df_final.dropna(axis=1, how='all', inplace=True)

        # Aplica a Tipagem Rigorosa
        df_final = enforce_strict_types(df_final)

        # --- TRATAMENTOS POWER QUERY (MIGRATION) ---
        logger.info("Aplicando transformações finais (Power Query Migration)...")

        # 1. Filtro de IDs nulos/vazios
        if 'Id' in df_final.columns:
            df_final = df_final[df_final['Id'].notna()].copy()

        # 2. Padronização de StatusSolic
        if 'StatusSolic' in df_final.columns:
            status_map = {
                'Confirmado': 'Movimentado',
                'Reservado': 'Pendente',
                'Deletado': 'Rejeitado',
                'Estornado': 'Rejeitado'
            }
            df_final['StatusSolic'] = df_final['StatusSolic'].replace(status_map)

        # 3. Tratamento da coluna 'Justificar'
        if 'Justificar' in df_final.columns:
            df_final['Justificar'] = df_final['Justificar'].fillna('Comum').replace({'': 'Comum', 'Normal': 'Comum'})

        # 4. Formatação de 'titulo' (Proper Case)
        if 'titulo' in df_final.columns:
            df_final['titulo'] = df_final['titulo'].astype(str).str.title().str.strip()

        # 5. Remoção de Colunas (Conforme M Code)
        cols_to_drop = [
            'MotivoRejSolic', 'EmailSolic', 'IsAvulso', 'LatitudeSolic', 'LongetudeSolic',
            'Observacao', 'isUrgente', 'UnidadeMedida', 'ProjetoFilho', 'Separacao',
            'AuthorId', 'EditorId', 'MOTIVO_EXCLUSAO', 'AVALIACAO_MATERIAL', 
            'CENTRO_MATERIAL', 'RECEBEDOR', 'SUPR_MATR', 'GUID'
        ]
        df_final.drop(columns=[c for c in cols_to_drop if c in df_final.columns], inplace=True)

        # 6. Limpeza de Linhas em Branco (Rigorosa)
        # Se IdSolic, obra e CodMaterial forem nulos/vazios, remove.
        subset_validation = ['IdSolic', 'obra', 'CodMaterial']
        subset_validation = [c for c in subset_validation if c in df_final.columns]
        
        if subset_validation:
            initial_rows = len(df_final)
            mask = df_final[subset_validation].replace('', np.nan).isna().all(axis=1)
            df_final = df_final[~mask]
            dropped = initial_rows - len(df_final)
            if dropped > 0:
                logger.info(f"Removidas {dropped} linhas sem identificadores principais.")

        # --- SANITIZAÇÃO FINAL DE STRINGS (CRÍTICO: ANTI-SHIFTING) ---
        logger.info("Sanitizando campos de texto (Removendo ';' e quebras de linha)...")
        text_cols = df_final.select_dtypes(include=['object']).columns
        for col in text_cols:
            df_final[col] = df_final[col].astype(str).str.replace(';', ',', regex=False).str.replace('\n', ' ', regex=False).str.replace('\r', '', regex=False).str.strip()
            df_final.loc[df_final[col].str.lower().isin(['nan', 'none', 'nat', '']), col] = ''

        # Salvamento com vírgula decimal
        output_path = processed_dir / "fato_movimentacoes_itens.csv"
        df_final.to_csv(output_path, sep=';', index=False, encoding='utf-8-sig', date_format='%Y-%m-%d', decimal=',')
        
        logger.info("=== SUCESSO ===")
        logger.info(f"Arquivo gerado: {output_path}")
        logger.info(f"Total de Linhas: {len(df_final)}")
        logger.info("Tipos de Dados Finais:")
        logger.info(df_final.dtypes)

    except Exception as e:
        logger.critical(f"Erro fatal: {e}")
        raise

if __name__ == "__main__":
    main()

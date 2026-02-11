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
        "DataPendencia", "DataRegularisado", "Created", "DataSolicMod", 
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
            # Adicione outros mapeamentos se necessário para alinhar com Reservas
        }
        df_mat = df_mat.rename(columns=mapping_mat)

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

        # Remove linhas totalmente vazias (Equivalente ao Table.SelectRows do Power BI)
        # Verifica se todas as colunas (exceto index) são nulas/vazias
        # Mas como strings viraram "", verificamos se não é tudo "" ou NaT ou NaN
        # Uma abordagem prática: se IdSolic, obra e CodMaterial forem nulos/vazios, remove.
        subset_validation = ['IdSolic', 'obra', 'CodMaterial']
        # Filtra apenas colunas que existem
        subset_validation = [c for c in subset_validation if c in df_final.columns]
        
        if subset_validation:
            initial_rows = len(df_final)
            # Converte temporariamente para validar vazio
            mask = df_final[subset_validation].replace('', np.nan).isna().all(axis=1)
            df_final = df_final[~mask]
            dropped = initial_rows - len(df_final)
            if dropped > 0:
                logger.info(f"Removidas {dropped} linhas sem identificadores principais.")

        # Salvamento
        output_path = processed_dir / "fato_movimentacoes_itens.csv"
        df_final.to_csv(output_path, sep=';', index=False, encoding='utf-8-sig', date_format='%Y-%m-%d')
        
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

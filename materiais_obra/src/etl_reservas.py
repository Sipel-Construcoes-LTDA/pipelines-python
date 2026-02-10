import os
import sys
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from office365.runtime.auth.client_credential import ClientCredential
from office365.runtime.auth.user_credential import UserCredential
from office365.sharepoint.client_context import ClientContext
from office365.sharepoint.listitems.collection import ListItemCollection

# Configuração de Logging Estruturado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configurações Globais
SHAREPOINT_SITE_URL = "https://netorg2135259.sharepoint.com/sites/sipel.com.br"
SHAREPOINT_LIST_NAME = "TabelaReservas"

def load_environment_variables():
    """
    Carrega variáveis de ambiente de forma robusta e exibe diagnóstico.
    """
    # 1. Determina caminho do .env
    root_dir = Path(__file__).resolve().parents[2]
    env_path = root_dir / '.env'
    
    logger.info(f"Carregando configurações de: {env_path}")
    
    if not env_path.exists():
        logger.critical(f"ARQUIVO .ENV NÃO ENCONTRADO EM: {env_path}")
        logger.critical("O script não conseguirá se autenticar.")
        return

    # 2. Força recarga (override=True) para garantir que alterações recentes sejam lidas
    load_dotenv(dotenv_path=env_path, override=True)
    
    # 3. Diagnóstico de Variáveis (Apenas status, sem valores)
    client_id = os.getenv("SHAREPOINT_CLIENT_ID")
    client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET")
    username = os.getenv("SHAREPOINT_USER")
    
    logger.info("--- DIAGNÓSTICO DE CREDENCIAIS ---")
    logger.info(f"SHAREPOINT_CLIENT_ID     : {'[OK] Carregado' if client_id else '[FALHA] Vazio ou Não Encontrado'}")
    logger.info(f"SHAREPOINT_CLIENT_SECRET : {'[OK] Carregado' if client_secret else '[FALHA] Vazio ou Não Encontrado'}")
    logger.info(f"SHAREPOINT_USER          : {'[OK] Carregado' if username else '[AVISO] Não encontrado (Fallback)'}")
    logger.info("----------------------------------")

def get_sharepoint_context(url: str) -> ClientContext:
    """
    Estabelece conexão segura com o SharePoint.
    """
    # Lê as variáveis AGORA, garantindo que load_dotenv já rodou
    client_id = os.getenv("SHAREPOINT_CLIENT_ID")
    client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET")
    username = os.getenv("SHAREPOINT_USER")
    password = os.getenv("SHAREPOINT_PASSWORD")

    try:
        # 1. Tenta Autenticação Moderna (App-Only)
        if client_id and client_secret:
            logger.info(f"Autenticando via App-Only (Client ID: ...{client_id[-4:] if len(client_id)>4 else '****'})")
            credentials = ClientCredential(client_id, client_secret)
            ctx = ClientContext(url).with_credentials(credentials)
        
        # 2. Fallback para Usuário/Senha
        elif username and password:
            logger.warning("Autenticando via Usuário/Senha (Legado).")
            credentials = UserCredential(username, password)
            ctx = ClientContext(url).with_credentials(credentials)
            
        else:
            raise ValueError("Nenhuma credencial válida encontrada no .env.")

        # Teste de conexão
        web = ctx.web
        ctx.load(web)
        ctx.execute_query()
        logger.info(f"Conexão SUCESSO: Site '{web.properties.get('Title')}'")
        return ctx

    except Exception as e:
        error_msg = str(e)
        logger.error(f"FALHA DE CONEXÃO: {error_msg}")
        
        if "AADSTS90023" in error_msg:
             logger.error("-> CAUSA: A Microsoft bloqueou login por senha neste tenant.")
             logger.error("-> SOLUÇÃO: Verifique se o Diagnóstico acima mostra CLIENT_ID como [FALHA].")
        elif "401" in error_msg:
             logger.error("-> CAUSA: Credenciais inválidas (Secret expirado ou ID errado).")
        
        sys.exit(1)

def extract_list_items_paged(ctx: ClientContext, list_name: str, page_size: int = 5000) -> List[Dict[str, Any]]:
    logger.info(f"Extraindo lista '{list_name}' (Pág: {page_size})...")
    try:
        target_list = ctx.web.lists.get_by_title(list_name)
        items: ListItemCollection = target_list.items.paged(page_size).get().execute_query()
        
        all_data = []
        batch_count = 0
        for item in items:
            all_data.append(item.properties)
            if len(all_data) % page_size == 0:
                batch_count += 1
                logger.info(f"Lote {batch_count}: {len(all_data)} itens...")

        logger.info(f"Total extraído: {len(all_data)} registros.")
        return all_data
    except Exception as e:
        logger.error(f"Erro na extração: {e}")
        raise

def clean_and_profile_data(raw_data: List[Dict[str, Any]]) -> pd.DataFrame:
    logger.info("Iniciando limpeza técnica...")
    if not raw_data:
        return pd.DataFrame()

    df = pd.DataFrame(raw_data)
    
    # Remove colunas técnicas e de mídia/assinatura
    cols_to_drop = [c for c in df.columns if c.startswith('odata.') or c.startswith('__')] 
    system_cols = [
        'FileSystemObjectType', 'ServerRedirectedEmbedUri', 'ServerRedirectedEmbedUrl', 
        'ContentTypeId', 'ComplianceAssetId', 'ID', 'Attachments',
        'AssRespAlmoxarifado', 'AssRespSaque', 'GUID', 'OData__ColorTag'
    ]
    cols_to_drop.extend([c for c in system_cols if c in df.columns])
    
    df.drop(columns=cols_to_drop, inplace=True, errors='ignore')
    
    # Converte datas
    for col in ['Created', 'Modified']:
        if col in df.columns:
            df.loc[:, col] = pd.to_datetime(df[col], errors='coerce')

    df = df.copy().convert_dtypes()

    # Log de perfilamento simples
    logger.info(f"Dimensões finais: {df.shape}")
    logger.info(f"Colunas: {list(df.columns)}")
    return df

def apply_business_rules(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica regras de negócio e sanitização de valores.
    NOTA: Assume que as colunas JÁ FORAM PADRONIZADAS pela função standardize_columns.
    """
    logger.info("Aplicando regras de negócio e sanitização...")

    # 1. Unificação de IDSolic (Granularidade: obra + TipoSolic + Created)
    # Nomes atualizados pós-padronização
    group_cols = ['obra', 'TipoSolic', 'Created']
    if set(group_cols).issubset(df.columns) and 'IdSolic' in df.columns:
        logger.info(f"Unificando IdSolic baseado em: {group_cols}")
        df['IdSolic'] = df.groupby(group_cols, dropna=False)['IdSolic'].transform('max')

    # 2. Filtro de Integridade: Remove registros sem IdSolic
    if 'IdSolic' in df.columns:
        initial_rows = df.shape[0]
        df.dropna(subset=['IdSolic'], inplace=True)
        dropped_rows = initial_rows - df.shape[0]
        if dropped_rows > 0:
            logger.info(f"Removidos {dropped_rows} registros sem 'IdSolic' válido.")

    # 2.1. Conversão de Quantidades (CRÍTICO: Evita concatenação de strings)
    if 'QuantSolic' in df.columns:
        initial_rows = df.shape[0]
        df['QuantSolic'] = pd.to_numeric(df['QuantSolic'], errors='coerce')
        df.dropna(subset=['QuantSolic'], inplace=True)
        dropped_invalid = initial_rows - df.shape[0]
        if dropped_invalid > 0:
            logger.warning(f"Removidos {dropped_invalid} registros com 'QuantSolic' não numérico.")

    if 'Quant_Confirmada' in df.columns:
        df['Quant_Confirmada'] = pd.to_numeric(df['Quant_Confirmada'], errors='coerce').fillna(0)

    # 3. Sanitização de NumeroReserva
    if 'NumeroReserva' in df.columns:
        logger.info("Sanitizando NumeroReserva: mantendo apenas valores numéricos...")
        df['NumeroReserva'] = pd.to_numeric(df['NumeroReserva'], errors='coerce')

    # 4. Normalização de Texto (Title Case)
    cols_to_normalize = [
        'titulo', 'Descricao', 'Observacao', 'StatusSolic', 
        'Coleborador_solicitante', 'AgenteResponsavel', 'obra', 
        'BaseOperacional', 'Pendencias', 'DescricaoPendencias', 
        'isUrgente', 'IsDeleted'
    ]
    found_cols = [c for c in cols_to_normalize if c in df.columns]
    
    if found_cols:
        logger.info(f"Normalizando texto (Title Case) nas colunas: {found_cols}")
        for col in found_cols:
            df[col] = df[col].astype(str).str.title().str.strip()
            df.loc[df[col].str.lower() == 'nan', col] = ''

    # 5. Normalização de Obra (Remoção de prefixo B-)
    if 'obra' in df.columns:
        logger.info("Normalizando coluna 'obra' (Limpando espaços e prefixo B-)...")
        # Limpeza inicial
        df['obra'] = df['obra'].astype(str).str.strip().str.replace(r'^[Bb]-', '', regex=True).str.strip()
        
        # Conversão para numérico e remoção de inválidos
        initial_rows = df.shape[0]
        df['obra'] = pd.to_numeric(df['obra'], errors='coerce')
        df.dropna(subset=['obra'], inplace=True)
        
        dropped_invalid = initial_rows - df.shape[0]
        if dropped_invalid > 0:
            logger.warning(f"Removidos {dropped_invalid} registros com 'obra' não numérica.")

    # 6. Padronização de StatusSolic
    if 'StatusSolic' in df.columns:
        logger.info("Padronizando status na coluna StatusSolic...")
        status_map = {
            'Confirmado': 'Movimentado',
            'Mov Parcial': 'Mov. Parcial',
            'Mov.Parcial': 'Mov. Parcial'
        }
        df['StatusSolic'] = df['StatusSolic'].replace(status_map)

    # 7. Remove colunas totalmente vazias
    initial_cols = df.shape[1]
    df.dropna(axis=1, how='all', inplace=True)
    dropped = initial_cols - df.shape[1]
    if dropped > 0:
        logger.info(f"Removidas {dropped} colunas que estavam 100% vazias.")

    return df

def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Padroniza o nome das colunas conforme solicitado.
    """
    logger.info("Padronizando nomes das colunas...")
    
    mapping = {
        'PROJETO': 'obra',
        'CODIGO': 'CodMaterial',
        'DESCRICAO_MATERIAL': 'MaterialSolic',
        'BASE': 'BaseOperacional',
        'TIPO_MOVIMENTACAO': 'TipoSolic',
        'STATUS': 'StatusSolic',
        'DATA_CRIACAOCOELBA': 'DataCriacaoReserva',
        'NUMERO_RESERVA': 'NumeroReserva',
        'DATA_SOLICITACAO': 'DataSolic',
        'QUANTIDADE_SOLICITADA': 'QuantSolic',
        'QUANTIDADE_MOVIMENTADA': 'Quant_Confirmada',
        'IDSolic': 'IdSolic',
        'Titulo': 'titulo',
        'DataMovimentacao': 'DataSaqMod',
        'TECNICO': 'Coleborador_solicitante',
        'Urgente': 'isUrgente',
        'OBSERVACAO_MAT': 'Observacao',
        'Descri_x00e7__x00e3_oPendencias': 'DescricaoPendencias'
    }
    
    df = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
    return df

def create_reservas_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gera uma visão consolidada da Tabela Reservas por IdSolic.
    """
    logger.info("Gerando tabela agrupada por IdSolic (Reservas)...")
    
    if df.empty or 'IdSolic' not in df.columns:
        return pd.DataFrame()

    def resolve_status(series):
        statuses = set(s.strip() for s in series.astype(str) if s.strip() and s.lower() != 'nan')
        if not statuses: return ''
        if 'Mov. Parcial' in statuses: return 'Mov. Parcial'
        if len(statuses) == 1:
            return list(statuses)[0]
        return 'Misto/Em Análise'

    agg_rules = {
        'StatusSolic': resolve_status,
        'QuantSolic': 'sum',
        'Quant_Confirmada': 'sum'
    }
    
    # Metadados: pega o primeiro valor
    metadata_cols = ['obra', 'BaseOperacional', 'TipoSolic', 'titulo', 'DataSolic', 'DataCriacaoReserva']
    for col in metadata_cols:
        if col in df.columns:
            agg_rules[col] = 'first'
            
    # Datas: pega a mínima
    date_cols = [c for c in df.columns if 'Data' in c or c in ['Created', 'Modified']]
    for col in date_cols:
        if col not in agg_rules:
            agg_rules[col] = 'min'

    df_grouped = df.groupby('IdSolic', as_index=False).agg(agg_rules)
    return df_grouped

def consolidate_all_data(df_reservas: pd.DataFrame, root_dir: Path) -> pd.DataFrame:
    """
    Lê materiais_obra_raw.csv, combina com reservas e gera o consolidado geral.
    Corrige automaticamente colunas duplicadas (ex: Quant_x002e_Confirmada vs Quant_Confirmada).
    """
    logger.info("Iniciando consolidação geral (Materiais + Reservas)...")
    
    materiais_path = root_dir / "materiais_obra/data/raw/materiais_obra_raw.csv"
    if not materiais_path.exists():
        logger.warning(f"Arquivo de materiais não encontrado: {materiais_path}")
        return pd.DataFrame()

    df_mat = pd.read_csv(materiais_path, sep=';', encoding='utf-8-sig')
    
    # Padronização de nomes em Materiais para facilitar o merge
    mat_mapping = {
        'Quant_x002e_Confirmada': 'Quant_Confirmada',
        'Coleborador_solicitante': 'Solicitante',
        'IdSolic': 'IdSolic'
    }
    df_mat = df_mat.rename(columns=mat_mapping)

    # Concatena as duas tabelas
    df_all = pd.concat([df_mat, df_reservas], ignore_index=True)

    # Garantia de que QuantSolic é numérica e válida após o merge
    if 'QuantSolic' in df_all.columns:
        df_all['QuantSolic'] = pd.to_numeric(df_all['QuantSolic'], errors='coerce')
        df_all.dropna(subset=['QuantSolic'], inplace=True)

    # --- CORREÇÃO DE COLUNAS DUPLICADAS/OVERLAP ---
    overlap_mapping = {
        'Quant_x002e_Confirmada': 'Quant_Confirmada',
        'QUANTIDADE_MOVIMENTADA': 'Quant_Confirmada',
        'QUANTIDADE_SOLICITADA': 'QuantSolic',
        'PROJETO': 'obra',
        'TIPO_MOVIMENTACAO': 'TipoSolic',
        'STATUS': 'StatusSolic',
        'Status': 'StatusSolic' # Alguns campos podem vir como Status
    }
    
    for old_col, new_col in overlap_mapping.items():
        if old_col in df_all.columns and old_col != new_col:
            logger.info(f"Mesclando coluna redundante: {old_col} -> {new_col}")
            df_all[new_col] = df_all[new_col].fillna(df_all[old_col])
            df_all.drop(columns=[old_col], inplace=True)

    # Agrupamento Final por IdSolic
    logger.info("Agrupando base consolidada geral...")
    
    def resolve_status_geral(series):
        statuses = set(s.strip() for s in series.astype(str) if s.strip() and s.lower() != 'nan')
        if 'Mov. Parcial' in statuses: return 'Mov. Parcial'
        # Se tem itens Pendentes e Movimentados no mesmo ID, é Parcial
        if ('Pendente' in statuses or 'Reservado' in statuses) and 'Movimentado' in statuses: 
            return 'Mov. Parcial'
        if 'Movimentado' in statuses: return 'Movimentado'
        return list(statuses)[0] if statuses else 'Pendente'

    agg_rules = {
        'QuantSolic': 'sum',
        'Quant_Confirmada': 'sum',
        'StatusSolic': resolve_status_geral
    }

    # Metadados e Datas
    for col in df_all.columns:
        if col in ['IdSolic', 'QuantSolic', 'Quant_Confirmada', 'StatusSolic']: continue
        if df_all[col].dtype == 'object' or df_all[col].dtype == 'string':
            agg_rules[col] = 'first'
        else:
            agg_rules[col] = 'max' # Para datas e números

    df_final = df_all.groupby('IdSolic', as_index=False).agg(agg_rules)
    
    return df_final

def main():
    logger.info("=== Pipeline ETL Iniciado (TabelaReservas) ===")
    
    try:
        # 1. Carrega e Valida Ambiente
        load_environment_variables()
        root_dir = Path(__file__).resolve().parents[2]

        # 2. Conexão
        ctx = get_sharepoint_context(SHAREPOINT_SITE_URL)
        
        # 3. Extração
        raw_data = extract_list_items_paged(ctx, SHAREPOINT_LIST_NAME)
        
        # 4. Transformação
        df_raw = clean_and_profile_data(raw_data)
        df_standard = standardize_columns(df_raw)
        df_treated = apply_business_rules(df_standard)
        
        # 5. Carga Raw Reservas
        output_dir_raw = root_dir / "materiais_obra/data/raw"
        output_dir_raw.mkdir(parents=True, exist_ok=True)
        output_path_raw = output_dir_raw / "tabela_reservas_raw.csv"
        
        if not df_treated.empty:
            df_treated.to_csv(output_path_raw, index=False, sep=';', encoding='utf-8-sig')
            logger.info(f"Arquivo Raw Reservas salvo: {output_path_raw}")

            # 6. Agrupamento Reservas
            df_grouped_res = create_reservas_summary(df_treated)
            output_dir_proc = root_dir / "materiais_obra/data/processed"
            output_dir_proc.mkdir(parents=True, exist_ok=True)
            df_grouped_res.to_csv(output_dir_proc / "tabela_reservas_agrupada.csv", index=False, sep=';', encoding='utf-8-sig')
            logger.info("Tabela de reservas agrupada salva.")

            # 7. Consolidação Geral (Materiais + Reservas)
            df_consolidated = consolidate_all_data(df_treated, root_dir)
            if not df_consolidated.empty:
                df_consolidated.to_csv(output_dir_proc / "solicitacoes_consolidadas_geral.csv", index=False, sep=';', encoding='utf-8-sig')
                logger.info("Consolidado geral (Materiais + Reservas) salvo.")
        else:
            logger.warning("DataFrame vazio. Nenhum arquivo salvo.")

    except KeyboardInterrupt:
        logger.warning("Cancelado pelo usuário.")
    except Exception as e:
        logger.critical(f"Erro não tratado: {e}")
        raise

if __name__ == "__main__":
    main()

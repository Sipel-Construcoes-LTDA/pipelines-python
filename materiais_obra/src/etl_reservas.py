import os
import sys
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
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

def clean_pendency_tags(text: Any) -> str:
    """
    Limpa e remove duplicatas de tags de pendências (ex: 'Outro; Outro' -> 'Outro').
    """
    if pd.isna(text) or str(text).lower() in ['nan', '<na>', 'none', '']:
        return ""
    
    # Divide por ; ou , e limpa cada parte
    parts = [p.strip().title() for p in str(text).replace(',', ';').split(';') if p.strip()]
    # Remove duplicatas mantendo ordem alfabética - USANDO VÍRGULA para não quebrar o CSV
    return ", ".join(sorted(list(set(parts))))

def clean_and_profile_data(raw_data: List[Dict[str, Any]]) -> pd.DataFrame:
    logger.info("Iniciando limpeza técnica...")
    if not raw_data:
        return pd.DataFrame()

    df = pd.DataFrame(raw_data)
    
    # Remove colunas técnicas e de mídia/assinatura
    cols_to_drop = [c for c in df.columns if c.startswith('odata.') or c.startswith('__')] 
    system_cols = [
        'FileSystemObjectType', 'ServerRedirectedEmbedUri', 'ServerRedirectedEmbedUrl', 
        'ContentTypeId', 'ComplianceAssetId', 'Attachments',
        'AssRespAlmoxarifado', 'AssRespSaque', 'GUID', 'OData__ColorTag', 'OData__UIVersionString'
    ]
    cols_to_drop.extend([c for c in system_cols if c in df.columns])
    
    df.drop(columns=cols_to_drop, inplace=True, errors='ignore')
    
    # Validação Crítica: A coluna 'Id' (ou 'ID') é obrigatória
    id_col = 'Id' if 'Id' in df.columns else ('ID' if 'ID' in df.columns else None)
    if id_col:
        initial_rows = len(df)
        df[id_col] = df[id_col].astype(str).replace(['nan', 'NaN', 'None', ''], pd.NA)
        df.dropna(subset=[id_col], inplace=True)
        dropped_ids = initial_rows - len(df)
        if dropped_ids > 0:
            logger.warning(f"Removidos {dropped_ids} registros com '{id_col}' em branco.")
    else:
        logger.error("Coluna de Identificação (Id/ID) não encontrada no DataFrame!")

    # Converte datas de forma proativa (Ignorando colunas técnicas já removidas)
    date_candidates = ['Created', 'Modified']
    date_candidates.extend([col for col in df.columns if ('Data' in col or 'DATE' in col.upper()) and col not in system_cols])
    
    found_dates = [c for c in set(date_candidates) if c in df.columns]
    if found_dates:
        logger.info(f"Convertendo colunas de data: {found_dates}")
        for col in found_dates:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.normalize()

    # Renomeia DataRegularisado para DataRegularizacao se existir
    if 'DataRegularisado' in df.columns:
        df.rename(columns={'DataRegularisado': 'DataRegularizacao'}, inplace=True)

    # Log de perfilamento simples
    logger.info(f"Dimensões finais: {df.shape}")
    return df

def apply_business_rules(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica regras de negócio e sanitização de valores.
    """
    logger.info("Aplicando regras de negócio e sanitização...")

    # 1. Regra de DataSolicPrev para Encerramento (Solicitação do Usuário)
    if 'Created' in df.columns:
        df['Created_Date'] = pd.to_datetime(df['Created']).dt.normalize()

    if 'DataCriacaoReserva' in df.columns:
        # Se DataSolicPrev estiver vazia, usa DataCriacaoReserva
        if 'DataSolicPrev' not in df.columns:
            df['DataSolicPrev'] = df['DataCriacaoReserva']
        else:
            df['DataSolicPrev'] = df['DataSolicPrev'].fillna(df['DataCriacaoReserva'])

    # 1.1 Unificação de IDSolic (APENAS PARA ENCERRAMENTO - Granularidade: obra + TipoSolic + Created_Date + NumeroReserva)
    df['Processo'] = 'Encerramento' # Define o processo antes da unificação
    
    # Limpeza preventiva de 'obra' para garantir agrupamento correto
    if 'obra' in df.columns:
        df['obra'] = df['obra'].astype(str).str.strip().str.replace(r'^[Bb]-', '', regex=True).str.strip()

    group_cols = ['obra', 'TipoSolic', 'Created_Date', 'NumeroReserva']
    group_cols = [c for c in group_cols if c in df.columns]
    
    if len(group_cols) >= 3 and 'IdSolic' in df.columns:
        logger.info(f"Padronizando IdSolic (Processo: Encerramento) com prefixo ENC- baseado em: {group_cols}")
        
        # Garante que NumeroReserva tenha um fallback se for nulo
        reserva_serie = df['NumeroReserva'].astype(str).replace(['nan', 'NaN', 'None', '<NA>', ''], 'S-RES')
        
        # DEFINITIVO: Para Encerramento, ignoramos o ID original (UUID) e geramos o ID baseado na chave de negócio.
        df['IdSolic'] = (
            "ENC-" + 
            df['Created_Date'].dt.strftime('%Y%m%d') + "-" + 
            df['obra'].astype(str) + "-" +
            df['TipoSolic'].astype(str) + "-" +
            reserva_serie
        )
    
    # Remove coluna auxiliar
    if 'Created_Date' in df.columns:
        df.drop(columns=['Created_Date'], inplace=True)

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

    # 3.5 TRATAMENTO DE PENDÊNCIAS (DEDUP E LIMPEZA)
    if 'Pendencias' in df.columns:
        logger.info("Limpando e deduplicando tags de Pendencias...")
        df['Pendencias'] = df['Pendencias'].apply(clean_pendency_tags)

    # 4. Normalização de Texto (Title Case)
    cols_to_normalize = [
        'titulo', 'Descricao', 'Observacao', 'StatusSolic', 
        'Coleborador_solicitante', 'AgenteResponsavel', 'obra', 
        'BaseOperacional', 'DescricaoPendencias', 
        'isUrgente', 'IsDeleted'
    ]
    found_cols = [c for c in cols_to_normalize if c in df.columns]
    
    if found_cols:
        logger.info(f"Normalizando texto (Title Case) nas colunas: {found_cols}")
        for col in found_cols:
            df[col] = df[col].astype(str).str.title().str.strip()
            df.loc[df[col].str.lower().isin(['nan', 'nat', 'none', '<na>', '']), col] = ''

    # 5. Normalização de Obra (Remoção de prefixo B-)
    if 'obra' in df.columns:
        logger.info("Normalizando coluna 'obra' (Limpando espaços e prefixo B-)...")
        # Limpeza inicial
        df['obra'] = df['obra'].astype(str).str.strip().str.replace(r'^[Bb]-', '', regex=True).str.strip()
        
        # Conversão para numérico e remoção de inválidos
        initial_rows = df.shape[0]
        df['obra'] = pd.to_numeric(df['obra'], errors='coerce')
        df.dropna(subset=['obra'], inplace=True)
        
        # Garante int64 para evitar .0 no CSV
        df['obra'] = df['obra'].round().astype('Int64')
        
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

    # 8. Conversão de Tipos Inteiros Adicionais
    int_cols = ['NumeroReserva', 'CodMaterial', 'TipoSolic', 'CENTRO_MATERIAL', 'idCoordenador', 'idSupervisor']
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').round().astype('Int64')

    # 9. Identificação do Processo
    df['Processo'] = 'Encerramento'

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
        'DataMovimentacao': 'DataSolicMod',
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
        # Limpa e padroniza os status para análise
        statuses = set(s.strip().title() for s in series.astype(str) 
                       if s.strip() and s.lower() not in ['nan', 'none', 'nat'])
        
        if not statuses: 
            return 'Pendente'
            
        # 1. Prioridade Máxima: Mov. Parcial
        # Se houver qualquer indicação de parcialidade, o grupo todo assume esse status
        if any('Parcial' in s for s in statuses):
            return 'Mov. Parcial'
            
        # 2. Segunda Prioridade: Movimentado ou Confirmado
        # Se todos ou alguns forem movimentados (e não houver Parcial), priorizamos Movimentado
        if any(s in ['Movimentado', 'Confirmado'] for s in statuses):
            # Se tiver Movimentado e também tiver Pendente no mesmo ID agrupado, vira Parcial
            if any('Pendente' in s or 'Reservado' in s for s in statuses):
                return 'Mov. Parcial'
            return 'Movimentado'
            
        # 3. Terceira Prioridade: Pendente
        if any(s in ['Pendente', 'Reservado'] for s in statuses):
            return 'Pendente'
            
        # Fallback para o primeiro status encontrado se for algo fora do padrão
        return sorted(list(statuses))[0] if statuses else 'Pendente'

    def agg_pendencias(series):
        all_p = "; ".join([str(s) for s in series if pd.notna(s) and str(s).strip()])
        return clean_pendency_tags(all_p)

    def agg_descriptions(series):
        descs = [str(s).strip() for s in series if pd.notna(s) and str(s).strip() and str(s).lower() not in ['nan', 'none', '<na>', '']]
        return " | ".join(sorted(list(set(descs))))

    agg_rules = {
        'StatusSolic': resolve_status,
        'QuantSolic': 'sum',
        'Quant_Confirmada': 'sum',
        'Pendencias': agg_pendencias,
        'DescricaoPendencias': agg_descriptions
    }
    
    # Metadados: pega o primeiro valor
    metadata_cols = ['obra', 'BaseOperacional', 'TipoSolic', 'titulo', 'DataSolic', 'DataCriacaoReserva', 'Processo']
    for col in metadata_cols:
        if col in df.columns:
            agg_rules[col] = 'first'
            
    # Datas: pega a mínima (Garante conversão para datetime para evitar erro de agg no pandas)
    date_cols = [c for c in df.columns if 'Data' in c or c in ['Created', 'Modified']]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors='coerce')
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

    # Lê o CSV e tenta converter colunas de data conhecidas
    df_mat = pd.read_csv(materiais_path, sep=';', encoding='utf-8-sig', low_memory=False)
    
    # Padronização de nomes em Materiais para facilitar o merge
    mat_mapping = {
        'Quant_x002e_Confirmada': 'Quant_Confirmada',
        'Coleborador_solicitante': 'Solicitante',
        'IdSolic': 'IdSolic'
    }
    df_mat = df_mat.rename(columns=mat_mapping)

    # Concatena as duas tabelas
    df_all = pd.concat([df_mat, df_reservas], ignore_index=True)

    # --- CORREÇÃO DE COLUNAS DE DATA (CRÍTICO) ---
    # Garante que todas as colunas de data sejam datetime após a concatenação
    date_cols = [c for c in df_all.columns if 'Data' in c or c in ['Created', 'Modified']]
    for col in date_cols:
        # Usamos utc=True para lidar com mixed offsets do SharePoint/Pandas 2.0+
        # E convertemos para tz-naive (removendo o UTC) para consistência no CSV
        df_all[col] = pd.to_datetime(df_all[col], errors='coerce', utc=True).dt.tz_localize(None).dt.normalize()

    # --- UNIFICAÇÃO DE IDSOLIC NO CONSOLIDADO (ENCERRAMENTO) ---
    if 'Created' in df_all.columns:
        df_all['Created_Date_Temp'] = pd.to_datetime(df_all['Created']).dt.normalize()
        
        # Só unifica para Encerramento (Reservas)
        mask_enc = df_all['Processo'] == 'Encerramento'
        if mask_enc.any():
            logger.info("Padronizando IdSolic na base consolidada (Encerramento) com prefixo ENC-...")
            # Garante limpeza de obra
            df_all.loc[mask_enc, 'obra'] = df_all.loc[mask_enc, 'obra'].astype(str).str.strip().str.replace(r'^[Bb]-', '', regex=True).str.strip()
            
            # DEFINITIVO: Para Encerramento, ignoramos o ID original e geramos o ID baseado na chave de negócio.
            reserva_serie = df_all.loc[mask_enc, 'NumeroReserva'].astype(str).replace(['nan', 'NaN', 'None', '<NA>', ''], 'S-RES')
            
            df_all.loc[mask_enc, 'IdSolic'] = (
                "ENC-" + 
                df_all.loc[mask_enc, 'Created_Date_Temp'].dt.strftime('%Y%m%d') + "-" + 
                df_all.loc[mask_enc, 'obra'].astype(str) + "-" +
                df_all.loc[mask_enc, 'TipoSolic'].astype(str) + "-" +
                reserva_serie
            )

        df_all.drop(columns=['Created_Date_Temp'], inplace=True)

    # Garantia extra para DataRegularizacao
    if 'DataRegularizacao' in df_all.columns:
        df_all['DataRegularizacao'] = pd.to_datetime(df_all['DataRegularizacao'], errors='coerce')

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

    # Garante Int64 para colunas de ID antes do agrupamento
    int_cols_final = ['obra', 'CodMaterial', 'TipoSolic', 'CENTRO_MATERIAL', 'NumeroReserva', 'idCoordenador', 'idSupervisor', 'AuthorId', 'EditorId', 'OData__UIVersionString']
    for col in int_cols_final:
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(df_all[col], errors='coerce').astype('Int64')

    # Agrupamento Final por IdSolic
    logger.info("Agrupando base consolidada geral...")
    
    def resolve_status_geral(series):
        # Limpa e padroniza os status para análise
        statuses = set(s.strip().title() for s in series.astype(str) 
                       if s.strip() and s.lower() not in ['nan', 'none', 'nat'])
        
        if not statuses: 
            return 'Pendente'
            
        # 1. Prioridade Máxima: Mov. Parcial
        if any('Parcial' in s for s in statuses):
            return 'Mov. Parcial'
            
        # 2. Segunda Prioridade: Movimentado ou Confirmado
        if any(s in ['Movimentado', 'Confirmado'] for s in statuses):
            # Se tiver Movimentado e também tiver Pendente no mesmo ID agrupado, vira Parcial
            if any('Pendente' in s or 'Reservado' in s for s in statuses):
                return 'Mov. Parcial'
            return 'Movimentado'
            
        # 3. Terceira Prioridade: Pendente
        if any(s in ['Pendente', 'Reservado'] for s in statuses):
            return 'Pendente'
            
        return sorted(list(statuses))[0] if statuses else 'Pendente'

    def agg_pendencias(series):
        all_p = "; ".join([str(s) for s in series if pd.notna(s) and str(s).strip()])
        return clean_pendency_tags(all_p)

    def agg_descriptions(series):
        descs = [str(s).strip() for s in series if pd.notna(s) and str(s).strip() and str(s).lower() not in ['nan', 'none', '<na>', '']]
        return " | ".join(sorted(list(set(descs))))

    agg_rules = {
        'QuantSolic': 'sum',
        'Quant_Confirmada': 'sum',
        'StatusSolic': resolve_status_geral,
        'Pendencias': agg_pendencias,
        'DescricaoPendencias': agg_descriptions
    }

    # Metadados e Datas: Define regras seguras para as demais colunas
    for col in df_all.columns:
        if col in agg_rules or col == 'IdSolic':
            continue
            
        # Para datas (incluindo DataCriacaoReserva), usamos 'max' (última atualização)
        if 'Data' in col or col in ['Created', 'Modified']:
            agg_rules[col] = 'max'
        # Para números (obra, códigos, etc), usamos 'max' ou 'first'
        elif pd.api.types.is_numeric_dtype(df_all[col]):
            agg_rules[col] = 'max'
        # Para todo o resto (strings, objetos), usamos 'first'
        else:
            agg_rules[col] = 'first'

    # Garante que colunas de data críticas usem 'max' se existirem
    critical_date_cols = ['DataCriacaoReserva', 'DataSolicMod', 'DataPendencia', 'DataRegularizacao']
    for col in critical_date_cols:
        if col in df_all.columns:
            agg_rules[col] = 'max'

    df_final = df_all.groupby('IdSolic', as_index=False).agg(agg_rules)
    
    # --- TRATAMENTOS FINAIS (REPLICANDO POWER QUERY DO USUÁRIO) ---
    logger.info("Aplicando tratamentos finais solicitados (Power Query Migration)...")
    
    # 1. Remoção de colunas indesejadas
    cols_to_remove = [
        'LatitudeSolic', 'LongetudeSolic', 'Id', '', '_1', '_2', '_3',
        'GUID', 'MOTIVO_EXCLUSAO', 'AVALIACAO_MATERIAL', 'CENTRO_MATERIAL',
        'RECEBEDOR', 'SUPR_MATR', 'AuthorId', 'EditorId',
        'IsAvulso', 'isUrgente', 'Observacao', 'MotivoRejSolic',
        'ID', 'DATA_CRIACAO', 'DataEstorno'
    ]
    df_final.drop(columns=[c for c in cols_to_remove if c in df_final.columns], inplace=True, errors='ignore')

    # 2. Tratamento de IsDeleted e Filtro (Somente False)
    if 'IsDeleted' in df_final.columns:
        # Mapeamento robusto para booleano (logical)
        df_final['IsDeleted'] = df_final['IsDeleted'].astype(str).str.lower().map({
            '0': False, '0.0': False, 'false': False, 'false': False,
            '1': True, '1.0': True, 'true': True, 'true': True
        }).fillna(False)
        
        # Filtra apenas o que não foi deletado (IsDeleted = false)
        df_final = df_final[df_final['IsDeleted'] == False].copy()
        
        # Converte para tipo booleano explicitamente
        df_final['IsDeleted'] = df_final['IsDeleted'].astype(bool)

    # 3. Padronização de StatusSolic
    if 'StatusSolic' in df_final.columns:
        status_replacements = {
            'Confirmado': 'Movimentado',
            'Reservado': 'Pendente',
            'Deletado': 'Rejeitado',
            'Estornado': 'Rejeitado'
        }
        df_final['StatusSolic'] = df_final['StatusSolic'].replace(status_replacements)

    # 4. Formatação de Titulo (Proper Case / Cada Palavra em Maiúscula)
    if 'titulo' in df_final.columns:
        df_final['titulo'] = df_final['titulo'].astype(str).str.title().str.strip()
        # Limpa eventuais 'Nan' que viraram string
        df_final.loc[df_final['titulo'].str.lower() == 'nan', 'titulo'] = ""

    # 5. Limpeza de Linhas em Branco e Erros em QuantSolic
    # Equivalente ao Table.RemoveRowsWithErrors e Table.SelectRows(not List.IsEmpty)
    if 'QuantSolic' in df_final.columns:
        df_final['QuantSolic'] = pd.to_numeric(df_final['QuantSolic'], errors='coerce')
        df_final.dropna(subset=['QuantSolic'], inplace=True)

    # Remove linhas que sejam inteiramente vazias ou apenas com strings vazias
    # (Simulando o List.RemoveMatchingItems do Power Query)
    temp_df = df_final.replace('', np.nan)
    df_final = df_final[temp_df.notna().any(axis=1)].copy()

    # --- SANITIZAÇÃO FINAL DE STRINGS (CRÍTICO: ANTI-SHIFTING) ---
    logger.info("Sanitizando campos de texto (Removendo ';' e quebras de linha)...")
    # Seleciona apenas colunas 'object' que não são identificadas como data
    text_cols = [c for c in df_final.select_dtypes(include=['object']).columns 
                 if not ('Data' in c or c in ['Created', 'Modified'])]
    
    for col in text_cols:
        df_final[col] = df_final[col].astype(str).str.replace(';', ',', regex=False).str.replace('\n', ' ', regex=False).str.replace('\r', '', regex=False).str.strip()
        df_final.loc[df_final[col].str.lower().isin(['nan', 'none', 'nat', '']), col] = ''

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
            df_treated.to_csv(output_path_raw, index=False, sep=';', encoding='utf-8-sig', date_format='%Y-%m-%d')
            logger.info(f"Arquivo Raw Reservas salvo: {output_path_raw}")

            # 6. Agrupamento Reservas
            df_grouped_res = create_reservas_summary(df_treated)
            output_dir_proc = root_dir / "materiais_obra/data/processed"
            output_dir_proc.mkdir(parents=True, exist_ok=True)
            df_grouped_res.to_csv(output_dir_proc / "tabela_reservas_agrupada.csv", index=False, sep=';', encoding='utf-8-sig', date_format='%Y-%m-%d', decimal=',')
            logger.info("Tabela de reservas agrupada salva.")

            # 7. Consolidação Geral (Materiais + Reservas)
            df_consolidated = consolidate_all_data(df_treated, root_dir)
            if not df_consolidated.empty:
                df_consolidated.to_csv(output_dir_proc / "solicitacoes_consolidadas_geral.csv", index=False, sep=';', encoding='utf-8-sig', date_format='%Y-%m-%d', decimal=',')
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

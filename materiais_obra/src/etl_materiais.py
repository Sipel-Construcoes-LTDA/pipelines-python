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
SHAREPOINT_LIST_NAME = "MateriaisObraSolic"

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
    # Remove duplicatas mantendo ordem alfabética
    return "; ".join(sorted(list(set(parts))))

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
        'AssRespAlmoxarifado', 'AssRespSaque'
    ]
    cols_to_drop.extend([c for c in system_cols if c in df.columns])
    
    df.drop(columns=cols_to_drop, inplace=True, errors='ignore')
    
    # Validação Crítica: A coluna 'Id' (ou 'ID') é obrigatória
    id_col = 'Id' if 'Id' in df.columns else ('ID' if 'ID' in df.columns else None)
    if id_col:
        initial_rows = len(df)
        # Remove nulos e strings vazias/nan
        df[id_col] = df[id_col].astype(str).replace(['nan', 'NaN', 'None', ''], pd.NA)
        df.dropna(subset=[id_col], inplace=True)
        dropped_ids = initial_rows - len(df)
        if dropped_ids > 0:
            logger.warning(f"Removidos {dropped_ids} registros com '{id_col}' em branco.")
    else:
        logger.error("Coluna de Identificação (Id/ID) não encontrada no DataFrame!")
    
    # Converte datas de forma proativa
    # Identifica colunas do SharePoint que são tipicamente datas ou contêm 'Data' ou 'Date' no nome
    date_candidates = ['Created', 'Modified']
    date_candidates.extend([col for col in df.columns if 'Data' in col or 'DATE' in col.upper()])
    
    found_dates = [c for c in set(date_candidates) if c in df.columns]
    if found_dates:
        logger.info(f"Convertendo colunas de data: {found_dates}")
        for col in found_dates:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.normalize()

    # Log de perfilamento simples
    logger.info(f"Dimensões finais: {df.shape}")
    return df

def apply_business_rules(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica regras de negócio específicas e sanitização de valores.
    """
    logger.info("Aplicando regras de negócio e sanitização...")

    # 1. Remove colunas totalmente vazias
    initial_cols = df.shape[1]
    df.dropna(axis=1, how='all', inplace=True)
    dropped = initial_cols - df.shape[1]
    if dropped > 0:
        logger.info(f"Removidas {dropped} colunas que estavam 100% vazias.")

    # 2. Tratamento de Quantidades (Outliers e Tipagem)
    # QuantSolic: Solicitada | Quant_x002e_Confirmada: Confirmada
    if 'QuantSolic' in df.columns:
        initial_rows = df.shape[0]
        df['QuantSolic'] = pd.to_numeric(df['QuantSolic'], errors='coerce')
        df.dropna(subset=['QuantSolic'], inplace=True)
        dropped_invalid = initial_rows - df.shape[0]
        if dropped_invalid > 0:
            logger.warning(f"Removidos {dropped_invalid} registros com 'QuantSolic' não numérico.")

    if 'Quant_x002e_Confirmada' in df.columns:
        df['Quant_x002e_Confirmada'] = pd.to_numeric(df['Quant_x002e_Confirmada'], errors='coerce').fillna(0)

    qty_cols = ['QuantSolic', 'Quant_x002e_Confirmada']
    for col in qty_cols:
        if col in df.columns:
            # Regra: Quantidade > 10.000 é erro de input
            outliers_mask = df[col] > 10000
            qtd_outliers = outliers_mask.sum()
            
            if qtd_outliers > 0:
                logger.warning(f"ALERTA: Coluna '{col}' possui {qtd_outliers} valores > 10.000 (Possível erro). Zerando valores.")
                # Exemplo de auditoria: Mostra os IDs dos primeiros 5 erros
                if 'Id' in df.columns:
                    ids_erro = df.loc[outliers_mask, 'Id'].head(5).tolist()
                    logger.warning(f"Exemplos de IDs com erro em '{col}': {ids_erro}")
                
                # Zera os valores inválidos
                df.loc[outliers_mask, col] = 0

    # 2.5 TRATAMENTO DE PENDÊNCIAS (DEDUP E LIMPEZA)
    if 'Pendencias' in df.columns:
        logger.info("Limpando e deduplicando tags de Pendencias...")
        df['Pendencias'] = df['Pendencias'].apply(clean_pendency_tags)

    # 3. Normalização de Texto (Title Case)
    # Lista de colunas candidatas baseada na solicitação e nomes reais do SharePoint
    cols_to_normalize = [
        'Coleborador_solicitante', 'IsDeleted', 'BaseOperacional', 
        'Observacao', 'isUrgente', 'AgenteResponsavel', 
        'DescricaoPendencias', 'Justificativa', 'Justificar'
    ]
    
    # Filtra apenas as que existem no DataFrame
    found_cols = [c for c in cols_to_normalize if c in df.columns]
    
    if found_cols:
        logger.info(f"Normalizando texto (Title Case) nas colunas: {found_cols}")
        for col in found_cols:
            # Converte para string, aplica Title Case e remove espaços extras
            df[col] = df[col].astype(str).str.title().str.strip()
            # Tratamento para 'nan' string que pode surgir de conversão de nulls
            df.loc[df[col].str.lower().isin(['nan', 'nat', 'none', '<na>', '']), col] = ''

    # 4. Tratamento da Coluna 'Obra'
    if 'obra' in df.columns:
        logger.info("Normalizando coluna 'obra' (Limpando espaços e prefixo B-)...")
        # Limpeza inicial de strings
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
        
        # Garante que não temos zeros ou vazios estatísticos se necessário (opcional)
        df = df[df['obra'] != 0].copy()

    # 5. Conversão de Tipos Inteiros Adicionais
    # Lista de colunas que devem ser inteiras se existirem
    int_cols = ['CodMaterial', 'TipoSolic', 'CENTRO_MATERIAL', 'AuthorId', 'EditorId', 'OData__UIVersionString']
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').round().astype('Int64')

    # 6. Identificação do Processo
    df['Processo'] = 'Obras'

    return df

def create_solicitations_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gera uma visão consolidada por Solicitação (IdSolic), aplicando regras de status e somas.
    """
    logger.info("Gerando tabela consolidada por Solicitação (IdSolic)...")

    # 1. Filtra removidos (IsDeleted != 'True')
    # Garante verificação case-insensitive
    if 'IsDeleted' in df.columns:
        mask_valid = df['IsDeleted'].astype(str).str.lower() != 'true'
        df_filtered = df[mask_valid].copy()
    else:
        df_filtered = df.copy()

    if df_filtered.empty:
        logger.warning("Nenhum dado válido disponível para agrupamento.")
        return pd.DataFrame()

    # 2. Definição da Lógica de Status
    def resolve_status(series):
        # Normaliza para garantir comparação limpa
        statuses = set(s.strip() for s in series.astype(str))

        # Regra 1: Prioridade absoluta para "Mov. Parcial"
        if 'Mov. Parcial' in statuses:
            return 'Mov. Parcial'

        # Regra 2: Uniformidade
        if len(statuses) == 1:
            unique_status = list(statuses)[0]
            if unique_status == 'Confirmado':
                return 'Movimentado'
            return unique_status

        # Regra 3: Fallback para estados mistos (ex: Pendente + Reservado)
        return 'Em Análise/Misto'

    # 2.5 Lógica de Agregação de Pendências
    def agg_pendencias(series):
        all_p = "; ".join([str(s) for s in series if pd.notna(s) and str(s).strip()])
        return clean_pendency_tags(all_p)

    def agg_descriptions(series):
        # Une as descrições únicas, separando por " | "
        descs = [str(s).strip() for s in series if pd.notna(s) and str(s).strip() and str(s).lower() not in ['nan', 'none', '<na>', '']]
        return " | ".join(sorted(list(set(descs))))

    # 3. Agrupamento
    
    # Colunas de Metadados (Texto/Categorias) -> 'first'
    # Inclui colunas solicitadas: EmailSolic, TipoSolic, titulo
    metadata_cols = [
        'Coleborador_solicitante', 'obra', 'BaseOperacional', 
        'isUrgente', 'AgenteResponsavel',
        'EmailSolic', 'TipoSolic', 'titulo', 'Titulo', 'Processo'
    ]
    
    # Colunas de Data -> 'min' (menor data)
    # Identifica colunas que parecem ser datas
    date_cols = [col for col in df_filtered.columns if 'Data' in col or col in ['Created', 'Modified']]

    agg_rules = {
        'StatusSolic': resolve_status,
        'Pendencias': agg_pendencias,
        'DescricaoPendencias': agg_descriptions
    }
    
    # Adiciona soma para colunas de quantidade se existirem
    if 'QuantSolic' in df_filtered.columns:
        agg_rules['QuantSolic'] = 'sum'
    if 'Quant_x002e_Confirmada' in df_filtered.columns:
        agg_rules['Quant_x002e_Confirmada'] = 'sum'

    # Adiciona rules para metadata (pega o primeiro valor encontrado no grupo)
    for col in metadata_cols:
        if col in df_filtered.columns:
            agg_rules[col] = 'first'

    # Adiciona rules para datas (menor data encontrada no grupo)
    for col in date_cols:
        # Evita sobrescrever se já estiver no metadata (embora improvável com nomes padrão)
        if col not in agg_rules: 
            agg_rules[col] = 'min'

    # Executa o GroupBy
    if 'IdSolic' not in df_filtered.columns:
        logger.error("Coluna 'IdSolic' não encontrada. Impossível agrupar.")
        return pd.DataFrame()

    df_grouped = df_filtered.groupby('IdSolic', as_index=False).agg(agg_rules)

    logger.info(f"Agrupamento concluído. {len(df_filtered)} linhas -> {len(df_grouped)} solicitações únicas.")
    return df_grouped

def main():
    logger.info("=== Pipeline ETL Iniciado ===")
    
    try:
        # 1. Carrega e Valida Ambiente
        load_environment_variables()

        # 2. Conexão
        ctx = get_sharepoint_context(SHAREPOINT_SITE_URL)
        
        # 3. Extração
        raw_data = extract_list_items_paged(ctx, SHAREPOINT_LIST_NAME)
        
        # 4. Transformação (Limpeza e Regras de Negócio)
        df_clean = clean_and_profile_data(raw_data)
        df_final = apply_business_rules(df_clean)
        
        # 5. Carga (Raw/Tratado nível item)
        output_dir_raw = Path("materiais_obra/data/raw")
        output_dir_raw.mkdir(parents=True, exist_ok=True)
        output_path_raw = output_dir_raw / "materiais_obra_raw.csv"
        
        df_final.to_csv(output_path_raw, index=False, sep=';', encoding='utf-8-sig', date_format='%Y-%m-%d')
        logger.info(f"Arquivo Raw salvo: {output_path_raw}")

        # 6. Agrupamento (Tabela Consolidada)
        df_grouped = create_solicitations_summary(df_final)
        
        if not df_grouped.empty:
            output_dir_processed = Path("materiais_obra/data/processed")
            output_dir_processed.mkdir(parents=True, exist_ok=True)
            output_path_processed = output_dir_processed / "solicitacoes_agrupadas.csv"
            
            df_grouped.to_csv(output_path_processed, index=False, sep=';', encoding='utf-8-sig', date_format='%Y-%m-%d')
            logger.info(f"Arquivo Agrupado salvo: {output_path_processed}")
        
    except KeyboardInterrupt:
        logger.warning("Cancelado pelo usuário.")
    except Exception as e:
        logger.critical(f"Erro não tratado: {e}")
        raise

if __name__ == "__main__":
    main()

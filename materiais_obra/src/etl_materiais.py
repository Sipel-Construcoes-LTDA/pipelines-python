import os
import sys
import logging
from typing import List, Dict, Any
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

# --- Configurações & Constantes ---
# Caminhos robustos baseados na localização do script
MODULE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = MODULE_ROOT.parent

SHAREPOINT_SITE_URL = "https://netorg2135259.sharepoint.com/sites/sipel.com.br"
SHAREPOINT_LIST_NAME = "MateriaisObraSolic"

def load_environment_variables() -> None:
    """
    Carrega variáveis de ambiente de forma robusta e exibe diagnóstico.
    """
    env_path = PROJECT_ROOT / '.env'
    logger.info(f"Carregando configurações de: {env_path}")
    
    if not env_path.exists():
        logger.critical(f"ARQUIVO .ENV NÃO ENCONTRADO EM: {env_path}")
        sys.exit("O script não conseguirá se autenticar sem o arquivo .env.")

    load_dotenv(dotenv_path=env_path, override=True)
    
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
    client_id = os.getenv("SHAREPOINT_CLIENT_ID")
    client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET")
    username = os.getenv("SHAREPOINT_USER")
    password = os.getenv("SHAREPOINT_PASSWORD")

    try:
        if client_id and client_secret:
            logger.info(f"Autenticando via App-Only (Client ID: ...{client_id[-4:] if client_id and len(client_id)>4 else '****'})")
            credentials = ClientCredential(client_id, client_secret)
            ctx = ClientContext(url).with_credentials(credentials)
        
        elif username and password:
            logger.warning("Autenticando via Usuário/Senha (Legado).")
            credentials = UserCredential(username, password)
            ctx = ClientContext(url).with_credentials(credentials)
            
        else:
            raise ValueError("Nenhuma credencial válida encontrada no .env para App-Only ou User/Password.")

        web = ctx.web
        ctx.load(web)
        ctx.execute_query()
        logger.info(f"Conexão SUCESSO: Site '{web.properties.get('Title')}'")
        return ctx

    except Exception as e:
        logger.critical(f"FALHA DE CONEXÃO: {e}", exc_info=True)
        sys.exit(1)

def extract_list_items_paged(ctx: ClientContext, list_name: str, page_size: int = 5000) -> List[Dict[str, Any]]:
    logger.info(f"Extraindo lista '{list_name}' (Pág: {page_size})...")
    try:
        target_list = ctx.web.lists.get_by_title(list_name)
        items: ListItemCollection = target_list.items.paged(page_size).get().execute_query()
        
        all_data = [item.properties for item in items]
        logger.info(f"Total extraído: {len(all_data)} registros.")
        return all_data
    except Exception as e:
        logger.error(f"Erro na extração da lista '{list_name}': {e}")
        raise

def clean_pendency_tags(text: Any) -> str:
    if pd.isna(text) or str(text).lower() in ['nan', '<na>', 'none', '']:
        return ""
    
    parts = [p.strip().title() for p in str(text).replace(',', ';').split(';') if p.strip()]
    return ", ".join(sorted(list(set(parts))))

def clean_and_profile_data(raw_data: List[Dict[str, Any]]) -> pd.DataFrame:
    logger.info("Iniciando limpeza técnica...")
    if not raw_data:
        return pd.DataFrame()

    df = pd.DataFrame(raw_data)
    
    cols_to_drop = [c for c in df.columns if c.startswith('odata.') or c.startswith('__')] 
    system_cols = ['FileSystemObjectType', 'ServerRedirectedEmbedUri', 'ServerRedirectedEmbedUrl', 'ContentTypeId', 'ComplianceAssetId', 'Attachments', 'AssRespAlmoxarifado', 'AssRespSaque']
    cols_to_drop.extend([c for c in system_cols if c in df.columns])
    df.drop(columns=cols_to_drop, inplace=True, errors='ignore')
    
    id_col = 'Id' if 'Id' in df.columns else 'ID' if 'ID' in df.columns else None
    if id_col:
        df[id_col] = df[id_col].astype(str).replace(['nan', 'NaN', 'None', ''], pd.NA)
        df.dropna(subset=[id_col], inplace=True)
    else:
        logger.error("Coluna de Identificação (Id/ID) não encontrada!")

    date_candidates = ['Created', 'Modified'] + [col for col in df.columns if 'Data' in col or 'DATE' in col.upper()]
    found_dates = [c for c in set(date_candidates) if c in df.columns]

    for col in found_dates:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.normalize()

    if 'DataRegularisado' in df.columns:
        df.rename(columns={'DataRegularisado': 'DataRegularizacao'}, inplace=True)

    logger.info(f"Dimensões finais: {df.shape}")
    return df

def apply_business_rules(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Aplicando regras de negócio e sanitização...")
    df.dropna(axis=1, how='all', inplace=True)

    for col in ['QuantSolic', 'Quant_x002e_Confirmada']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            outliers_mask = df[col] > 10000
            if outliers_mask.any():
                logger.warning(f"Coluna '{col}' possui {outliers_mask.sum()} valores > 10000. Zerando-os.")
                df.loc[outliers_mask, col] = 0

    if 'Pendencias' in df.columns:
        df['Pendencias'] = df['Pendencias'].apply(clean_pendency_tags)

    cols_to_normalize = ['Coleborador_solicitante', 'IsDeleted', 'BaseOperacional', 'Observacao', 'isUrgente', 'AgenteResponsavel', 'DescricaoPendencias', 'Justificativa', 'Justificar']
    for col in [c for c in cols_to_normalize if c in df.columns]:
        df[col] = df[col].astype(str).str.title().str.strip().replace({'Nan': '', 'Nat': '', 'None': '', '<Na>': ''}, regex=False)

    if 'obra' in df.columns:
        df['obra'] = df['obra'].astype(str).str.strip().str.replace(r'^[Bb]-', '', regex=True)
        df['obra'] = pd.to_numeric(df['obra'], errors='coerce').round().astype('Int64')
        df.dropna(subset=['obra'], inplace=True)
        df = df[df['obra'] != 0].copy()

    int_cols = ['CodMaterial', 'TipoSolic', 'CENTRO_MATERIAL', 'AuthorId', 'EditorId', 'OData__UIVersionString']
    for col in [c for c in int_cols if c in df.columns]:
        df[col] = pd.to_numeric(df[col], errors='coerce').round().astype('Int64')

    df['Processo'] = 'Obras'

    text_cols = df.select_dtypes(include=['object']).columns
    for col in text_cols:
        df[col] = df[col].astype(str).str.replace(';', ',', regex=False).str.replace(r'\s*\n\s*', ' ', regex=True).str.strip()
        df[col] = df[col].replace({'nan': '', 'None': '', 'nat': ''}, regex=False)

    return df

def create_solicitations_summary(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Gerando tabela consolidada por Solicitação (IdSolic)...")

    if 'IsDeleted' in df.columns:
        df = df[df['IsDeleted'].astype(str).str.lower() != 'true'].copy()

    if df.empty or 'IdSolic' not in df.columns:
        logger.error("Nenhum dado válido ou coluna 'IdSolic' não encontrada para agrupamento.")
        return pd.DataFrame()

    def resolve_status(series: pd.Series) -> str:
        statuses = set(s.strip() for s in series.astype(str) if pd.notna(s) and str(s).strip())
        if 'Mov. Parcial' in statuses:
            return 'Mov. Parcial'
        if len(statuses) == 1:
            status = statuses.pop()
            return 'Movimentado' if status == 'Confirmado' else status
        return 'Em Análise/Misto'

    def agg_text_unique(series: pd.Series) -> str:
        items = {str(s).strip() for s in series if pd.notna(s) and str(s).strip() and str(s).lower() not in ['nan', 'none', '<na>']}
        return " | ".join(sorted(items))
    
    metadata_cols = ['Coleborador_solicitante', 'obra', 'BaseOperacional', 'isUrgente', 'AgenteResponsavel', 'EmailSolic', 'TipoSolic', 'titulo', 'Titulo', 'Processo']
    date_cols = [col for col in df.columns if 'Data' in col or col in ['Created', 'Modified']]
    
    agg_rules = {
        'StatusSolic': resolve_status,
        'Pendencias': lambda s: clean_pendency_tags("; ".join(s.dropna().astype(str))),
        'DescricaoPendencias': agg_text_unique
    }
    
    for col in ['QuantSolic', 'Quant_x002e_Confirmada']:
        if col in df.columns:
            agg_rules[col] = 'sum'
    for col in metadata_cols:
        if col in df.columns:
            agg_rules[col] = 'first'
    for col in date_cols:
        if col not in agg_rules:
            agg_rules[col] = 'min'

    df_grouped = df.groupby('IdSolic', as_index=False).agg(agg_rules)
    logger.info(f"Agrupamento concluído: {len(df)} linhas -> {len(df_grouped)} solicitações únicas.")
    return df_grouped

def main() -> None:
    logger.info("=== Pipeline ETL de Materiais de Obra Iniciado ===")
    try:
        load_environment_variables()
        ctx = get_sharepoint_context(SHAREPOINT_SITE_URL)
        raw_data = extract_list_items_paged(ctx, SHAREPOINT_LIST_NAME)
        
        df_clean = clean_and_profile_data(raw_data)
        df_final = apply_business_rules(df_clean)
        
        output_dir_raw = MODULE_ROOT / "data" / "raw"
        output_dir_raw.mkdir(parents=True, exist_ok=True)
        output_path_raw = output_dir_raw / "materiais_obra_raw.csv"
        df_final.to_csv(output_path_raw, index=False, sep=';', encoding='utf-8-sig', date_format='%Y-%m-%d')
        logger.info(f"Arquivo Raw salvo: {output_path_raw}")

        df_grouped = create_solicitations_summary(df_final)
        if not df_grouped.empty:
            output_dir_processed = MODULE_ROOT / "data" / "processed"
            output_dir_processed.mkdir(parents=True, exist_ok=True)
            output_path_processed = output_dir_processed / "solicitacoes_agrupadas.csv"
            df_grouped.to_csv(output_path_processed, index=False, sep=';', encoding='utf-8-sig', date_format='%Y-%m-%d')
            logger.info(f"Arquivo Agrupado salvo: {output_path_processed}")
        
    except KeyboardInterrupt:
        logger.warning("Processo cancelado pelo usuário.")
    except Exception as e:
        logger.critical(f"Erro fatal no pipeline: {e}", exc_info=True)

if __name__ == "__main__":
    main()

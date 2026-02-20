import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from office365.runtime.auth.client_credential import ClientCredential
from office365.runtime.auth.user_credential import UserCredential
from office365.sharepoint.client_context import ClientContext
from office365.sharepoint.listitems.collection import ListItemCollection

# Configuração de Logging Estruturado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Configurações Globais
SHAREPOINT_SITE_URL = "https://netorg2135259.sharepoint.com/sites/sipel.com.br"
SHAREPOINT_LIST_NAME = "TabelaReservas"


def load_environment_variables() -> None:
    """
    Carrega variáveis de ambiente de forma robusta e exibe diagnóstico.
    """
    root_dir = Path(__file__).resolve().parents[2]
    env_path = root_dir / ".env"

    logger.info(f"Carregando configurações de: {env_path}")

    if not env_path.exists():
        logger.critical(f"ARQUIVO .ENV NÃO ENCONTRADO EM: {env_path}")
        sys.exit(1)

    load_dotenv(dotenv_path=env_path, override=True)

    client_id = os.getenv("SHAREPOINT_CLIENT_ID")
    client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET")
    username = os.getenv("SHAREPOINT_USER")

    logger.info("--- DIAGNÓSTICO DE CREDENCIAIS ---")
    logger.info(
        f"SHAREPOINT_CLIENT_ID     : {'[OK] Carregado' if client_id else '[FALHA] Vazio ou Não Encontrado'}"
    )
    logger.info(
        f"SHAREPOINT_CLIENT_SECRET : {'[OK] Carregado' if client_secret else '[FALHA] Vazio ou Não Encontrado'}"
    )
    logger.info(
        f"SHAREPOINT_USER          : {'[OK] Carregado' if username else '[AVISO] Não encontrado (Fallback)'}"
    )
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
            logger.info(
                f"Autenticando via App-Only (Client ID: ...{client_id[-4:] if client_id and len(client_id) > 4 else '****'})"
            )
            credentials = ClientCredential(client_id, client_secret)
            ctx = ClientContext(url).with_credentials(credentials)

        elif username and password:
            logger.warning("Autenticando via Usuário/Senha (Legado).")
            credentials = UserCredential(username, password)
            ctx = ClientContext(url).with_credentials(credentials)

        else:
            raise ValueError("Nenhuma credencial válida encontrada no .env.")

        web = ctx.web
        ctx.load(web)
        ctx.execute_query()
        logger.info(f"Conexão SUCESSO: Site '{web.properties.get('Title')}'")
        return ctx

    except Exception as e:
        logger.critical(f"FALHA DE CONEXÃO: {e}", exc_info=True)
        sys.exit(1)


def extract_list_items_paged(
    ctx: ClientContext, list_name: str, page_size: int = 5000
) -> List[Dict[str, Any]]:
    logger.info(f"Extraindo lista '{list_name}' (Pág: {page_size})...")
    try:
        target_list = ctx.web.lists.get_by_title(list_name)
        items: ListItemCollection = (
            target_list.items.paged(page_size).get().execute_query()
        )
        all_data = [item.properties for item in items]
        logger.info(f"Total extraído: {len(all_data)} registros.")
        return all_data
    except Exception as e:
        logger.error(f"Erro na extração da lista '{list_name}': {e}")
        raise


def clean_pendency_tags(text: Any) -> str:
    if pd.isna(text) or str(text).lower() in ["nan", "<na>", "none", ""]:
        return ""

    parts = [
        p.strip().title() for p in str(text).replace(",", ";").split(";") if p.strip()
    ]
    return ", ".join(sorted(list(set(parts))))


def clean_and_profile_data(raw_data: List[Dict[str, Any]]) -> pd.DataFrame:
    logger.info("Iniciando limpeza técnica...")
    if not raw_data:
        return pd.DataFrame()

    df = pd.DataFrame(raw_data)

    cols_to_drop = [
        c for c in df.columns if c.startswith("odata.") or c.startswith("__")
    ]
    system_cols = [
        "FileSystemObjectType",
        "ServerRedirectedEmbedUri",
        "ServerRedirectedEmbedUrl",
        "ContentTypeId",
        "ComplianceAssetId",
        "Attachments",
        "AssRespAlmoxarifado",
        "AssRespSaque",
        "GUID",
        "OData__ColorTag",
        "OData__UIVersionString",
    ]
    cols_to_drop.extend([c for c in system_cols if c in df.columns])
    df.drop(columns=cols_to_drop, inplace=True, errors="ignore")

    id_col = "Id" if "Id" in df.columns else "ID" if "ID" in df.columns else None
    if id_col:
        df[id_col] = df[id_col].astype(str).replace(["nan", "NaN", "None", ""], pd.NA)
        df.dropna(subset=[id_col], inplace=True)
    else:
        logger.error("Coluna de Identificação (Id/ID) não encontrada!")

    date_candidates = ["Created", "Modified"] + [
        col
        for col in df.columns
        if ("Data" in col or "DATE" in col.upper()) and col not in system_cols
    ]

    for col in [c for c in set(date_candidates) if c in df.columns]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.normalize()

    if "DataRegularisado" in df.columns:
        df.rename(columns={"DataRegularisado": "DataRegularizacao"}, inplace=True)

    logger.info(f"Dimensões finais: {df.shape}")
    return df


def apply_business_rules(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Aplicando regras de negócio e sanitização...")

    if "Created" in df.columns:
        df["Created_Date"] = pd.to_datetime(df["Created"]).dt.normalize()

    if "DataCriacaoReserva" in df.columns:
        if "DataSolicPrev" not in df.columns:
            df["DataSolicPrev"] = df["DataCriacaoReserva"]
        else:
            df["DataSolicPrev"] = df["DataSolicPrev"].fillna(df["DataCriacaoReserva"])

    df["Processo"] = "Encerramento"

    if "obra" in df.columns:
        df["obra"] = (
            df["obra"]
            .astype(str)
            .str.strip()
            .str.replace(r"^[Bb]-", "", regex=True)
            .str.strip()
        )

    group_cols = ["obra", "TipoSolic", "Created_Date", "NumeroReserva"]
    group_cols = [c for c in group_cols if c in df.columns]

    if len(group_cols) >= 3 and "IdSolic" in df.columns:
        logger.info(
            f"Padronizando IdSolic (Processo: Encerramento) com prefixo ENC- baseado em: {group_cols}"
        )
        reserva_serie = (
            df["NumeroReserva"]
            .astype(str)
            .replace(["nan", "NaN", "None", "<NA>", ""], "S-RES")
        )
        df["IdSolic"] = (
            "ENC-"
            + df["Created_Date"].dt.strftime("%Y%m%d")
            + "-"
            + df["obra"].astype(str)
            + "-"
            + df["TipoSolic"].astype(str)
            + "-"
            + reserva_serie
        )

    if "Created_Date" in df.columns:
        df.drop(columns=["Created_Date"], inplace=True)

    if "IdSolic" in df.columns:
        df.dropna(subset=["IdSolic"], inplace=True)

    if "QuantSolic" in df.columns:
        df["QuantSolic"] = pd.to_numeric(df["QuantSolic"], errors="coerce")
        df.dropna(subset=["QuantSolic"], inplace=True)

    if "Quant_Confirmada" in df.columns:
        df["Quant_Confirmada"] = pd.to_numeric(
            df["Quant_Confirmada"], errors="coerce"
        ).fillna(0)

    if "NumeroReserva" in df.columns:
        df["NumeroReserva"] = pd.to_numeric(df["NumeroReserva"], errors="coerce")

    if "Pendencias" in df.columns:
        df["Pendencias"] = df["Pendencias"].apply(clean_pendency_tags)

    cols_to_normalize = [
        "titulo",
        "Descricao",
        "Observacao",
        "StatusSolic",
        "Coleborador_solicitante",
        "AgenteResponsavel",
        "obra",
        "BaseOperacional",
        "DescricaoPendencias",
        "isUrgente",
        "IsDeleted",
    ]
    for col in [c for c in cols_to_normalize if c in df.columns]:
        df[col] = (
            df[col]
            .astype(str)
            .str.title()
            .str.strip()
            .replace({"Nan": "", "Nat": "", "None": "", "<Na>": ""}, regex=False)
        )

    if "obra" in df.columns:
        df["obra"] = pd.to_numeric(df["obra"], errors="coerce").round().astype("Int64")
        df.dropna(subset=["obra"], inplace=True)

    if "StatusSolic" in df.columns:
        status_map = {
            "Confirmado": "Movimentado",
            "Mov Parcial": "Mov. Parcial",
            "Mov.Parcial": "Mov. Parcial",
        }
        df["StatusSolic"] = df["StatusSolic"].replace(status_map)

    df.dropna(axis=1, how="all", inplace=True)

    int_cols = [
        "NumeroReserva",
        "CodMaterial",
        "TipoSolic",
        "CENTRO_MATERIAL",
        "idCoordenador",
        "idSupervisor",
    ]
    for col in [c for c in int_cols if c in df.columns]:
        df[col] = pd.to_numeric(df[col], errors="coerce").round().astype("Int64")

    df["Processo"] = "Encerramento"
    return df


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Padronizando nomes das colunas...")
    mapping = {
        "PROJETO": "obra",
        "CODIGO": "CodMaterial",
        "DESCRICAO_MATERIAL": "MaterialSolic",
        "BASE": "BaseOperacional",
        "TIPO_MOVIMENTACAO": "TipoSolic",
        "STATUS": "StatusSolic",
        "DATA_CRIACAOCOELBA": "DataCriacaoReserva",
        "NUMERO_RESERVA": "NumeroReserva",
        "DATA_SOLICITACAO": "DataSolic",
        "QUANTIDADE_SOLICITADA": "QuantSolic",
        "QUANTIDADE_MOVIMENTADA": "Quant_Confirmada",
        "IDSolic": "IdSolic",
        "Titulo": "titulo",
        "DataMovimentacao": "DataSolicMod",
        "TECNICO": "Coleborador_solicitante",
        "Urgente": "isUrgente",
        "OBSERVACAO_MAT": "Observacao",
        "Descri_x00e7__x00e3_oPendencias": "DescricaoPendencias",
    }
    return df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})


def resolve_status_aggr(series: pd.Series) -> str:
    # Helper for create_reservas_summary and consolidate_all_data
    statuses = {
        s.strip().title()
        for s in series.astype(str)
        if s.strip() and s.lower() not in ["nan", "none", "nat"]
    }
    if not statuses:
        return "Pendente"
    if any("Parcial" in s for s in statuses):
        return "Mov. Parcial"
    if any(s in ["Movimentado", "Confirmado"] for s in statuses):
        return (
            "Mov. Parcial"
            if any("Pendente" in s or "Reservado" in s for s in statuses)
            else "Movimentado"
        )
    if any(s in ["Pendente", "Reservado"] for s in statuses):
        return "Pendente"
    return sorted(list(statuses))[0] if statuses else "Pendente"


def agg_pendencias_aggr(series: pd.Series) -> str:
    # Helper for create_reservas_summary and consolidate_all_data
    return clean_pendency_tags(
        "; ".join(s for s in series.dropna().astype(str) if s.strip())
    )


def agg_descriptions_aggr(series: pd.Series) -> str:
    # Helper for create_reservas_summary and consolidate_all_data
    return " | ".join(
        sorted(
            {
                s.strip()
                for s in series.dropna().astype(str)
                if s.strip() and s.lower() not in ["nan", "none", "<na>"]
            }
        )
    )


def create_reservas_summary(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Gerando tabela agrupada por IdSolic (Reservas)...")
    if df.empty or "IdSolic" not in df.columns:
        return pd.DataFrame()

    agg_rules = {
        "StatusSolic": resolve_status_aggr,
        "QuantSolic": "sum",
        "Quant_Confirmada": "sum",
        "Pendencias": agg_pendencias_aggr,
        "DescricaoPendencias": agg_descriptions_aggr,
    }

    metadata_cols = [
        "obra",
        "BaseOperacional",
        "TipoSolic",
        "titulo",
        "DataSolic",
        "DataCriacaoReserva",
        "Processo",
    ]
    for col in [c for c in metadata_cols if c in df.columns]:
        agg_rules[col] = "first"

    date_cols = [c for c in df.columns if "Data" in c or c in ["Created", "Modified"]]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")
        if col not in agg_rules:
            agg_rules[col] = "min"

    return df.groupby("IdSolic", as_index=False).agg(agg_rules)


def consolidate_all_data(df_reservas: pd.DataFrame, root_dir: Path) -> pd.DataFrame:
    logger.info("Iniciando consolidação geral (Materiais + Reservas)...")
    materiais_path = root_dir / "materiais_obra/data/raw/materiais_obra_raw.csv"
    if not materiais_path.exists():
        logger.warning(f"Arquivo de materiais não encontrado: {materiais_path}")
        return pd.DataFrame()

    df_mat = pd.read_csv(
        materiais_path, sep=";", encoding="utf-8-sig", low_memory=False
    )
    mat_mapping = {
        "Quant_x002e_Confirmada": "Quant_Confirmada",
        "Coleborador_solicitante": "Solicitante",
        "IdSolic": "IdSolic",
    }
    df_mat = df_mat.rename(columns=mat_mapping)
    df_all = pd.concat([df_mat, df_reservas], ignore_index=True)

    date_cols = [
        c for c in df_all.columns if "Data" in c or c in ["Created", "Modified"]
    ]
    for col in date_cols:
        df_all[col] = (
            pd.to_datetime(df_all[col], errors="coerce", utc=True)
            .dt.tz_localize(None)
            .dt.normalize()
        )

    if "Created" in df_all.columns:
        df_all["Created_Date_Temp"] = pd.to_datetime(df_all["Created"]).dt.normalize()
        mask_enc = df_all["Processo"] == "Encerramento"
        if mask_enc.any():
            logger.info(
                "Padronizando IdSolic na base consolidada (Encerramento) com prefixo ENC-..."
            )
            df_all.loc[mask_enc, "obra"] = (
                df_all.loc[mask_enc, "obra"]
                .astype(str)
                .str.strip()
                .str.replace(r"^[Bb]-", "", regex=True)
                .str.strip()
            )
            reserva_serie = (
                df_all.loc[mask_enc, "NumeroReserva"]
                .astype(str)
                .replace(["nan", "NaN", "None", "<NA>", ""], "S-RES")
            )
            df_all.loc[mask_enc, "IdSolic"] = (
                "ENC-"
                + df_all.loc[mask_enc, "Created_Date_Temp"].dt.strftime("%Y%m%d")
                + "-"
                + df_all.loc[mask_enc, "obra"].astype(str)
                + "-"
                + df_all.loc[mask_enc, "TipoSolic"].astype(str)
                + "-"
                + reserva_serie
            )
        df_all.drop(columns=["Created_Date_Temp"], inplace=True)

    if "DataRegularizacao" in df_all.columns:
        df_all["DataRegularizacao"] = pd.to_datetime(
            df_all["DataRegularizacao"], errors="coerce"
        )

    if "QuantSolic" in df_all.columns:
        df_all["QuantSolic"] = pd.to_numeric(df_all["QuantSolic"], errors="coerce")
        df_all.dropna(subset=["QuantSolic"], inplace=True)

    overlap_mapping = {
        "Quant_x002e_Confirmada": "Quant_Confirmada",
        "QUANTIDADE_MOVIMENTADA": "Quant_Confirmada",
        "QUANTIDADE_SOLICITADA": "QuantSolic",
        "PROJETO": "obra",
        "TIPO_MOVIMENTACAO": "TipoSolic",
        "STATUS": "StatusSolic",
        "Status": "StatusSolic",
    }
    for old_col, new_col in overlap_mapping.items():
        if old_col in df_all.columns and old_col != new_col:
            df_all[new_col] = df_all[new_col].fillna(df_all[old_col])
            df_all.drop(columns=[old_col], inplace=True)

    int_cols_final = [
        "obra",
        "CodMaterial",
        "TipoSolic",
        "CENTRO_MATERIAL",
        "NumeroReserva",
        "idCoordenador",
        "idSupervisor",
        "AuthorId",
        "EditorId",
    ]
    for col in [c for c in int_cols_final if c in df_all.columns]:
        df_all[col] = pd.to_numeric(df_all[col], errors="coerce").astype("Int64")

    logger.info("Agrupando base consolidada geral...")

    agg_rules = {
        "QuantSolic": "sum",
        "Quant_Confirmada": "sum",
        "StatusSolic": resolve_status_aggr,
        "Pendencias": agg_pendencias_aggr,
        "DescricaoPendencias": agg_descriptions_aggr,
    }
    for col in df_all.columns:
        if col in agg_rules or col == "IdSolic":
            continue
        agg_rules[col] = (
            "max"
            if "Data" in col
            or col in ["Created", "Modified"]
            or pd.api.types.is_numeric_dtype(df_all[col])
            else "first"
        )
    for col in [
        "DataCriacaoReserva",
        "DataSolicMod",
        "DataPendencia",
        "DataRegularizacao",
    ]:
        if col in df_all.columns:
            agg_rules[col] = "max"

    df_final = df_all.groupby("IdSolic", as_index=False).agg(agg_rules)

    logger.info("Aplicando tratamentos finais...")
    cols_to_remove = [
        "LatitudeSolic",
        "LongetudeSolic",
        "Id",
        "",
        "_1",
        "_2",
        "_3",
        "GUID",
        "MOTIVO_EXCLUSAO",
        "AVALIACAO_MATERIAL",
        "CENTRO_MATERIAL",
        "RECEBEDOR",
        "SUPR_MATR",
        "AuthorId",
        "EditorId",
        "IsAvulso",
        "isUrgente",
        "Observacao",
        "MotivoRejSolic",
        "ID",
        "DATA_CRIACAO",
        "DataEstorno",
    ]
    df_final.drop(
        columns=[c for c in cols_to_remove if c in df_final.columns],
        inplace=True,
        errors="ignore",
    )

    if "IsDeleted" in df_final.columns:
        df_final["IsDeleted"] = (
            df_final["IsDeleted"]
            .astype(str)
            .str.lower()
            .map(
                {
                    "0": False,
                    "0.0": False,
                    "false": False,
                    "1": True,
                    "1.0": True,
                    "true": True,
                }
            )
            .fillna(False)
            .astype(bool)
        )
        df_final = df_final[~df_final["IsDeleted"]].copy()

    if "StatusSolic" in df_final.columns:
        df_final["StatusSolic"] = df_final["StatusSolic"].replace(
            {
                "Confirmado": "Movimentado",
                "Reservado": "Pendente",
                "Deletado": "Rejeitado",
                "Estornado": "Rejeitado",
            }
        )

    if "titulo" in df_final.columns:
        df_final["titulo"] = (
            df_final["titulo"]
            .astype(str)
            .str.title()
            .str.strip()
            .replace("Nan", "", regex=False)
        )

    if "QuantSolic" in df_final.columns:
        df_final["QuantSolic"] = pd.to_numeric(df_final["QuantSolic"], errors="coerce")
        df_final.dropna(subset=["QuantSolic"], inplace=True)

    temp_df = df_final.replace("", np.nan)
    df_final = df_final[temp_df.notna().any(axis=1)].copy()

    logger.info("Sanitizando campos de texto...")
    text_cols = [
        c
        for c in df_final.select_dtypes(include=["object"]).columns
        if not ("Data" in c or c in ["Created", "Modified"])
    ]
    for col in text_cols:
        df_final[col] = (
            df_final[col]
            .astype(str)
            .str.replace(";", ",", regex=False)
            .str.replace("\n", " ", regex=False)
            .str.replace("\r", "", regex=False)
            .str.strip()
        )
        df_final.loc[
            df_final[col].str.lower().isin(["nan", "none", "nat", ""]), col
        ] = ""

    return df_final


def main() -> None:
    logger.info("=== Pipeline ETL Iniciado (TabelaReservas) ===")
    try:
        load_environment_variables()
        root_dir = Path(__file__).resolve().parents[2]
        ctx = get_sharepoint_context(SHAREPOINT_SITE_URL)
        raw_data = extract_list_items_paged(ctx, SHAREPOINT_LIST_NAME)

        df_raw = clean_and_profile_data(raw_data)
        df_standard = standardize_columns(df_raw)
        df_treated = apply_business_rules(df_standard)

        output_dir_raw = root_dir / "materiais_obra/data/raw"
        output_dir_raw.mkdir(parents=True, exist_ok=True)
        output_path_raw = output_dir_raw / "tabela_reservas_raw.csv"

        if not df_treated.empty:
            df_treated.to_csv(
                output_path_raw,
                index=False,
                sep=";",
                encoding="utf-8-sig",
                date_format="%Y-%m-%d",
            )
            logger.info(f"Arquivo Raw Reservas salvo: {output_path_raw}")

            df_grouped_res = create_reservas_summary(df_treated)
            output_dir_proc = root_dir / "materiais_obra/data/processed"
            output_dir_proc.mkdir(parents=True, exist_ok=True)
            df_grouped_res.to_csv(
                output_dir_proc / "tabela_reservas_agrupada.csv",
                index=False,
                sep=";",
                encoding="utf-8-sig",
                date_format="%Y-%m-%d",
                decimal=",",
            )
            logger.info("Tabela de reservas agrupada salva.")

            df_consolidated = consolidate_all_data(df_treated, root_dir)
            if not df_consolidated.empty:
                df_consolidated.to_csv(
                    output_dir_proc / "solicitacoes_consolidadas_geral.csv",
                    index=False,
                    sep=";",
                    encoding="utf-8-sig",
                    date_format="%Y-%m-%d",
                    decimal=",",
                )
                logger.info("Consolidado geral (Materiais + Reservas) salvo.")
        else:
            logger.warning("DataFrame vazio. Nenhum arquivo salvo.")

    except KeyboardInterrupt:
        logger.warning("Cancelado pelo usuário.")
    except Exception as e:
        logger.critical(f"Erro não tratado: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

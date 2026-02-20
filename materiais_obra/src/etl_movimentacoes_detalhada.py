import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ETL_Movimentacoes_Detalhada")


def enforce_strict_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica tipagem rigorosa baseada no Power Query (M Code) fornecido.
    """
    logger.info("Iniciando conversão rigorosa de tipos...")
    df = df.replace({"<Na>": np.nan, "<na>": np.nan})

    cols_int = [
        "obra",
        "CodMaterial",
        "TipoSolic",
        "IsDeleted",
        "CENTRO_MATERIAL",
        "idCoordenador",
        "idSupervisor",
    ]
    cols_float = ["QuantSolic", "Quant_Confirmada"]
    cols_date = [
        "DataEstorno",
        "DataSolic",
        "DataCriacaoReserva",
        "Modified",
        "DataPendencia",
        "DataRegularizacao",
        "Created",
        "DataSolicMod",
        "DataSolicPrev",
        "DATA_CRIACAO",
        "DataSolicMod",
    ]
    cols_str = [
        "MaterialSolic",
        "BaseOperacional",
        "StatusSolic",
        "MOTIVO_EXCLUSAO",
        "Coleborador_solicitante",
        "AVALIACAO_MATERIAL",
        "RECEBEDOR",
        "SUPR_MATR",
        "Observacao",
        "IdSolic",
        "Encarregado",
        "isUrgente",
        "titulo",
        "AgenteResponsavel",
        "Pendencias",
        "DescricaoPendencias",
        "UsuarioMovimentacao",
        "MotivoRejSolic",
        "EmailSolic",
        "UnidadeMedida",
        "Processo",
        "ProjetoFilho",
        "Separacao",
        "Justificar",
    ]
    cols_bool = ["IsAvulso"]

    for col in cols_int:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    for col in cols_float:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in cols_date:
        if col in df.columns:
            df[col] = (
                pd.to_datetime(df[col], errors="coerce", dayfirst=False, utc=True)
                .dt.tz_localize(None)
                .dt.normalize()
            )

    for col in cols_str:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            replace_mask = df[col].str.lower().isin(["nan", "nat", "none", "<na>", ""])
            df.loc[replace_mask, col] = ""

    for col in cols_bool:
        if col in df.columns:
            df[col] = df[col].map(
                {"True": True, "False": False, True: True, False: False}
            )
            df[col] = df[col].astype("boolean")

    logger.info("Tipagem rigorosa aplicada.")
    return df


def main() -> None:
    try:
        root_dir = Path(__file__).resolve().parents[2]
        raw_dir = root_dir / "materiais_obra/data/raw"
        processed_dir = root_dir / "materiais_obra/data/processed"
        processed_dir.mkdir(parents=True, exist_ok=True)

        path_materiais = raw_dir / "materiais_obra_raw.csv"
        path_reservas = raw_dir / "tabela_reservas_raw.csv"

        if not path_materiais.exists() or not path_reservas.exists():
            logger.error(
                "Arquivos RAW não encontrados. Execute etl_materiais.py e etl_reservas.py primeiro."
            )
            sys.exit(1)

        logger.info("Lendo arquivos RAW...")
        df_mat = pd.read_csv(path_materiais, sep=";", dtype=str, encoding="utf-8-sig")
        df_res = pd.read_csv(path_reservas, sep=";", dtype=str, encoding="utf-8-sig")

        mapping_mat = {
            "Quant_x002e_Confirmada": "Quant_Confirmada",
            "DataRegularisado": "DataRegularizacao",
        }
        df_mat = df_mat.rename(columns=mapping_mat)
        df_res = df_res.rename(columns={"DataRegularisado": "DataRegularizacao"})

        logger.info(f"Materiais: {df_mat.shape}, Reservas: {df_res.shape}")
        df_final = pd.concat([df_mat, df_res], ignore_index=True, sort=False)

        if "ID" in df_final.columns and "Id" in df_final.columns:
            df_final["Id"] = df_final["Id"].fillna(df_final["ID"])
            df_final.drop(columns=["ID"], inplace=True)
        elif "ID" in df_final.columns:
            df_final.rename(columns={"ID": "Id"}, inplace=True)

        if "Id" in df_final.columns:
            initial_rows = len(df_final)
            df_final["Id"] = (
                df_final["Id"]
                .astype(str)
                .str.strip()
                .replace(["nan", "NaN", "None", "nan", ""], np.nan)
            )
            df_final.dropna(subset=["Id"], inplace=True)
            if (dropped_ids := initial_rows - len(df_final)) > 0:
                logger.warning(
                    f"Removidas {dropped_ids} linhas com 'Id' inválido/vazio após o merge."
                )
        else:
            logger.error("COLUNA 'Id' NÃO ENCONTRADA APÓS O MERGE!")

        df_final.dropna(axis=1, how="all", inplace=True)
        df_final = enforce_strict_types(df_final)

        logger.info("Aplicando transformações finais (Power Query Migration)...")
        if "Id" in df_final.columns:
            df_final = df_final[df_final["Id"].notna()].copy()

        if "Created" in df_final.columns:
            df_final["Created_Date"] = pd.to_datetime(
                df_final["Created"]
            ).dt.normalize()

        group_cols = ["obra", "TipoSolic", "Created_Date", "NumeroReserva"]
        group_cols = [c for c in group_cols if c in df_final.columns]

        if len(group_cols) >= 3 and "IdSolic" in df_final.columns:
            logger.info(
                f"Aplicando padronização definitiva de IdSolic (Encerramento) baseado em: {group_cols}"
            )
            mask_enc = df_final["Processo"] == "Encerramento"
            if mask_enc.any():
                df_final.loc[mask_enc, "obra"] = (
                    df_final.loc[mask_enc, "obra"]
                    .astype(str)
                    .str.strip()
                    .replace(r"^[Bb]-", "", regex=True)
                    .str.strip()
                )
                reserva_serie = (
                    df_final.loc[mask_enc, "NumeroReserva"]
                    .astype(str)
                    .replace(["nan", "NaN", "None", "<NA>", ""], "S-RES")
                )
                df_final.loc[mask_enc, "IdSolic"] = (
                    "ENC-"
                    + df_final.loc[mask_enc, "Created_Date"].dt.strftime("%Y%m%d")
                    + "-"
                    + df_final.loc[mask_enc, "obra"].astype(str)
                    + "-"
                    + df_final.loc[mask_enc, "TipoSolic"].astype(str)
                    + "-"
                    + reserva_serie
                )

        if "StatusSolic" in df_final.columns:
            status_map = {
                "Confirmado": "Movimentado",
                "Reservado": "Pendente",
                "Deletado": "Rejeitado",
                "Estornado": "Rejeitado",
                "Mov Parcial": "Mov. Parcial",
                "Mov.Parcial": "Mov. Parcial",
            }
            df_final["StatusSolic"] = df_final["StatusSolic"].replace(status_map)

        if "Created_Date" in df_final.columns:
            df_final.drop(columns=["Created_Date"], inplace=True)

        if "Justificar" in df_final.columns:
            df_final["Justificar"] = (
                df_final["Justificar"]
                .fillna("Comum")
                .replace({"": "Comum", "Normal": "Comum"})
            )

        if "titulo" in df_final.columns:
            df_final["titulo"] = df_final["titulo"].astype(str).str.title().str.strip()

        cols_to_drop = [
            "MotivoRejSolic",
            "EmailSolic",
            "IsAvulso",
            "LatitudeSolic",
            "LongetudeSolic",
            "Observacao",
            "isUrgente",
            "UnidadeMedida",
            "ProjetoFilho",
            "Separacao",
            "AuthorId",
            "EditorId",
            "MOTIVO_EXCLUSAO",
            "AVALIACAO_MATERIAL",
            "CENTRO_MATERIAL",
            "RECEBEDOR",
            "SUPR_MATR",
            "GUID",
        ]
        df_final.drop(
            columns=[c for c in cols_to_drop if c in df_final.columns], inplace=True
        )

        subset_validation = ["IdSolic", "obra", "CodMaterial"]
        subset_validation = [c for c in subset_validation if c in df_final.columns]

        if subset_validation:
            initial_rows = len(df_final)
            mask = df_final[subset_validation].replace("", np.nan).isna().all(axis=1)
            df_final = df_final[~mask]
            if (dropped := initial_rows - len(df_final)) > 0:
                logger.info(
                    f"Removidas {dropped} linhas sem identificadores principais."
                )

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

        output_path = processed_dir / "fato_movimentacoes_itens.csv"
        df_final.to_csv(
            output_path,
            sep=";",
            index=False,
            encoding="utf-8-sig",
            date_format="%Y-%m-%d",
            decimal=",",
        )

        logger.info("=== SUCESSO ===")
        logger.info(f"Arquivo gerado: {output_path}")
        logger.info(f"Total de Linhas: {len(df_final)}")
        logger.info(df_final.dtypes)

    except Exception as e:
        logger.critical(f"Erro fatal: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

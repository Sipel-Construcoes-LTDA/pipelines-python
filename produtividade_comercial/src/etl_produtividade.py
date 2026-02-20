import pandas as pd
import os
import glob
import re
import logging
from typing import List, Dict, Optional, Any

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configurações de Diretório ---
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_ROOT = os.path.dirname(SRC_DIR)
YEAR_DIRS = ["2024", "2025", "2026"]


def parse_filename(filename: str) -> Dict[str, Any]:
    """
    Analisa o nome do arquivo para extrair mês, ano e se é 'Abertas'.
    """
    basename = os.path.basename(filename)
    name_no_ext = os.path.splitext(basename)[0]

    is_abertas = "abertas" in name_no_ext.lower()
    parts = name_no_ext.split()

    month, year = 0, 0
    try:
        if parts:
            month = int(parts[0])
        for part in parts[1:]:
            if part.isdigit() and len(part) == 4:
                year = int(part)
                break
        if year == 0:
            parent_dir = os.path.basename(os.path.dirname(filename))
            if parent_dir.isdigit() and len(parent_dir) == 4:
                year = int(parent_dir)
    except (ValueError, IndexError):
        pass

    return {"filepath": filename, "month": month, "year": year, "is_abertas": is_abertas, "sort_key": year * 100 + month}


def get_files_to_process() -> List[str]:
    """
    Seleciona todos os arquivos fechados e APENAS o arquivo 'Abertas' mais recente.
    """
    all_files_paths: List[str] = []
    for year_dir in YEAR_DIRS:
        path = os.path.join(MODULE_ROOT, year_dir, "*.XLS")
        all_files_paths.extend(glob.glob(path))

    parsed_files = [parse_filename(f) for f in all_files_paths]

    regular_files = [f for f in parsed_files if not f['is_abertas']]
    abertas_files = [f for f in parsed_files if f['is_abertas']]

    final_list = [f['filepath'] for f in regular_files]

    if abertas_files:
        abertas_files.sort(key=lambda x: x['sort_key'], reverse=True)
        latest_abertas = abertas_files[0]
        final_list.append(latest_abertas['filepath'])
        logger.info(
            f"Arquivo 'Abertas' selecionado: {os.path.basename(latest_abertas['filepath'])}")

    return final_list


def convert_custom_date(val: Any) -> Optional[pd.Timestamp]:
    """
    Converte string para datetime, suportando formatos 'dd.mm.yyyy' e 'ddMMyyyy'.
    """
    if pd.isna(val) or val == "":
        return pd.NaT

    s_val = str(val).strip()
    try:
        if '.' in s_val:
            return pd.to_datetime(s_val, format='%d.%m.%Y', errors='coerce')
        s_val_clean = re.sub(r'\D', '', s_val).zfill(8)
        if len(s_val_clean) == 8:
            return pd.to_datetime(s_val_clean, format='%d%m%Y', errors='coerce')
        return pd.NaT
    except ValueError:
        return pd.NaT


def read_file(filepath: str) -> pd.DataFrame:
    """
    Lê o arquivo .XLS (Texto Tabulado UTF-16).
    """
    try:
        df = pd.read_csv(filepath, sep='\t', encoding='utf-16',
                         skiprows=3, on_bad_lines='skip')
        df.columns = df.columns.str.strip()

        if 'Nota' not in df.columns:
            logger.warning(
                f"'Nota' não encontrada em {os.path.basename(filepath)}. Tentando autodetect...")
            return pd.DataFrame()
        return df
    except Exception as e:
        logger.error(f"Erro ao ler {filepath}: {e}")
        return pd.DataFrame()


def transform_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica as regras de negócio.
    """
    if df.empty:
        return df

    if 'Nota' in df.columns:
        df['Nota'] = pd.to_numeric(df['Nota'], errors='coerce')

    date_cols_map = {
        "InícioAvar": "Inicio da Nota", "Fim avaria": "Finalização da nota",
        "Concl.desj": "Conc. desejada", "Encerram.": "Encerramento da nota"
    }
    for src, target in date_cols_map.items():
        df[target] = df[src].apply(
            convert_custom_date) if src in df.columns else pd.NaT
    df["Criação da nota"] = df["InícioAvar"].apply(
        convert_custom_date) if "InícioAvar" in df.columns else pd.NaT

    df = df.dropna(subset=['Nota'])
    df["Nº do pedido"] = df["Nº do pedido"].fillna(
        "Vazio") if "Nº do pedido" in df.columns else "Vazio"

    def check_vistoria(pedido: Any) -> str:
        if pd.isna(pedido):
            return "Não vistoriada"
        p = str(pedido)
        return "Vistoriada" if any(x in p for x in ["vv", "vv.", "v v"]) or p.startswith("VV") else "Não vistoriada"

    df["Nota vistoriada"] = df["Nº do pedido"].apply(check_vistoria)
    df.rename(columns={"Nr. Série Equip.": "Nr. Série"}, inplace=True)
    df["Data de Finalização"] = df["Finalização da nota"].fillna(
        df["Encerramento da nota"])

    cols_to_remove = ["Concl.desj", "ContContr.", "Instalação", "Dt.criação", "H fim des.", "TensFornec", "Code", "Data", "Hora", "Poste", "Grp.cod", "UnLeit.", "Ordenação", "TensMed", "CNAE", "EqMedVizAn", "EqMedVizPo", "MedVizPos", "MedVizAnt", "Posto", "InícioAvar", "Fim avaria", "HFimAvar", "Encerram.", "HEnc.", "Modif.em",
                      "Ordem", "C", "HInícAv.", "Centro cst", "Den.exec.", "Den.exec._1", "Exec.por", "Execução", "P", "Rg", "Localiz.", "Cen.", "Bairro de", "   DiasExec", "QtdHorExec", "Centro de Resultado", "Municípo", "Nome do parceiro", " DiasExec", "  DiasExec", "TpPri", "Cliente", "Texto breve", "Ctg.tar.", "NºEndereço", "Column14", "DiasExec"]
    df.drop(
        columns=[c for c in cols_to_remove if c in df.columns], inplace=True)

    df.drop_duplicates(subset=["Nota"], inplace=True)
    if "Urbano/Rur" in df.columns:
        df["Urbano/Rur"] = df["Urbano/Rur"].fillna(
            "Info.").replace({"R": "Rural", "U": "Urbano"})

    df.sort_values(by="Nota", ascending=True, inplace=True)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df["Nota"] = df["Nota"].astype('int64')
    return df


def main() -> None:
    """
    Orquestra o pipeline de ETL para dados de produtividade comercial.
    """
    logger.info("Iniciando ETL Produtividade Comercial...")

    files = get_files_to_process()
    logger.info(f"{len(files)} arquivos identificados para processamento.")

    dfs = [read_file(f) for f in files]
    dfs = [df for df in dfs if not df.empty]

    if not dfs:
        logger.error("Nenhum dado lido.")
        return

    logger.info("Consolidando dados...")
    full_df = pd.concat(dfs, ignore_index=True)

    logger.info("Aplicando transformações...")
    final_df = transform_data(full_df)

    processed_dir = os.path.join(MODULE_ROOT, "data", "processed")
    os.makedirs(processed_dir, exist_ok=True)
    output_path = os.path.join(processed_dir, "produtividade_tratada.csv")

    final_df.to_csv(output_path, index=False, sep=';', encoding='utf-8-sig')

    logger.info(f"Processo concluído. Arquivo gerado: {output_path}")
    logger.info(f"Total de registros: {len(final_df)}")


if __name__ == "__main__":
    main()

import os
from pathlib import Path
from dotenv import load_dotenv


def debug_environment() -> None:  # Added return type annotation
    # 1. Localizar o arquivo .env
    env_path = Path(".env")
    print(f"1. Verificando arquivo .env em: {env_path.absolute()}")

    if not env_path.exists():
        print("ERRO: Arquivo .env NÃO encontrado!")
        return

    print("   Arquivo encontrado.")

    # 2. Ler conteúdo bruto (mascarado) para verificar chaves
    print("\n2. Analisando chaves no arquivo (Valores mascarados):")
    with open(env_path, "r") as f:
        lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                masked_value = (
                    value[:2] + "*" * 4 + value[-2:] if len(value) > 4 else "****"
                )
                print(f"   Encontrado: [{key}] = {masked_value}")
            else:
                print(f"   ALERTA: Linha mal formatada (sem '='): {line}")

    # 3. Testar carregamento via biblioteca python-dotenv
    print("\n3. Testando carregamento via load_dotenv():")
    load_dotenv(dotenv_path=env_path, override=True)

    client_id = os.getenv("SHAREPOINT_CLIENT_ID")
    client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET")

    print(f"   SHAREPOINT_CLIENT_ID carregado? {'SIM' if client_id else 'NÃO'}")
    if client_id:
        print(f"   Valor: {client_id[:4]}...{client_id[-4:]} (Len: {len(client_id)})")

    print(f"   SHAREPOINT_CLIENT_SECRET carregado? {'SIM' if client_secret else 'NÃO'}")


if __name__ == "__main__":
    debug_environment()

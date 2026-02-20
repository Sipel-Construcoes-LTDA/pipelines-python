import pandas as pd
import requests
import io

IDS = {
    "Bonfim": "1gNr558RS_DHwv8PjaSdwOvDI0mqlVVY3GEKFFXKsU5U",
    "Jacobina": "19OdT08BBNJqQwU4GNyYySNlpTj6p7UVW66xFYyd5B5I",
    "Juazeiro": "1Q9-OHTSZG7IRoZ2zocmLjv934_fTwOB7FhCFXbzECG0"
}

GIDS = {
    "Bonfim": "1164135827",
    "Jacobina": "1906289711",
    "Juazeiro": "1923088500"
}

for name, sheet_id in IDS.items():
    print(f"
--- Analisando: {name} ---")
    gid = GIDS[name]
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    response = requests.get(url)
    if response.status_code == 200:
        # Lendo as primeiras 5 linhas brutas para ver o que tem nelas
        content = response.content.decode('utf-8')
        lines = content.splitlines()[:10]
        for i, line in enumerate(lines):
            print(f"Linha {i}: {line[:150]}") # Limita largura para o log
    else:
        print(f"Erro ao acessar {name}: {response.status_code}")

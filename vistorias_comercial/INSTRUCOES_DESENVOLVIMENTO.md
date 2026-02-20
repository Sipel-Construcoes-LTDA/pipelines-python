# Guia de Desenvolvimento: Pipeline Vistorias Comercial (Python)

Este documento orienta a criação do pipeline `vistorias_comercial`, convertendo a lógica de Power Query (M) para Python/Pandas.

## 1. Objetivo
Consolidar as vistorias online das bases de **Senhor do Bonfim**, **Jacobina** e **Juazeiro** em um único arquivo CSV (`vistorias_consolidadas.csv`).

## 2. Preparação do Ambiente
Certifique-se de ter as bibliotecas instaladas:
```bash
pip install pandas requests openpyxl
```

## 3. Acesso aos Dados (Google Sheets)
Para ler planilhas do Google sem APIs complexas, altere o final da URL para exportação em CSV:
*   **Original:** `.../edit?usp=sharing`
*   **Modificado:** `/export?format=csv`

### IDs das Planilhas:
- **Bonfim:** `1gNr558RS_DHwv8PjaSdwOvDI0mqlVVY3GEKFFXKsU5U`
- **Jacobina:** `19OdT08BBNJqQwU4GNyYySNlpTj6p7UVW66xFYyd5B5I`
- **Juazeiro:** `1Q9-OHTSZG7IRoZ2zocmLjv934_fTwOB7FhCFXbzECG0`

## 4. Mapeamento de Lógica (Power Query -> Python)

### A. vistorias_bonfim
1.  **Leitura:** Use `pd.read_csv(url_bonfim)`.
2.  **Tipagem:** Converta `NOTA` para inteiro. Use `pd.to_datetime()` para `PRAZO DA NOTA` e `DATA DO CONTATO`.
3.  **Renomeação:** 
    - `COLABORADOR` -> `RESPONSAVEL`
    - `STATUS` -> `CONFORMIDADE`
    - `CONFORMIDADE` -> `STATUS` (Inversão solicitada)
4.  **Limpeza:** Remova linhas onde `NOTA` não é um número válido.

### B. vistorias_jacobina
1.  **Leitura:** Use `pd.read_csv(url_jacobina)`.
2.  **Limpeza de Vazios:** No Power Query usamos `Table.SelectRows` para remover brancos. No Python, use `df.dropna(how='all')`.
3.  **Renomeação:**
    - `LOCAL` -> `MUNICIPIO`
    - `DATA CONTATO` -> `DATA DO CONTATO`
    - `STATUS` -> `CONFORMIDADE`
    - `CONFORMIDADE` -> `STATUS`
4.  **Erros:** Garanta que `NOTA` seja numérico.

### C. vistorias_juazeiro
1.  **Leitura:** Esta planilha possui múltiplos cabeçalhos promovidos no Power Query. No Pandas, verifique se precisa pular linhas iniciais usando o argumento `skiprows`.
2.  **Renomeação:**
    - `UTEP` -> `MUNICIPIO`
    - `COLABORADOR` -> `RESPONSAVEL`
    - `DATA CONTATO` -> `DATA DO CONTATO`
    - `RETORNO` -> `CONFORMIDADE`

## 5. Consolidação (vistorias_consolidadas)
Após tratar os três DataFrames individualmente:

1.  **União:** Utilize `pd.concat([df_bonfim, df_jacobina, df_juazeiro])`.
2.  **Seleção de Colunas:** Filtre apenas as colunas:
    - `NOTA`, `DATA DO CONTATO`, `DATA DO RETORNO`, `MUNICIPIO`, `RESPONSAVEL`, `STATUS`, `CONFORMIDADE`.
3.  **Tratamento de Datas:** Converta `DATA DO RETORNO` para o tipo `date`.
4.  **Remoção de Erros Críticos:** Delete linhas onde as datas de contato ou retorno estejam nulas/inválidas após a conversão.

## 6. Padrões de Código
Para que seu script seja profissional:
*   **Modularidade:** Crie uma função para cada cidade.
*   **Logging:** Não use `print()`. Use `import logging` para registrar o progresso.
*   **Segurança:** Use blocos `try-except` ao ler as URLs para tratar falhas de internet.
*   **Exportação:** Salve o resultado final em `data/processed/vistorias_consolidadas.csv` usando `index=False`.
*   **Padrão:** Use os demais pipelines como base. Siga os padrões de projeto presentes no arquivo PADROES_PROJETO.md

---
*Dúvidas? Consulte a documentação oficial do Pandas ou peça revisão praThaison lindo.*

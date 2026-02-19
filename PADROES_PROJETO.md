# Guia de Padronização e Boas Práticas - SIPEL Data Engineering

Este documento estabelece as diretrizes técnicas e de design para o desenvolvimento de pipelines de dados no repositório `pipelines-dados-SIPEL`. O objetivo é garantir código resiliente, performático e de fácil manutenção.

---

## 1. Filosofia de Desenvolvimento
*   **Pipeline como Código**: Tratamos extrações e transformações com o mesmo rigor de uma aplicação de software.
*   **Arquitetura Resiliente**: Antecipe a falha. Dados virão sujos, conexões cairão e tipos mudarão. O código deve tratar esses cenários sem interromper o fluxo global.
*   **Contratos de Dados**: Defina claramente o que entra e o que sai de cada função.

---

## 2. Padrões de Código (Python)

### A. Estilo e Formatação
*   **PEP 8**: Adesão obrigatória. Use linters (Flake8/Blue) antes de realizar o commit.
*   **Type Hinting**: Obrigatório em todas as assinaturas de funções.
    ```python
    def transform_data(df: pd.DataFrame, base_name: str) -> pd.DataFrame:
    ```
*   **Docstrings**: Use o padrão Google ou NumPy para descrever parâmetros e retornos.

### B. Gestão de Logs e Monitoramento
*   **PROIBIDO o uso de `print()`**: Use a biblioteca `logging`.
*   **Estrutura de Log**:
    ```python
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    ```
*   **Níveis de Log**:
    *   `INFO`: Início/Fim de etapas e volumetria.
    *   `WARNING`: Inconsistências de dados tratadas (ex: nulos removidos).
    *   `ERROR`: Falha em um arquivo específico que permite a continuação do pipeline.
    *   `CRITICAL`: Erro de credenciais ou infraestrutura que impede a execução.

---

## 3. Engenharia de Pipelines

### A. Estrutura Modular
Todo script de ETL deve seguir esta anatomia:
1.  **Imports**: Explícitos (nada de `from module import *`).
2.  **Configurações/Constants**: Caminhos e mapeamentos globais.
3.  **Extract**: Funções de I/O (SharePoint, SQL, Google Sheets).
4.  **Transform**: Lógica de limpeza pesada (vetorizada).
5.  **Validate**: Validação de schemas e tipos.
6.  **Load**: Escrita em CSV/Parquet/Database.
7.  **Main Execution**: Bloco `if __name__ == "__main__":`.

### B. Manipulação de Dados (Pandas/Polars)
*   **Vetorização**: Evite `iterrows()` ou loops manuais. Use métodos nativos do Pandas (`.map()`, `.apply()`, `.loc[]`).
*   **Seleção Explícita**: Nunca assuma a ordem das colunas. Sempre selecione colunas por nome.
*   **Tipagem Estrita**: Converta colunas para tipos específicos (especialmente `Int64` para IDs e `datetime64[ns]` para datas) logo após a carga inicial.

---

## 4. Segurança e Ambiente
*   **Variáveis de Ambiente**: Credenciais (IDs, Secrets, Senhas) devem residir exclusivamente em arquivos `.env`.
*   **Exclusão no Git**: Nunca commite arquivos `.env`, pastas `__pycache__` ou dados brutos (`data/raw`).
*   **Gerenciamento de Dependências**: Mantenha o `requirements.txt` atualizado. Sempre use versões fixas (ex: `pandas==2.1.0`).

---

## 5. Estrutura de Pastas
Mantenha a organização por domínio:
```text
nome_do_pipeline/
├── data/
│   ├── raw/         # Dados brutos (Cache/SharePoint) - Ignorado pelo Git
│   ├── processed/   # Output final para dashboards
│   └── auxiliary/   # Tabelas dimensão e de-para
├── src/
│   └── etl_script.py
└── README.md        # Documentação específica do pipeline
```

---

## 6. Workflow de Versionamento
*   **Commits Semânticos**: Mensagens claras e objetivas.
    *   `feat`: Nova funcionalidade de extração.
    *   `fix`: Correção de bug na transformação.
    *   `refactor`: Melhoria de performance sem alterar output.
*   **Branching**: Desenvolva em branches específicas (ex: `feature/ajuste-sharepoint`) e solicite code review.

---
**Dúvidas?** Consulte o arquivo `GEMINI.md` para entender as diretrizes de IA ou procure o responsável pelo repositório.

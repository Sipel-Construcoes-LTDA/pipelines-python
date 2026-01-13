# Pipelines de Dados - SIPEL

Repositório centralizado para automação de extração, tratamento e carga de dados (ETL) da SIPEL. Este projeto utiliza Python de alto nível para garantir a integridade, padronização e escalabilidade dos dados corporativos.

## 🛠️ Tecnologias e Bibliotecas

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Pandas](https://img.shields.io/badge/pandas-%23150458.svg?style=for-the-badge&logo=pandas&logoColor=white)
![Git](https://img.shields.io/badge/git-%23F05033.svg?style=for-the-badge&logo=git&logoColor=white)
![Gemini AI](https://img.shields.io/badge/Gemini-8E75B2?style=for-the-badge&logo=google-gemini&logoColor=white)

### Detalhamento da Stack
*   **Python 3.10+**: Linguagem base para processamento de dados.
*   **Pandas**: Engine para manipulação de DataFrames e transformações complexas.
*   **Requests**: Extração de dados via HTTP/HTTPS (Google Sheets API/Export).
*   **Regex (Re)**: Higienização e padronização de strings.
*   **Logging**: Rastreabilidade e monitoramento de execução em tempo real.

---

## 🚀 Estrutura do Repositório

O repositório está organizado por pastas, onde cada uma representa um domínio de dados ou pipeline específico:

```text
pipelines-dados-SIPEL/
├── faturamento_comercial/         # Pipeline de Faturamento
│   ├── etl_pipeline.py            # Script principal de ETL
│   └── faturamentos_tratados.csv  # Output gerado
├── produtividade_comercial/       # Pipeline de Produtividade (Novo)
│   ├── 2024/                      # Arquivos fonte (Histórico)
│   ├── 2025/                      # Arquivos fonte (Corrente)
│   ├── etl_produtividade.py       # Script principal de ETL
│   └── produtividade_tratada.csv  # Output gerado (CSV ; UTF-8)
├── GEMINI.md                      # Diretrizes da IA e padrões de engenharia
├── README.md                      # Documentação oficial
└── .gitignore                     # Configuração de exclusão do Git
```

## 🤖 Integração com Gemini AI

Este repositório segue diretrizes estritas de desenvolvimento definidas no arquivo `GEMINI.md`. A IA atua como um **Engenheiro de Dados Sênior**, garantindo:

1.  **Chain of Thought**: Análise lógica prévia (Fonte -> Sujeira -> Tratamento -> Validação).
2.  **Código Seguro**: Proteção contra *Type Errors*, tratamento de exceções específico e validação de schemas.
3.  **Manutenibilidade**: Código modular, tipado (`Type Hints`) e documentado.

## ⚙️ Pipelines Ativos

### 1. Tratamento de Faturamentos Comerciais
*Local: `/faturamento_comercial`*

Pipeline responsável por normalizar IDs de faturamento extraídos de múltiplas planilhas do Google Sheets.
*   **Input**: Links de exportação do Google Sheets.
*   **Regras de Negócio**:
    *   Remoção de cabeçalhos mesclados.
    *   Limpeza de prefixos alfanuméricos (`SOL`, `B-`, `X-`).
    *   **Normalização Estrita**: Preenchimento com zeros à esquerda (`zfill`) para garantir IDs com **7 dígitos**.
    *   Deduplicação global de registros.

### 2. Produtividade Comercial
*Local: `/produtividade_comercial`*

Pipeline consolidado para processamento de relatórios de produtividade (Notas de Serviço) extraídos do sistema legado (arquivos `.XLS` tabulados).
*   **Input**: Arquivos `.XLS` organizados por pastas de ano (`2024`, `2025`, `2026`).
*   **Lógica de Seleção**:
    *   Processa todos os arquivos mensais fechados.
    *   Identifica e processa **apenas o arquivo "Abertas" mais recente** (baseado no nome/data), ignorando versões obsoletas.
*   **Regras de Negócio**:
    *   **Padronização de Datas**: Conversão de múltiplos formatos (`dd.mm.yyyy` e `ddMMyyyy`) para `datetime` unificado.
    *   **Mapeamento de Colunas**: Renomeação de campos técnicos (`InícioAvar` -> `Inicio da Nota`, `Concl.desj` -> `Conc. desejada`).
    *   **Classificação de Vistoria**: Análise do campo "Nº do pedido" para identificar vistorias (`VV`, `V V`, `VV.`).
    *   **Limpeza**: Remoção de colunas técnicas desnecessárias e linhas sem número de nota.
    *   **Output**: CSV separado por ponto e vírgula (`;`) com encoding `utf-8-sig` (compatível com Excel BR).

## 📦 Como Executar

### Instalação das Dependências
```bash
pip install pandas requests
```

### Execução dos Pipelines

**Para Faturamento:**
```bash
cd faturamento_comercial
python etl_pipeline.py
```

**Para Produtividade:**
```bash
cd produtividade_comercial
python etl_produtividade.py
```

## 📄 Licença
Este projeto é privado e de uso exclusivo da SIPEL.

# Guia de Padronização da Carteira de Juazeiro

# planilha Novembro de 2024

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="CARTEIRA NOVEMBRO 24",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/11/2024", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"CRITÉRIO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "V. PROJETO", "VALOR 30%", "CARTEIRA", "OBRAS SIMPLIFICADAS", "TECNICO FECHAMENTO", "VISITA PRÉVIA", "PRÉ FECHAMENTO"})
in
    #"Colunas Removidas"

# planilha Dezembro 2024

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="CARTEIRA DEZEMBRO 24",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/12/2024", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"CRITÉRIO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", "PAT", "SI DE PG", "VALOR 30%", "SITUAÇÃO", "CARTEIRA", "OBRAS SIMPLIFICADAS", "TECNICO FECHAMENTO", "VISITA PRÉVIA", "PRÉ FECHAMENTO", "V. PROJETO"})
in
    #"Colunas Removidas"

# planilha Janeiro 2025

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="CARTEIRA JANEIRO 25",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/01/2025", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"CRITÉRIO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", "VALOR 30%", "SITUAÇÃO", "CARTEIRA", "OBRAS SIMPLIFICADAS", "TECNICO FECHAMENTO", "VISITA PRÉVIA", "PRÉ FECHAMENTO", "SITUAÇÃO_1", "SI PG", "PG INICIAL", "PG FINAL", "V. PROJETO"})
in
    #"Colunas Removidas"

# planilha Feveiro 2025

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="CARTEIRA FEVEREIRO 25",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/02/2025", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"CRITÉRIO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", "CARTEIRA", "OBRAS SIMPLIFICADAS", "TECNICO FECHAMENTO", "VISITA PRÉVIA", "PRÉ FECHAMENTO", "SI PG", "PG INICIAL", "PG FINAL", "VALOR 25%", "LINK MAPS", "V. PROJETO"})
in
    #"Colunas Removidas"

# planilha março 2025

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="CARTEIRA MARÇO 25",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/03/2025", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"PROJETO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", "CARTEIRA", "OBRAS SIMPLIFICADAS", "TECNICO FECHAMENTO", "VISITA PRÉVIA", "PRÉ FECHAMENTO", "SI PG", "PG INICIAL", "PG FINAL", "VALOR 25%", "PRE FECHAMENTO", "OBS", "V. PROJETO"})
in
    #"Colunas Removidas"

# planilha abril 2025

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="CARTEIRA ABRIL 25",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/04/2025", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"PROJETO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", "CARTEIRA", "OBRAS SIMPLIFICADAS", "TECNICO FECHAMENTO", "VISITA PRÉVIA", "PRÉ FECHAMENTO", "SI PG", "PG INICIAL", "PG FINAL", "VALOR 25%", "PRE FECHAMENTO", "OBS", "V. PROJETO"}),
    #"Colunas Renomeadas" = Table.RenameColumns(#"Colunas Removidas",{{"PST EXEC", "PST EXEC"}, {"TITULO", "TÍTULO"}})
in
    #"Colunas Renomeadas"

# planilha maio 2025

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="CARTEIRA MAIO 25",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/05/2025", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"PROJETO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "SEPARAR MATERIAL", "DATA DESLIG", "CARTEIRA", "OBRAS SIMPLIFICADAS", "SI PG", "PG INICIAL", "PG FINAL", "PRE FECHAMENTO", "V. PROJETO", "STATUS 1"}),
    #"Colunas Renomeadas" = Table.RenameColumns(#"Colunas Removidas",{{"STATUS 1_1", "STATUS 1"}, {"TITULO", "TÍTULO"}})
in
    #"Colunas Renomeadas"

# planilha junho 2025

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="CARTEIRA JUNHO 25",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/06/2025", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"PROJETO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "SEPARAR MATERIAL", "CARTEIRA", "OBRAS SIMPLIFICADAS", "SI PG", "PG INICIAL", "PG FINAL", "PRE FECHAMENTO", "V. PROJETO", "STATUS 1"}),
    #"Colunas Renomeadas" = Table.RenameColumns(#"Colunas Removidas",{{"STATUS 1_2", "STATUS 1"}, {"TITULO", "TÍTULO"}})
in
    #"Colunas Renomeadas"

# planilha julho 2025

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="CARTEIRA JULHO 25",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/07/2025", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"PROJETO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "SEPARAR MATERIAL", "OBRAS SIMPLIFICADAS", "SI PG", "PG INICIAL", "PG FINAL", "PRE FECHAMENTO", "V. PROJETO", "STATUS 1"}),
    #"Colunas Renomeadas" = Table.RenameColumns(#"Colunas Removidas",{{"STATUS 1_1", "STATUS 1"}, {"TITULO", "TÍTULO"}})
in
    #"Colunas Renomeadas"

# planilha agosto 2025

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="CARTEIRA AGOSTO 25",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/08/2025", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"PROJETO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "SEPARAR MATERIAL", "OBRAS SIMPLIFICADAS", "SI PG", "PG INICIAL", "PG FINAL", "PRE FECHAMENTO", "V. PROJETO", "STATUS 1"}),
    #"Colunas Renomeadas" = Table.RenameColumns(#"Colunas Removidas",{{"STATUS 1_2", "STATUS 1"}, {"TITULO", "TÍTULO"}})
in
    #"Colunas Renomeadas"

# planilha setembro 2025

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UoiSdTEfKbAUXK5P6izPO19zEwop7hld9z-UDRbOKt4/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name=" CARTEIRA SETEMBRO 25",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Cabeçalhos Promovidos",{{"PROJETO", type text}}),
    #"UTD inserida" = Table.AddColumn(#"Tipo Alterado", "COORD", each "JUAZEIRO", type text),
    #"Periodo carteira inserido" = Table.AddColumn(#"UTD inserida", "Carteira", each "01/09/2025", type text),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Periodo carteira inserido", {"PROJETO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CRITÉRIO", "NOTA", "SEPARAR MATERIAL", "OBRAS SIMPLIFICADAS", "SI PG", "PG INICIAL", "PG FINAL", "PRE FECHAMENTO", "V. PROJETO", "STATUS 1"}),
    #"Colunas Renomeadas" = Table.RenameColumns(#"Colunas Removidas",{{"STATUS 1_2", "STATUS 1"}, {"TITULO", "TÍTULO"}})
in
    #"Colunas Renomeadas"

# planilha novembro 2025

let
    Fonte = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1UCpxyV_pd2TUet6JnefEi9_z80Z_1-8PQxS230soATo/edit?usp=sharing"),
    #"CARTEIRA NOVEMBRO 24_Table" = Fonte{[name="BASE GERAL",ItemKind="Table"]}[Data],
    #"Cabeçalhos Promovidos" = Table.PromoteHeaders(#"CARTEIRA NOVEMBRO 24_Table", [PromoteAllScalars=true]),
    #"Linhas Filtradas" = Table.SelectRows(#"Cabeçalhos Promovidos", each ([CARTEIRA] <> "" and [CARTEIRA] <> "AGOSTO" and [CARTEIRA] <> "JULHO")),
    #"UTD inserida" = Table.AddColumn(#"Linhas Filtradas", "COORD", each "JUAZEIRO", type text),
    #"Colunas Renomeadas1" = Table.RenameColumns(#"UTD inserida",{{"STATUS", "STATUS 1"}}),
    #"Personalização Adicionada" = Table.AddColumn(#"Colunas Renomeadas1", "Carteira", each 
    let
        // Tenta converter direto caso já seja data (ex: 13/01/2026 -> 01/01/2026)
        DataDireta = try Date.StartOfMonth(Date.From([CARTEIRA])) otherwise null,

        // Lógica para tratar texto (Ex: "Janeiro" ou "Janeiro 2026")
        LogicaTexto = 
            let
                // Padroniza: Remove espaços e coloca Primeira Maiúscula
                TextoLimpo = Text.Proper(Text.Trim(Text.From([CARTEIRA]))),
                ListaMeses = {"Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"},
                
                // Quebra o texto por espaço
                Partes = Text.Split(TextoLimpo, " "),
                NomeMes = Partes{0},

                // Regra do Ano: Se tiver 2 partes usa a 2ª como ano, senão fixa 2025
                Ano = if List.Count(Partes) > 1 then Number.From(Partes{1}) else 2025,

                // Acha o numero do mês na lista
                NumMes = List.PositionOf(ListaMeses, NomeMes) + 1
            in
                if NumMes > 0 then #date(Ano, NumMes, 1) else null
    in
        // Se conseguiu converter data direta usa ela, senão usa a lógica de texto
        if DataDireta <> null then DataDireta else LogicaTexto,
    type date
),
    #"Tipo Alterado" = Table.TransformColumnTypes(#"Personalização Adicionada",{{"PROJETO", type text}}),
    #"Erros Removidos" = Table.RemoveRowsWithErrors(#"Tipo Alterado", {"PROJETO"}),
    Personalizar1 = Table.AddColumn(#"Erros Removidos", "PROJETO_FATO", each if Text.Length([PROJETO]) < 7 then "0" & [PROJETO] else [PROJETO], type text),
    #"Colunas Removidas" = Table.RemoveColumns(Personalizar1,{"PROJETO", "CARTEIRA"}),
    #"Colunas Renomeadas" = Table.RenameColumns(#"Colunas Removidas",{{"PSTP INICIAL", "PSTP"}, {"ENERGIZAÇÃO", "DATA DE ENERG."}, {"PSTP FINAL", "PST REALZ"}}),
    #"Linhas Filtradas1" = Table.SelectRows(#"Colunas Renomeadas", each ([STATUS 1] <> "RETIRADA COELBA" and [STATUS 1] <> "RETIRADA PROGRAMAÇÃO" and [STATUS 1] <> "SEM CAPACIDADE EXECUTIVA")),
    #"Valor Substituído" = Table.ReplaceValue(#"Linhas Filtradas1","CONCLUÍDA","CONCLUIDA",Replacer.ReplaceText,{"STATUS 1"})
in
    #"Valor Substituído"

# Fato_carteira_juazeiro

let
    Fonte = Table.Combine({Sup_Jzr_janeiro2025, Sup_Jzr_feveiro2025, Sup_Jzr_março2025, Sup_Jzr_abril2025, Sup_Jzr_maio2025, Sup_Jzr_junho2025, Sup_Jzr_julho2025, Sup_Jzr_agosto2025, Sup_Jzr_2025_2026}),
    #"Colunas Removidas" = Table.RemoveColumns(Fonte,{"STATUS"}),
    #"Colunas Renomeadas" = Table.RenameColumns(#"Colunas Removidas",{{"STATUS 1", "STATUS"}}),
    #"Valor Substituído" = Table.ReplaceValue(#"Colunas Renomeadas","","NÃO DEFINIDO",Replacer.ReplaceValue,{"STATUS"}),
    #"Valor Substituído1" = Table.ReplaceValue(#"Valor Substituído","MANTER","",Replacer.ReplaceValue,{"PST REALZ"}),
    #"Linhas Filtradas" = Table.SelectRows(#"Valor Substituído1", each ([STATUS] <> "CANCELADA" and [STATUS] <> "PARALIZADA" and [STATUS] <> "RETIRADA ")),
    #"Coluna Condicional Adicionada" = Table.AddColumn(#"Linhas Filtradas", "PST EXEC FATO", each if [PST REALZ] = "" then [PST EXEC] else [PST REALZ]),
    #"Colunas Removidas1" = Table.RemoveColumns(#"Coluna Condicional Adicionada",{"PST REALZ", "PST EXEC"}),
    #"Colunas Renomeadas1" = Table.RenameColumns(#"Colunas Removidas1",{{"PST EXEC FATO", "PST EXEC"}}),
    #"Texto Aparado" = Table.TransformColumns(#"Colunas Renomeadas1",{{"PROJETO_FATO", Text.Trim, type text}}),
    #"Texto Limpo" = Table.TransformColumns(#"Texto Aparado",{{"PROJETO_FATO", Text.Clean, type text}}),
    #"Colunas Renomeadas2" = Table.RenameColumns(#"Texto Limpo",{{"AVANÇO", "AVNP"}}),
    #"Removed Errors" = Table.RemoveRowsWithErrors(#"Colunas Renomeadas2", {"PV. FIM"})
in
    #"Removed Errors"
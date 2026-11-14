---
name: identificador-de-dados
description: Analisa e compara dados de forma específica, verificável e contextualizada, classificando cada campo ou registro como idêntico, equivalente, distinto, não comparável ou inconclusivo, com evidência tirada dos dados reais. Use sempre que for identificar o que um dado significa, comparar colunas ou bases (ex.: MODIS × VIIRS), dizer se campos são "iguais", decidir o que reaproveitar ou converter numa harmonização, ou validar uma afirmação sobre dados. Também quando o usuário pedir "identificar os dados", "conferir se são idênticos", "o que dá para reutilizar".
---

# Identificador de Dados

Examine os **dados reais e suas fontes** antes de concluir. Nunca troque a análise por explicação genérica nem infira significado só pelo nome da coluna.

## Passo a passo (para cada análise)

### 1. Identificar o significado
Verifique, com consulta aos dados e à documentação da fonte:
origem, campos, tipos, unidades, período, localização, método de coleta e **o que cada registro representa**.

### 2. Definir o critério de comparação
Diga quais atributos serão comparados e por quê. Separe três coisas diferentes:
- igualdade de **valores**;
- identidade de **registros**;
- identidade do **evento/objeto** representado.

### 3. Classificar com precisão
| Classe | Quando usar |
|---|---|
| **Idêntico** | Coincide exatamente em todos os atributos do escopo declarado, **sem transformação** (formato, unidade e regra de geração iguais). |
| **Equivalente sob um critério** | Mesmo valor/significado **após transformação válida e explicitada** (ex.: 1 km → 1.000 m). Não afirmar que os registros completos são idênticos. |
| **Distinto** | Diferenças verificáveis. Nomeie os campos diferentes e explique a relevância. |
| **Não comparável diretamente** | Medem coisas diferentes ou sob condições incompatíveis. |
| **Inconclusivo** | Falta evidência. Diga exatamente o que falta. |

### 4. Investigar o motivo
Para cada resultado: evidência, regra aplicada e consequência prática.
Separe **diferença observada** de **causa possível**. Causa não comprovada = hipótese, com o teste que a verificaria.

### 5. Verificar qualidade e contexto
- Diferencie **zero**, **ausência**, **valor inválido** e **falta de observação**.
- Examine duplicatas, precisão/casas decimais, arredondamento, fuso horário (UTC × local), cobertura e mudanças no método de coleta.
- Valores iguais ≠ mesmo evento.

### 6. Justificar qualquer transformação
Preserve os dados originais. Registre conversões, filtros, tolerâncias e critérios de correspondência.
Não use tolerância arbitrária. Não remova duplicatas sem definir antes o que identifica um registro.

### 7. Entregar conclusões rastreáveis
Quando útil, entregue a tabela:

| item comparado | classificação | critério | evidência (valor/consulta real) | justificativa | limitações |
|---|---|---|---|---|---|

Use exemplos concretos dos dados analisados. Não invente fontes, valores ou causas.

## Regras para dados de satélite e queimadas
- Antes de comparar contagens, verifique **sensor, produto, resolução, horário de passagem, cobertura e critério de detecção**.
- Foco detectado ≠ incêndio ≠ área queimada.
- Não atribua aumento de detecções a aumento real de fogo sem avaliar mudanças na observação (troca de sensor, deriva de órbita, nova versão do produto).

## Como executar neste projeto
- Fonte local: `data/raw/*.parquet` (colunas reduzidas) e `data/processed/grid_monthly.parquet`.
- Para colunas originais completas, ler um trecho do CSV do FIRMS (`Range: bytes=0-2000000`), com `dtype=str` para não perder zeros à esquerda e casas decimais.
- Consultas com DuckDB pelo `.venv` do projeto. Coloque os testes como células no notebook pertinente (ex.: `notebooks/00_entendendo_dados.ipynb`).

## Regra central
Toda conclusão diz **o que foi identificado, por qual critério, com qual evidência e até onde ela vale**.

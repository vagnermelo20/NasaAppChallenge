# TASKS — equipe de 2 pessoas (ref.: spec.md / plan.md)

Marque `[x]` ao concluir. Horas = estimativa de trabalho focado.
Cada tarefa aponta para o requisito (R#) ou critério de aceite (A#) que atende.

## Fase 1 — Dados e entendimento ✅ concluída
- [x] Setup: repo GitHub, venv, requirements, kernel "Python (hotspots)"
- [x] R1 Download FIRMS Brasil: MODIS 2001–2025, VIIRS S-NPP 2012–2025 (`notebooks/01_dados.ipynb`)
- [x] R3 Grade 0,25° × mês × sensor → `data/processed/grid_monthly.parquet` (precisa ser regerada, ver A1)
- [x] Análise dos dados: notebooks 00, 02 e 03 (campos, versão do MODIS, pixel)
- [x] Checkpoint 1: razão VIIRS/MODIS ≈ 3,8 estável (2012–2021)

**Descobertas que mudaram o plano:** calibrar com 2012–2021 (deriva orbital depois); `k` separado para Terra e Aqua;
`type` do MODIS mudou em 2018 → máscara única de fontes estáticas; pixel MODIS ≈ 7× o VIIRS → harmonizar só por célula/mês.

---

## Quem faz o quê
| Pessoa | Frente | Entrega principal |
|---|---|---|
| **A — Dados/Ciência** | harmonização, validação, dados 2026 | `harmonized.parquet` + `reports/metrics.json` + figuras |
| **B — Front-end** | site do projeto (app web) | app funcionando com o calendário |
| **A + B juntos** | deploy, README, vídeo, envio | link público + vídeo + submissão |

**Contrato entre as duas frentes** (definido no `plan.md`): `data/processed/harmonized.parquet` com
`lat, lon, ano, mes, focos_harmonizados, fonte, dado_incompleto`.
B começa com um **mock** nesse formato; quando A entregar o arquivo real, B só troca o caminho.

---

## Pessoa A — Dados/Ciência

### Fase 2 — Harmonização · R2, R3, R4, R5 ← PRIORIDADE
- [ ] **A1** (1 h) Regerar a grade com colunas `satellite` (Terra/Aqua/N) e `daynight` → `grid_monthly.parquet` v2 · R3
- [ ] **A2** (1 h) Máscara de fontes estáticas: células 0,25° com `type=2` em qualquer ano/sensor → `static_mask.parquet`; aplicar na grade · R2
- [ ] **A3** (2 h) `notebooks/04_harmonizacao.ipynb`: `k_Terra` e `k_Aqua` por bloco 5° × mês (2012–2021), fallback nacional se < 30 focos · R4
- [ ] **A4** (1 h) Série final: 2001–2011 MODIS convertido (jan/2001–jun/2002 só Terra), 2012→ VIIRS real → `harmonized.parquet` · R5
- [ ] **A5** (0,5 h) Coluna `dado_incompleto` para meses com dias sem observação · R5c
- [ ] **A6** (0,5 h) Gráfico anual bruto × harmonizado → `reports/harmonizado_anual.png`
- **Checkpoint 2 (A1):** sem degrau artificial em 2012 nem em jul/2002 → **avisar B**

### Fase 3 — Validação · R6
- [ ] **A7** (2 h) `notebooks/05_validacao.ipynb`: leave-one-year-out em 2012–2021; correlação mensal, erro relativo, % acerto do mês de pico → `reports/metrics.json` + figuras
- [ ] **A8** (1 h, opcional) Testar variações e manter só se melhorar: confiança MODIS ≥ 50; `k` separado dia/noite; regressão log
- **Checkpoint 3 (A2):** correlação ≥ 0,85 e mês de pico ≥ 80%

### Fase 3b — Ano corrente · R5b
- [ ] **A9** (1,5 h) Pedir MAP_KEY; baixar 2026 via API do FIRMS (VIIRS S-NPP NRT); aplicar a mesma máscara e agregar; anexar ao `harmonized.parquet` com `dado_incompleto=True` no mês corrente

### Apoio à entrega
- [ ] **A10** (1 h) Texto da página Metodologia em inglês → `docs/metodologia.md` (método, métricas, limitações: deriva orbital, versão do `type`, foco ≠ incêndio)

---

## Pessoa B — Front-end (site do projeto) · R7–R11
**Passo a passo detalhado, com critério de "pronto" em cada etapa: [`frontend_pessoa_B.md`](frontend_pessoa_B.md).**

- [x] **B0** (15 min) Ambiente: `app/app.py` abrindo com `streamlit run`
- [x] **B1** (5 min) Rodar `app/make_mock.py` (script já criado) e ligar o app ao mock
- [x] **B2** (30 min) Layout: barra lateral de filtros + abas Calendar / Trends / Methodology / About
- [x] **B3** (2 h) Região: desenho no mapa (retângulo/polígono) ou lat/lon + raio · R7
- [x] **B4** (1,5 h) Consulta DuckDB da região por ano × mês em < 3 s · R7, A3
- [x] **B5** (2 h) Calendário heatmap ano × mês (viridis), meses incompletos marcados · R8
- [x] **B6** (1,5 h) Cartão mês atual × mediana + modo anomalia (PuOr) · R9
- [x] **B7** (1 h) Aba Trends: série anual + sazonalidade
- [x] **B8** (1 h) Download CSV da região (+ PNG pelo botão do Plotly) · R10
- [x] **B9** (1 h) Aba Methodology com texto de A10, figuras e `metrics.json` · R11
- [ ] **B10** (1 h) Acabamento e acessibilidade (inglês, aviso "hotspots ≠ fires", celular)
- [ ] **B11** (30 min) Trocar o mock pelo `harmonized.parquet` real após o Checkpoint 2 de A
- [x] **B12** Camada de identificação de atividade de fogo solicitada pelo usuário: aba Fire map, cores/legenda, sensor/mês, detalhes e CSV por célula · complemento de R7
- **Checkpoint 4 (A3):** consulta < 3 s com o arquivo real

Validação da entrega B3–B5/B8 com mock: 7 testes em `app/test_delivery.py`;
consulta fria do Pantanal (2001–2025, 300 meses) em 0,247 s, soma conferida por SQL independente;
CSV conferido contra o calendário via HTTP para Pantanal, Matopiba, Acre e região sem focos.
Seleção por coordenadas validada na aplicação; eventos de desenho/edição/exclusão cobertos em Python.
Interação Leaflet e exportação PNG no navegador aguardam conferência manual (controle do Chrome não autorizado).
Checkpoint 4 com o arquivo real continua pendente.

Ajuste de estabilidade B3: desenho/edição ficam em um fragmento isolado e só atualizam
o calendário após **Apply map selection**. No modo por coordenadas, a prévia do mapa
é opcional; os campos persistem ao trocar de modo. Recursos externos reduzidos a
Leaflet + Leaflet.Draw (2 scripts e 2 estilos). Sete testes passaram após o ajuste;
consulta por coordenadas confirmada em execução sem carregar o componente do mapa.

Entrega B6/B7/B9: comparação do último mês disponível com o mesmo mês em anos
anteriores completos; anomalias PuOr centradas em zero, iguais às exportadas no CSV.
Meses incompletos não recebem anomalia; mediana zero e histórico ausente ficam sem percentual.
Categorias requerem pelo menos 3 anos de referência. Trends diferencia anos completos e parciais.
Methodology carrega documentos/métricas quando disponíveis, com aviso provisório enquanto faltam.
Validação: 11 testes passaram, quatro abas conferidas via API local, CSV/calendário coerentes.
B10 permanece pendente da conferência visual no celular/Chrome; B11 depende da Pessoa A.

Acabamento B10 implementado: calendário com números opcionais, marcadores de dados
incompletos mantidos, atalhos para três regiões de exemplo (círculos de 100 km,
não limites oficiais), contagem de centros selecionados e aviso para seleção vazia.
Formato e valores básicos do arquivo de entrada são verificados; erro no arquivo real
não causa retorno silencioso ao mock. Versões mínimas das dependências documentadas.
Quatorze testes passaram; exemplos e exibição de números conferidos via API local.
Roteiro de conferência visual, integração B11 e preparação de publicação: `app/VERIFY.md`.
Ainda não há `harmonized.parquet`, documento final ou métricas entregues pela Pessoa A.

Fire map usa contagens observadas `n_modis`/`n_viirs` da grade existente, separadas
do calendário mock. Classes fixas Viridis: 1–5, 6–20, 21–100, 101–500, >500
detecções/célula/mês. Não representa severidade nem área queimada. Fundo sem cor
não comprova ausência de fogo; revisão final de cobertura permanece pendente.
Validação: 18 testes passaram; totais e CSV conferidos por SQL independente
(VIIRS dez/2025: 36.722 em 4.141 células; MODIS set/2024: 155.119 em 6.359 células).
A aparência no navegador e a interação Leaflet ainda requerem conferência manual.

---

## Juntos (A + B) — Entrega · A4
- [ ] **J1** (1 h) Deploy no Streamlit Community Cloud direto do GitHub; testar o link público em 3 regiões
- [ ] **J2** (1 h) README final em inglês: problema, método, link do app, dados NASA usados, como rodar, equipe
- [ ] **J3** (2 h) Vídeo de 30 s + slides: história (incêndio real) → degrau de 2012 sumindo → demo do calendário
- [ ] **J4** (30 min) Envio no portal do Space Apps com **2 h de folga** antes do prazo

Preparação J1/J2: README em inglês atualizado com execução local, contrato,
funcionalidades, limitações, papéis da equipe e estado real da entrega.
Link público e créditos finais permanecem pendentes. A equipe escolheu esperar
os dados reais antes de publicar (sem deploy do mock).
`python -m app.check_release` faz verificação somente de leitura dos artefatos
da Pessoa A; não gera dados nem certifica validade científica. Ainda faltam
`harmonized.parquet`, `docs/metodologia.md`, `reports/metrics.json` e
`reports/harmonizado_anual.png`. A próxima integração/publicação depende dessa entrega.
Verificação desta preparação: 16 testes passaram; geração do mock a partir de uma
cópia temporária dos arquivos versionados confirmou 1.221.364 registros (2001–2025),
sem modificar a base científica original. A publicação permanece aguardando dados reais.

---

## Pontos de sincronização
| Quando | O quê |
|---|---|
| Início | A e B leem este arquivo e o contrato do `plan.md` |
| A passa Checkpoint 2 | B troca o mock pelo `harmonized.parquet` real |
| A termina A7 e A10 | B coloca métricas, figuras e texto na aba Methodology (B9) |
| Antes de J1 | os dois testam o app juntos com 3 regiões (Pantanal, Matopiba, Acre) |
| Antes de J4 | os dois revisam vídeo, README e link |

## Se o tempo apertar, corte nesta ordem
A8 → B7 → modo anomalia do B6 (mantém o cartão) → polígono no B3 (fica retângulo/lat-lon) → A9 (série vai até 2025) → B9 vira imagens estáticas.
**Nunca corte:** A1–A4, A6, A7, B3 (lat/lon), B4, B5, B8, J1, J4.

> Nada do que foi feito além do escopo (notebooks 00, 02, 03, skill, figuras) deve ser apagado: são reaproveitados na aba Methodology, no vídeo e na apresentação.

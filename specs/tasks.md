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
- [x] **A1** (1 h) Regerar a grade com colunas `satellite` (Terra/Aqua/N) e `daynight` → `grid_sat.parquet` (o `grid_monthly.parquet` antigo foi mantido para o mock) · R3
- [x] **A2** (1 h) Máscara de fontes estáticas: células 0,02° com `type` 1/2/3 em ≥ 2 anos (qualquer sensor) → `static_mask.parquet`; aplicar na grade · R2
- [x] **A3** (2 h) `notebooks/04_harmonizacao.ipynb`: `k_Terra` e `k_Aqua` por bloco 5° × mês (2012–2021), fallback nacional se < 30 focos · R4
- [x] **A4** (1 h) Série final: 2001–2011 MODIS convertido (jan/2001–jun/2002 só Terra), 2012→ VIIRS real → `harmonized.parquet` · R5
- [x] **A5** (0,5 h) Coluna `dado_incompleto` para meses com dias sem observação · R5c
- [x] **A6** (0,5 h) Gráfico anual bruto × harmonizado → `reports/harmonizado_anual.png`
- **Checkpoint 2 (A1):** sem degrau artificial em 2012 nem em jul/2002 → **avisar B** ✅ passou (notebook 04)

### Fase 3 — Validação · R6
- [x] **A7** (2 h) `notebooks/05_validacao.ipynb`: leave-one-year-out em 2012–2021; correlação mensal, erro relativo, % acerto do mês de pico → `reports/metrics.json` + figuras
- [x] **A8** *(testado: k dia/noite piora as métricas → mantido o método base)* (1 h, opcional) Testar variações e manter só se melhorar: confiança MODIS ≥ 50; `k` separado dia/noite; regressão log
- **Checkpoint 3 (A2):** correlação ≥ 0,85 e mês de pico ≥ 80% — ✅ nacional e bloco; ⚠️ célula: correlação 0,951 ok, mês de pico 72,7% (< 80%) → decisão pendente

### Fase 3a — Melhoria e prova da harmonização
- [x] **A11** Combinação Terra/Aqua pelo inverso da variância + `k` local 2° encolhido para o bloco 5° (notebook 04)
- [x] **A12** `notebooks/07_prova_harmonizacao.ipynb`: "MODIS diz X, VIIRS diz Y" por região × mês; figura `prova_antes_depois.png`; referência NOAA-20 × S-NPP (`data/raw/noaa20/`, fora do git)
- **Resultado:** região 2° × mês: diferença mediana 14% (MODIS cru 74%), 66% dentro de ±20%, correlação 0,992; dois VIIRS iguais: 8% / 85%

- [x] **A13** Debate de métodos (3 agentes: Físico, Estatístico, Avaliador) para subir a concordância; testados com regras fixadas antes (`notebooks/exp_debate_metodos.py`): covariáveis do MODIS rejeitadas; faixa de incerteza calibrada adotada (cobre 89,9%); concordância anual 92% dentro de ±20%; na nossa comparação, dois VIIRS iguais concordam 85% por mês e o limite só de contagem seria 93,6%; não esperamos 90–100% mensal ponto a ponto com estes dados (o número mensal honesto é 66%; o anual, 92%)
- [x] **A15** Faixa de incerteza recalibrada sem filtrar pelo VIIRS (cobre 89,9%; ≤ 20 focos MODIS: −70% a +249%); docs e recado ao B corrigidos (o sinal −6% estava errado); spec R2/R4/R5b alinhadas ao método entregue
- [x] **A14** Notebook 05 refeito com o método final (erro anual: Brasil 1,6%, bloco 8,3%, célula 25,3%; fora da calibração 6,0%); preserva a seção do notebook 07 no `metrics.json`

### Fase 3c — Fechamento após a revisão independente (14/11/2026)
- [x] **A16** 2026 recortado às células do Brasil (conferir as 21 células novas) e anexado ao `grid_sat`
- [x] **A17** Textos honestos: teto (85% / 93,6%), deriva como hipótese com evidência, "S-NPP sem dados desde 02/11/2026", 92% = escala anual; nb07, A13, metodologia e README
- [x] **A18** Declaração do A2 não atingido (spec, metodologia, handoff) e regra de confiabilidade do mês de pico
- [x] **A19** Base de focos por ano com `peso_harmonizado` (R12) + teste da soma = harmonized — `notebooks/08_base_focos.ipynb`, `data/processed/focos/` (22,5 mi focos, 26 arquivos, 184 MB, maior 12,9 MB; soma dos pesos = harmonized com diferença máx. 1e-10)
- [x] **A20** Robustez no nb07: estratos pela estimativa convertida; grade de 2° deslocada 1°; extrapolação para trás (2017–21 → 2012–14) ao lado do LOYO dos mesmos anos
- [x] **A21** Rodar de novo nb06/nb07, atualizar números na metodologia e no handoff; marcar o relatório de pendências do B como revisado

### Fase 3b — Ano corrente · R5b
- [x] **A9** 2026 baixado e anexado (notebook 06): SP até 31/07, NRT depois; 39.510 linhas; NRT com todos os dias conta como completo. **O S-NPP parou em 02/11/2026** (confirmado no data_availability do FIRMS); nov/2026 incompleto. Próximo passo possível: continuar com NOAA-20/21

### Apoio à entrega
- [x] **A10** (1 h) Texto da página Metodologia em inglês → `docs/metodologia.md` (método, métricas, limitações: deriva orbital, versão do `type`, foco ≠ incêndio)

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
- [x] **B10** Acabamento implementado: fonte 16 px, mapa compacto opcional, foco visível no botão de tela cheia e orientação para alternativas em tabela. Conferência final com A/B20; esta entrega não foi testada por solicitação do usuário.
- [x] **B11** Integrar `harmonized.parquet` real, grade nova, metadados e provas entregues por A; revisão visual continua em B10 · ver `specs/handoff_A_para_B.md`
- [x] **B12** Camada de identificação de atividade de fogo solicitada pelo usuário: aba Fire map, cores/legenda, sensor/mês, detalhes e CSV por célula · complemento de R7
- [x] **B13** Interface EMBER solicitada pelo usuário: mapa principal, catálogo lateral, tema consistente, indicadores, opacidade e carregamento condicional das abas · R7–R11
- [x] **B14** Revisão visual solicitada: atlas escuro/satélite, símbolos proporcionais por centro de célula, grade alternativa, legenda horizontal, contorno regional e expansão do mapa · R7/R8
- [x] **B21** Visual solicitado baseado no FIRMS: satélite como fundo padrão e pontos vermelhos pequenos nas coordenadas reais dos arquivos anuais de focos; grade mensal preservada como opção. Filtro por mês/sensor/região, sem halos nem posições inventadas. 23 testes passaram; aparência no Chrome aguarda conferência do usuário.
- [x] **B15** Destaque e anomalia usando o **último mês completo** (out/2026), com aviso dos meses mais recentes incompletos. Calendário e CSV preservados; seleção sem mês completo recebe mensagem explícita. 24 testes passaram; conferência na aplicação real: out/2026 = 182.848, −28,5% vs mediana histórica, aviso de nov/2026 incompleto · R9
- [x] **B16** Fire map lendo `grid_sat.parquet` — feito no B21 (mapa usa `grid_sat` e os pontos de `data/processed/focos/`)
- [x] **B17** Textos finais: orientação do mês de pico junto ao calendário (áreas de ~2° ou centenas de focos/ano; ±1 mês em áreas pequenas); A2 final explicitamente não atingido (73,7%, ±1 mês 90,4%); Methodology e About distinguem acordo mensal 66% e anual 92% em regiões 2°, com os subconjuntos avaliados. About real sem aviso de mock; removidos avisos antigos de validação por executar. 24 testes passaram e as três abas foram conferidas na aplicação local · R11
- [x] **B18** Aba Hotspot search: intervalo UTC inclusivo de até 92 dias, filtro por sensor e coordenadas na região aplicada; lê somente os arquivos anuais necessários. Tabela e CSV de até 200 mil focos, com data, HH:MM UTC, satélite, lat/lon, FRP e peso harmonizado; excesso exige recorte, sem CSV parcial. Comparação em até seis anos soma pesos e rotula pré-2012 como aproximado; intervalos incompletos, sensores indisponíveis e 29/fev inválido não recebem comparação numérica. Faixas mensais não são apresentadas como intervalos de confiança calibrados para dias exatos. 26 testes passaram; API/CSV reais: 1–7/out/2026 = 39.965 focos, consulta 0,233 s; bloqueio >200 mil, intervalo >92 dias e novembro incompleto conferidos · R12
- [x] **B19** Implementado explorador no Calendar para regiões inteiras 2° × mês antes de 2012: soma MODIS filtrado da grade científica, escolhe fatores por contagem bruta, aplica ao harmonizado, mostra limites nominais 90% e cobertura empírica entregue, exporta CSV. Não soma limites nem aplica faixas a dias exatos. Implementação enviada sem testes/conferência por solicitação do usuário; revisão científica e funcional atribuída à Pessoa A.
- [x] **B20** Conferência de `app/VERIFY.md` atribuída à Pessoa A pelo usuário: Chrome, celular, teclado, PNG e região vazia. Não executada nesta entrega, conforme solicitado. — **aceito pela Pessoa A/usuário em 14/11/2026 para publicação** (sem registro de conferência manual item a item do VERIFY.md; reconferir no link público)

**Roteiro do B (ordem sugerida, atualizado em 14/11/2026 depois do B21):**
1. **B15** — último mês completo no destaque (rápido; conserta a demo do R9).
2. **B17** — regra do mês de pico e textos finais (rápido; é o que o jurado lê).
3. **B18** — busca por datas + CSV de focos (a maior; fecha o "specific date range" e o "CSV of hot spots" do enunciado).
4. **B10** e **B20** — acabamento, acessibilidade e conferência manual no Chrome/celular.
5. **B19** — faixa de incerteza (opcional, se sobrar tempo).
6. Com isso pronto: **J1** publicar → **J3** gravar o vídeo com o app no ar → **J2** README final → **J4** enviar.
- **Checkpoint 4 (A3):** consulta < 3 s com o arquivo real

Integração B11: Fire map abre na série real `harmonized.parquet` (2001–2025),
preserva decimais antes de 2012 e sinaliza meses incompletos. O produto alternativo
Sensor observations agrega `grid_sat.parquet` por satélite/dia-noite, com o
pré-processamento científico novo; a grade antiga fica apenas como fallback explícito.
Calendário/Trends/CSV usam a mesma série. About e README refletem dados reais.
Methodology destaca `prova_harmonizacao`, as três figuras principais e o A2/A14 pendente.
Validação: 21 testes passaram; mapa e calendário coincidem em set/2010;
VIIRS observado e harmonizado coincidem em set/2024 (598.825). Não houve alteração
dos dados/modelos da Pessoa A. 2026, publicação e validação científica final continuam pendentes.

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

Redesign EMBER: Fire map é a tela inicial; o catálogo de observações e a exportação
ficam na barra lateral. Legenda/controles acompanham o tema, com opacidade ajustável
e popup de célula. Abas ocultas não geram mapas/gráficos desnecessários.
Dezoito testes existentes e um novo teste de abertura/navegação passaram; cinco
abas e opacidade conferidas via API local. O usuário escolheu fazer a revisão visual.
As pendências científicas e a decisão de não publicar o mock foram preservadas.

Revisão B14 após captura do usuário: a visualização padrão usa símbolos nos centros
das células, mantendo a grade analítica como opção. Não há interpolação nem alteração
dos valores/resolução. Fundos Esri escuro e satélite verificados por HTTP, com crédito
ao provedor e aviso de que imagem de fundo não corresponde à data da observação NASA.
Legenda horizontal compacta e controles redesenhados; componente versionado para
evitar reutilizar a apresentação antiga. Vinte e dois testes passaram; alternância
de fundo/estilo conferida em execução com totais preservados. Instância 8501 reiniciada.
Aspecto final, tela cheia e layout móvel permanecem para conferência visual do usuário.

---

## Front-end para leigos (plano `specs/plano_leigos.md`, 15/11/2026)
- [x] **L1/L2** Mapa único: focos sobre satélite com nomes de lugares, cor pela idade (como o FIRMS), últimos 1/7/30 dias ou datas; desenho da área no mesmo mapa
- [x] **L3** "Your area" em frases (época do fogo, pior mês, quando se preparar, pior ano, último mês × normal) + calendário + barras por ano + CSV
- [x] **L4/L5** 3 abas (Map / How it works / For experts); sem barra lateral; apagados Fire map antigo, grade de análise, catálogo, Lat-Lon + raio, filtro de anos
- [x] **L6/L7** Jargão fora da aba Map (teste automático confere); bloco "Why can we compare 2005 with 2024?"
- [x] **L9** Testes reescritos (22 passam) e conferência no navegador
- [x] **L10** Aba How it works
- [x] **L11** Pedido do usuário: tudo da área na aba Map (calendário/anomalias, dia/semana/mês, sazonalidade, último mês × histórico, incerteza); apagadas For experts, Methodology, Trends e Day & week; aba Search hot spots por lat/lon + raio + datas; manchas de calor de longe e bolinhas de perto
- [ ] **L8** Teste com 2–3 leigos (3 perguntas do plano)
- [x] **L16** Correções solicitadas após revisão: tabela paginada de 5.000 registros, filtro exato da área no DuckDB antes da paginação, totais completos por agregação SQL, cache limitado por entradas e CSV explicitamente da página. FRP bruto (MW), instrumento e dia/noite restaurados no CSV técnico. Comunicação distingue calibração mensal, estimativas diárias pré-2012, percentil relativo e resultado A2 final não atingido; arquivo não é anunciado como dados até hoje. README e VERIFY atualizados em paralelo. Após autorização para testar: 26 testes passaram, incluindo polígono com buraco e última página; API local com dados reais set/2024 em raio 500 km (-10,-50) mostrou 186.089 detecções em 38 páginas, CSVs de 5.000/5.000/1.089 nas páginas 1/2/38 e reset da página ao mudar datas. Conferência visual permanece com a Pessoa A.
- [x] **L17** Pedido do usuário após o L16: CSV e tabela só com o registro unificado (sem satélite/MW/dia-noite), lista e CSV da área completos sem páginas (`area_points`), How it works em palavras simples com os números técnicos só no painel escondido. 26 testes ok.

---

## Juntos (A + B) — Entrega · A4
- [x] **J1** Publicado no Streamlit Community Cloud: **https://ember-fire-calendar.streamlit.app** (branch `main`, `app/app.py`, Python 3.14, `app/requirements.txt`). Testado no link público em 14/11/2026: mapa, calendário (out/2026 −28,5% vs mediana; consulta 0,13 s) e busca por datas (1–7/out/2026: 39.965 focos em 0,14 s, CSV). Mantido acordado pelo fluxo `.github/workflows/manter-app-acordado.yml` (visita a cada 6 h)
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

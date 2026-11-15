# CLAUDE.md — arquivo central do projeto (ler no início de toda sessão)

Projeto: **NASA Space Apps 2026 — "MODIS and VIIRS Hot Spots Harmonization"**. App **EMBER**.
Link público: https://ember-fire-calendar.streamlit.app · Repo: github.com/vagnermelo20/NasaAppChallenge

## Como retomar numa conversa nova (comece por aqui)
1. Leia este arquivo inteiro; depois `specs/tasks.md` (o que está feito/aberto) e `AGENTS.md`.
2. `git pull` na `main`. Rodar o app: `.venv/Scripts/python.exe -m streamlit run app/app.py` (http://localhost:8501) ou `.claude/launch.json` ("ember-app").
3. Testes: `.venv/Scripts/python -m unittest app.test_delivery` (24 testes) e `.venv/Scripts/python -m app.check_release`.
4. O usuário é a **Pessoa A** (dados/ciência); a Pessoa B fez o front-end. Hoje trabalhamos os dois no mesmo repositório, só na `main`.

## Regras (do usuário)
- **Trabalhar só na `main`.** Não criar outras branches.
- **Nunca colocar Claude nos commits** (sem `Co-Authored-By`, sem menção a IA).
- Conversar com o usuário em **português**; o app fica em **inglês**, com palavras simples.
- O que importa é a **harmonização MODIS × VIIRS**; não usar regiões nomeadas (Pantanal etc.) — o usuário desenha a área.
- Toda decisão nova e todo trabalho feito vão **neste arquivo** (seção "Diário").
- Spec-Driven: `specs/spec.md` (o quê), `specs/plan.md` (como), `specs/tasks.md` (tarefas). `AGENTS.md` tem as regras para agentes.

## Dados
- NASA FIRMS, Brasil. MODIS C6.1 Terra (2001–) + Aqua (jul/2002–), pixel 1 km; VIIRS S-NPP 375 m (2012–); 2026 pela API (MAP_KEY no `.env`, fora do git). Sem dados do S-NPP desde 02/11/2026.
- Brutos em `data/raw/` (fora do git). Processados em `data/processed/` (no git).

## Pipeline (notebooks/)
00 entendimento · 01 download + grade · 02 identificação dos campos · 03 versão MODIS e pixel · 04 **harmonização** (→ `harmonized.parquet`, `grid_sat.parquet`, `fatores_k.parquet`, `static_mask.parquet`) · 05 validação deixando o ano de fora · 06 dados de 2026 · 07 prova "MODIS diz X, VIIRS diz Y" + robustez + faixa de incerteza · 08 base de focos por ano com `peso_harmonizado` (`data/processed/focos/`) · **09** `09_serie_diaria.py` série diária/semanal com cascata S-NPP → NOAA-20 → MODIS convertido (`data/processed/diario/`, `semanal.parquet`, `disponibilidade_diaria.parquet`; soma diária = mensal) · experimentos: `exp_debate_*.py`, `exp_v3_conversao.py`.

## Método atual de harmonização (v2) — NÃO é machine learning
1. Filtros: MODIS confiança ≥ 30; VIIRS n|h; máscara de fontes estáticas (células 0,02° com type 1/2/3 em ≥ 2 anos).
2. Contagem por célula 0,25° × mês × satélite.
3. Fator k = ΣVIIRS/ΣMODIS por satélite × bloco 5° × mês (2012–2021), refinado na região 2° com encolhimento bayesiano (λ = 100).
4. Terra e Aqua combinados pelo inverso da variância; só Terra até jun/2002. 2012+ usa VIIRS real.
Resultado (deixando o ano de fora): Brasil erro anual 1,6%; região 2° × mês 66% dentro de ±20% (mediana 13,5%); por ano 92%; dois VIIRS iguais 85%/mês. A2 (pico por célula ≥ 80%) não atingido: 73,7%.
Testado e rejeitado: k dia/noite, vizinhança 3×3, climatologia como prior, covariáveis do MODIS por região×mês (P90 FRP etc.).

## App (app/app.py, Streamlit) — versão para leigos (15/11/2026)
3 abas: **Map** (mapa único: de longe manchas de calor laranja/amarelas, de perto (zoom ≥ 7) **todas** as bolinhas da parte visível do mapa (carregadas sob demanda, sem teto; se passar de 50 mil na tela, pede mais zoom), coloridas pela idade; últimos 1/7/30 dias, 12 meses ou qualquer intervalo desde 2001 (sem limite de dias); popup em hora de Brasília; desenhar a área no mesmo mapa → "Show fire history for this area" → frases simples, calendário (com opção "compare with a usual year"), dia/semana/mês, um ano comum (sazonalidade), barras por ano, "o último mês foi pior que o normal?", demo sem/com harmonização, faixa de incerteza antes de 2012, CSV — tudo da área desenhada) · **How it works** (7 passos simples) · **Search hot spots** (latitude + longitude + raio em km + qualquer intervalo de datas → contagem exata, tabela/CSV com **todos** os focos, sem teto; mapa com todas as bolinhas quando cabem, senão mancha). Sem barra lateral. Metodologia, For experts, Trends e Day & week separados foram apagados. Testes: `.venv/Scripts/python -m unittest app.test_delivery` (24 testes). Mantido acordado por `.github/workflows/manter-app-acordado.yml`.

## Pendências (atualizado 15/11/2026)
- **Entrega:** nomes da equipe (README e submissão), vídeo de 30 s, envio no portal (texto pronto em `docs/submissao_spaceapps.md`).
- **Série diária:** NOAA-20 de 2026 pela API (03–14/11/2026 vazios; S-NPP sem dados desde 02/11); faixa de incerteza diária (D4); medir concordância diária/semanal (D1).
- **Harmonização v3:** lei de potência e quantile mapping testados e rejeitados; resta testar o k físico pela distribuição de FRP (expectativa baixa).
- **App para leigos:** falta o L8 (mostrar a 2–3 leigos e corrigir onde travarem).
- Opcional: contornos de estados/biomas no mapa; teste automático que pegue o calendário vazio (eixo de categorias).

## Plano: harmonização v3 (proposta, ainda não implementada)
Ideia central: converter **cada foco MODIS** (não a soma do mês) pela física da detecção, para capturar a variação de ano a ano que o k médio não captura.
1. **Pareamento** (2012–2021): para cada foco VIIRS, dizer se um pixel MODIS do Aqua da mesma passagem o cobre (já medido no nb 03: curva de detecção 23% a 2–5 MW → 65% > 100 MW).
2. **Modelo de detecção** p(detectado pelo MODIS | FRP, área do pixel, dia/noite) — regressão logística/GAM.
3. **Distribuição de tamanho do fogo** por região × mês: o MODIS só vê a cauda forte; ajustar uma lei de potência truncada (ou lognormal) ao FRP dos focos MODIS e **extrapolar quantos fogos fracos ficaram invisíveis** (estimador de Horvitz–Thompson: cada foco MODIS vale 1/p(FRP) focos "reais", vezes quantos pixels VIIRS cabem nele).
4. Validar com a mesma regra (ano deixado de fora, região 2° × mês) contra o v2; só adotar se ganhar.

## Ideias para a harmonização v3 (5 subagentes independentes, 15/11/2026)
| # | Área | Ideia | Ganho estimado | Custo |
|---|---|---|---|---|
| 1 | Física/amostragem | k físico por ano: probabilidade de detecção p_M(FRP, ângulo, dia/noite) dos pares Aqua×VIIRS + distribuição de FRP (Horvitz–Thompson integrado), encolhido para o v2 | incerto | 25–35 h |
| 2 | Distribuições | mesma família: lei de potência truncada ajustada por máxima verossimilhança censurada, prior hierárquico, peso pela informação de Fisher | +2 a 5 pp (talvez 0) | 15–25 h |
| 3 | Machine learning | LightGBM no resíduo do v2 (features só do MODIS) + intervalos conformais; adotar só se ganhar em 8/10 anos | 66→70–72% | 10–14 h |
| 4 | Bayes espaço-temporal | NegBin hierárquico com BYM2 (vizinhança), inclinação β_r ≠ 1 (não proporcional), sazonalidade RW2, ano AR(1) (R-INLA) | 66→70–72% | 15–25 h |
| 5 | Homogeneização | quantile mapping condicional (bloco × estação), trata MODIS = 0, k varia com o nível de fogo | +3 a 8 pp | 6–10 h |
Convergência: 1 e 2 chegaram sozinhos à mesma ideia (k pela distribuição de FRP); 4 e 5 apontam a mesma falha do v2 (razão não proporcional: k muda com o nível de fogo). Plano: primeiro um diagnóstico de 1 h (o k depende do nível de MODIS? inclinação log V × log M < 1?); se sim, testar o quantile mapping (5) e a inclinação β (versão simples do 4); depois o k físico (1+2).

## Plano: série DIÁRIA harmonizada (proposto em 15/11/2026, ainda não implementado)
Objetivo: escolher um dia e ver um número de focos confiável, na escala VIIRS, com a fonte e a margem de erro daquele dia.
**Regra de cascata por região × dia** ("se não aparecer nada num, usa o outro"):
1. VIIRS S-NPP observou o dia → usa o S-NPP (fonte = `snpp`).
2. S-NPP sem dado naquele dia (falha, fim de missão desde 02/11/2026) → usa NOAA-20 e/ou NOAA-21, escalados para o S-NPP (razão Brasil 2018–2021: NOAA-20/S-NPP = 0,965) (fonte = `noaa20`/`noaa21`).
3. Nenhum VIIRS (antes de 2012) → MODIS convertido pelo `peso_harmonizado` (fonte = `modis_convertido`); se só um dos MODIS passou (Terra ou Aqua), usa o que passou com o seu próprio fator.
4. Nenhum sensor observou → **sem dado** (não é zero fogo).
**Separar "zero fogo" de "não observado":** um sensor conta como "observou o dia" se teve qualquer foco no Brasil naquele dia (o FIRMS não publica a faixa de passagem; limitação documentada).
**Etapas (tarefas D1–D6):**
- D1 (1 h) Medir a concordância diária atual (2012–2021, ano deixado de fora): MODIS convertido × VIIRS por região 2° × dia e por 7 dias.
- D2 (2 h) Tabela de disponibilidade por sensor × dia (2001–2026) e a cascata de fontes; baixar NOAA-20/21 2018–2026 do Brasil.
- D3 (2 h) Série diária `daily_harmonized.parquet` (célula 0,25° × dia, `focos`, `fonte`, `observado`).
- D4 (2 h) Faixa de incerteza diária calibrada (por fonte e por quantidade de focos), como a mensal.
- D5 (2 h) App: gráfico diário da área/intervalo, cor por fonte, faixa de incerteza, opção de média de 7 dias.
- D6 (1 h) Validação e texto honesto: concordância por dia e por 7 dias ao lado da mensal.

## Resultado do teste v3 (15/11/2026, notebooks/exp_v3_conversao.py)
Mesma régua (ano deixado de fora, região 2° × mês, VIIRS ≥ 100), comparado a um v2 simplificado (k bloco × mês, sem refino 2°):
v2 60,3% · lei de potência V=c·M^β 60,8% (erro anual 3,1%, pior) · quantile mapping 59,9% (erro anual 2,9%, pior).
β nacional = 1,06 → a relação VIIRS×MODIS é praticamente **proporcional**; a hipótese "k muda com o nível de fogo" foi **rejeitada**.
O v2 completo (com refino 2°) continua o melhor (66%). Próxima candidata, se houver tempo: k físico pela distribuição de FRP (ideias 1+2), com expectativa baixa.

## Diário
- 15/11/2026 (noite, 6): visual **branco estilo Wikipedia** (`.streamlit/config.toml`: fundo branco, texto #202122, linhas cinza #A2A9B1, títulos com serifa, azul #3366CC só em botões/links, cantos quase retos). "Pick dates" do mapa agora começa em 01/01/2001 (vai até o dado mais novo).
- 15/11/2026 (noite, 5): bolinhas **só de perto e todas**: ao dar zoom (≥ 7) o app busca no DuckDB os focos da parte visível do mapa e desenha todos (streamlit-folium `feature_group_to_add`, sem recarregar o mapa); acima de 50 mil na tela mostra a mancha e pede mais zoom. A mancha some quando as bolinhas aparecem e o raio dela cresce com o zoom (sem quadradinhos). Acabou o "50 mil mais recentes".
- 15/11/2026 (noite, 4): **busca sem teto** (pedido do usuário: "infinito"): tabela e CSV com todos os focos (ex.: 300 km em volta de -5, -45, 2001–2026 = 2.102.367 focos, página em ~3 s); o CSV só é montado ao clicar no botão; a hora fica como data-hora na tabela (0,5 s para 2 mi linhas). Só o desenho de bolinhas no navegador continua nos 50 mil mais recentes (as manchas de calor mostram todos).
- 15/11/2026 (noite, 3): **sem limite de 92 dias** no mapa e na busca (pedido do usuário). O mapa conta e agrupa no DuckDB (manchas com quadrados de 0,05°/0,1°/0,2° conforme o período) e só manda as 50 mil bolinhas mais recentes; 2001–2026 inteiro (22,5 mi focos) em ~1 s. A busca conta todos no círculo. Nova opção "Latest 12 months".
- 15/11/2026 (noite, 2): pedido do usuário: tudo da área desenhada fica na aba Map (calendário com anomalias, dia/semana/mês, sazonalidade, último mês × anos anteriores, incerteza); apagadas as abas For experts, Methodology, Trends e Day & week; nova aba Search hot spots por latitude/longitude + raio (não o Brasil todo); mapa com manchas de calor de longe e bolinhas de perto (troca no navegador, sem recarregar). 24 testes ok.
- 15/11/2026 (noite): usuário pediu app entendível por leigos. Diagnóstico: o mapa do Calendar não mostra os focos (mapa de ruas vazio; `show_area_hotspots` existe mas não é chamada), 6 abas, controles e jargão demais. Plano L1–L9 em `specs/plano_leigos.md` (mapa único com focos + desenho, cor pela idade como no FIRMS, 3 abas: Map / How it works / For experts). Aguardando aprovação.
- 15/11/2026 (noite): **plano para leigos executado** (L1–L7, L9): 3 abas Map / How it works / For experts; mapa único com focos coloridos pela idade e desenho da área; resumo em frases; sem barra lateral; apagados o Fire map antigo, grade de análise, catálogo, Lat-Lon + raio e filtro de anos (app.py 1.540 → ~1.100 linhas). README atualizado. Falta L8 (teste com leigos) e publicar.
- 15/11/2026 (noite): feita a aba **How it works** (L10), explicação para leigos em 7 passos, com o gráfico sem/com harmonização do Brasil. Agora são 7 abas; teste de contagem de abas ajustado (26 testes ok).
- 15/11/2026 (tarde): série diária/semanal (notebooks/09_serie_diaria.py, cascata S-NPP → NOAA-20 → MODIS convertido; soma diária = mensal) e visão Day/Week/Month no Calendar do app. Falta: NOAA-20 de 2026 pela API e faixa de incerteza diária.
- 14/11/2026: Fases 1–3, prova, base de focos, publicação, revisões independentes (ver specs/tasks.md).
- 15/11/2026: cores azul→vermelho, textos simples, filtro de data no mapa, mapa único; regras "só main" e "sem Claude nos commits"; este arquivo criado.

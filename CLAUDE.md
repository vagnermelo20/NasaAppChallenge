# CLAUDE.md — arquivo central do projeto (ler no início de toda sessão)

Projeto: **NASA Space Apps 2026 — "MODIS and VIIRS Hot Spots Harmonization"**. App **EMBER**.
Link público: https://ember-fire-calendar.streamlit.app · Repo: github.com/vagnermelo20/NasaAppChallenge

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
00 entendimento · 01 download + grade · 02 identificação dos campos · 03 versão MODIS e pixel · 04 **harmonização** (→ `harmonized.parquet`, `grid_sat.parquet`, `fatores_k.parquet`, `static_mask.parquet`) · 05 validação deixando o ano de fora · 06 dados de 2026 · 07 prova "MODIS diz X, VIIRS diz Y" + robustez + faixa de incerteza · 08 base de focos por ano com `peso_harmonizado` (`data/processed/focos/`).

## Método atual de harmonização (v2) — NÃO é machine learning
1. Filtros: MODIS confiança ≥ 30; VIIRS n|h; máscara de fontes estáticas (células 0,02° com type 1/2/3 em ≥ 2 anos).
2. Contagem por célula 0,25° × mês × satélite.
3. Fator k = ΣVIIRS/ΣMODIS por satélite × bloco 5° × mês (2012–2021), refinado na região 2° com encolhimento bayesiano (λ = 100).
4. Terra e Aqua combinados pelo inverso da variância; só Terra até jun/2002. 2012+ usa VIIRS real.
Resultado (deixando o ano de fora): Brasil erro anual 1,6%; região 2° × mês 66% dentro de ±20% (mediana 13,5%); por ano 92%; dois VIIRS iguais 85%/mês. A2 (pico por célula ≥ 80%) não atingido: 73,7%.
Testado e rejeitado: k dia/noite, vizinhança 3×3, climatologia como prior, covariáveis do MODIS por região×mês (P90 FRP etc.).

## App (app/app.py, Streamlit)
Fire map (um mapa só: escolher data/intervalo, MODIS e VIIRS juntos; popup nos pontos; limite 50 mil pontos) · Calendar (área desenhada, resumo automático, botão sem/com harmonização, cores azul→vermelho em escala log) · Hotspot search (CSV) · Trends · Methodology. Testes: `.venv/Scripts/python -m unittest app.test_delivery`. Mantido acordado por `.github/workflows/manter-app-acordado.yml`.

## Pendências
- Harmonização v3 mais forte (ver plano abaixo) — pedido do usuário em 15/11/2026.
- Nomes da equipe, vídeo de 30 s, envio no portal (texto pronto em `docs/submissao_spaceapps.md`).

## Plano: harmonização v3 (proposta, ainda não implementada)
Ideia central: converter **cada foco MODIS** (não a soma do mês) pela física da detecção, para capturar a variação de ano a ano que o k médio não captura.
1. **Pareamento** (2012–2021): para cada foco VIIRS, dizer se um pixel MODIS do Aqua da mesma passagem o cobre (já medido no nb 03: curva de detecção 23% a 2–5 MW → 65% > 100 MW).
2. **Modelo de detecção** p(detectado pelo MODIS | FRP, área do pixel, dia/noite) — regressão logística/GAM.
3. **Distribuição de tamanho do fogo** por região × mês: o MODIS só vê a cauda forte; ajustar uma lei de potência truncada (ou lognormal) ao FRP dos focos MODIS e **extrapolar quantos fogos fracos ficaram invisíveis** (estimador de Horvitz–Thompson: cada foco MODIS vale 1/p(FRP) focos "reais", vezes quantos pixels VIIRS cabem nele).
4. Validar com a mesma regra (ano deixado de fora, região 2° × mês) contra o v2; só adotar se ganhar.

## Diário
- 14/11/2026: Fases 1–3, prova, base de focos, publicação, revisões independentes (ver specs/tasks.md).
- 15/11/2026: cores azul→vermelho, textos simples, filtro de data no mapa, mapa único; regras "só main" e "sem Claude nos commits"; este arquivo criado.

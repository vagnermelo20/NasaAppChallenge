# Front-end — guia passo a passo da Pessoa B
Ref.: `spec.md` (R7–R11, A3) · `plan.md` (contrato de dados) · `tasks.md` (B1–B8)

**Objetivo:** o site do projeto NASA Space Apps. O usuário escolhe uma região e um período e vê o **calendário de queimadas harmonizado** (ano × mês), compara o mês atual com o histórico e baixa os dados.

**Stack:** Streamlit (app inteiro em Python) + streamlit-folium (mapa) + Plotly (gráficos) + DuckDB (consulta ao Parquet).
**Idioma da interface:** **inglês** (os jurados do Space Apps são internacionais). Comentários no código podem ser em português.

---

## Regras de trabalho
- **Rode todos os comandos a partir da raiz do repositório** (a pasta que tem `README.md`). Todos os caminhos deste guia são relativos a ela.
- **Python do projeto:** Windows → `.venv\Scripts\python`; Linux/Mac → `.venv/bin/python`. Se o `.venv` não existir: `python -m venv .venv` e depois instale o `requirements.txt`.
- **Estrutura do app:** um único arquivo `app/app.py`. Funções de dados com `@st.cache_data`. Não crie outros pacotes sem necessidade.
- **Git:** antes de começar cada passo, `git pull`; ao terminar, commit com a mensagem `B<n>: <o que fez>` e `git push`.
- Você **não depende** da Pessoa A para começar: use o mock (B1) com o mesmo formato do arquivo real.
- Só mexa em `app/` e no `requirements.txt`. Os dados (`data/`) e os notebooks são da Pessoa A.
- Cada passo tem um **pronto quando** (critério de aceite). Marque `[x]` no `tasks.md` ao concluir.
- Faça commit a cada passo concluído.

## Contrato de dados (não mudar sem combinar com A)
`data/processed/harmonized.parquet`, uma linha por célula × mês:

| coluna | tipo | significado |
|---|---|---|
| `lat`, `lon` | float | canto sudoeste da célula de 0,25° (centro = +0,125) |
| `ano`, `mes` | int | ano e mês (UTC) |
| `focos_harmonizados` | float | focos na escala VIIRS (MODIS convertido antes de 2012) |
| `fonte` | str | `modis_convertido` ou `viirs` |
| `dado_incompleto` | bool | mês com dias sem observação ou mês corrente |

**Regra importante:** só existem linhas com focos > 0. **Célula × mês ausente = 0 focos.** Por isso o B4 completa as combinações faltantes com zero.

---

## B0 — Preparar o ambiente (15 min)
1. `git pull` e ative o `.venv` do projeto.
2. Acrescente a linha `folium` ao `requirements.txt` (os outros pacotes já estão lá) e rode `.venv\Scripts\python -m pip install -r requirements.txt`.
3. Crie a pasta `app/` com `app/app.py` contendo só `st.title("Harmonized Burning Activity Calendar")`.
4. Rode `.venv\Scripts\python -m streamlit run app/app.py`.

**Pronto quando:** a página abre no navegador com o título.

## B1 — Mock dos dados (5 min) — o script já existe
1. Rode `.venv\Scripts\python app/make_mock.py`. Ele lê `data/processed/grid_monthly.parquet` e grava `data/processed/harmonized_mock.parquet` (o mock **não vai para o git**, está no `.gitignore`).
2. No `app.py`, escolha o arquivo assim (usa o real quando existir):
```python
from pathlib import Path
REAL = Path('data/processed/harmonized.parquet')
MOCK = Path('data/processed/harmonized_mock.parquet')
DADOS = REAL if REAL.exists() else MOCK
```
3. Mostre no rodapé qual arquivo está em uso (`st.caption(f"Data: {DADOS.name}")`), para ninguém confundir mock com dado real.

**Pronto quando:** o script imprime `harmonized_mock.parquet: ... colunas ['lat', 'lon', 'ano', 'mes', 'focos_harmonizados', 'fonte', 'dado_incompleto']`.

## B2 — Layout da página (30 min)
- `st.set_page_config(layout="wide", page_title=...)`.
- **Barra lateral (filtros):** modo de região (`st.radio` com `Draw on map` / `Lat-Lon + radius`), intervalo de anos (`st.slider` de `min(ano)` a `max(ano)` lidos do arquivo de dados), botão `Update`.
- **Área principal com abas:** `Calendar` · `Trends` · `Methodology` · `About`.
- Cabeçalho curto explicando em 2 linhas o que é o app e que os dados são do NASA FIRMS (MODIS + VIIRS).

**Pronto quando:** as abas e a barra lateral aparecem (ainda vazias).

## B3 — Seleção da região no mapa · R7 (2 h)
1. Mapa folium centrado no Brasil (`[-14, -52]`, zoom 4) com o plugin `Draw` (só retângulo e polígono), via `st_folium`.
2. `saida = st_folium(mapa, height=450, use_container_width=True)`; a geometria desenhada vem em `saida["last_active_drawing"]["geometry"]` (GeoJSON). Converta com `shapely.geometry.shape(...)`. Se for `None`, não há desenho.
3. Modo alternativo: `st.number_input` para `lat` (−34 a 6), `lon` (−74 a −34) e `radius (km)` (5 a 500, padrão 50); gere o círculo com `Point(lon, lat).buffer(raio_km / 111)` (aproximação em graus; atenção à ordem **lon, lat**).
4. Guarde a região em `st.session_state['regiao']` para não perder ao trocar de aba.
5. Sem região escolhida: mostre o Brasil inteiro e uma mensagem "Draw an area to filter".

**Pronto quando:** desenhar um retângulo ou digitar lat/lon atualiza a região guardada.

## B4 — Consulta dos dados da região · R7, A3 (1,5 h)
Implemente exatamente estas duas funções:
```python
@st.cache_data
def celulas() -> pd.DataFrame:
    return duckdb.sql(f"SELECT DISTINCT lat, lon FROM '{DADOS.as_posix()}'").df()

@st.cache_data
def serie_regiao(poligono_wkt: str | None, ano_ini: int, ano_fim: int) -> pd.DataFrame:
    # 1) células cujo CENTRO está dentro do polígono (None = Brasil inteiro)
    c = celulas()
    if poligono_wkt:
        poly = shapely.from_wkt(poligono_wkt)
        c = c[shapely.contains_xy(poly, c.lon + 0.125, c.lat + 0.125)]
    # 2) soma por ano × mês com DuckDB (registre o DataFrame `c` com con.register('sel', c))
    #    SELECT ano, mes, sum(focos_harmonizados) focos, bool_or(dado_incompleto) incompleto
    #    FROM '<DADOS>' JOIN sel USING (lat, lon) WHERE ano BETWEEN ano_ini AND ano_fim GROUP BY ALL
    # 3) complete todas as combinações ano × mês (1–12) com focos = 0 e incompleto = False
    ...
```
Passe o polígono como **WKT (texto)** (`poly.wkt`) para o cache do Streamlit funcionar.
Saída esperada: colunas `ano, mes, focos, incompleto`, exatamente `(ano_fim − ano_ini + 1) × 12` linhas.
5. Meça o tempo (`time.perf_counter`) e mostre discretamente no rodapé.

**Pronto quando:** para o retângulo do Pantanal (lat −20 a −16, lon −58 a −55) a tabela sai em **< 3 s**, tem `(anos × 12)` linhas e o mês de setembro está entre os maiores valores.

## B5 — Calendário de queimadas · R8 (2 h) ← peça central
1. Pivot `ano` (linhas) × `mes` (colunas Jan…Dec) com `focos`.
2. `plotly.express.imshow` com `color_continuous_scale='viridis'` (acessível para daltônicos), `text_auto` com números arredondados, hover "Year, Month, Hotspots".
3. Meses `incompleto=True`: sobreponha um marcador (`*` ou contorno) e explique na legenda "incomplete data".
4. Linha visual separando 2011 | 2012 com legenda "before 2012: MODIS converted to VIIRS scale".
5. Abaixo do calendário, dois destaques automáticos: **mês do ano com mais fogo** (mediana) e **ano com mais fogo**.

**Pronto quando:** o calendário aparece para a região escolhida e os destaques batem com a tabela.

## B6 — Mês atual × histórico · R9 (1,5 h)
1. "Mês atual" = último mês com dado na tabela.
2. Calcule, para o mesmo mês nos anos anteriores: mediana, percentis 25, 75 e 90.
3. Cartão com `st.metric`: valor atual, diferença em % da mediana e um rótulo:
   - `> p90` → **Critical** · `p75–p90` → **Above normal** · `p25–p75` → **Normal** · `< p25` → **Below normal**.
4. Gráfico de barras: valor de cada ano naquele mês, com a mediana como linha tracejada e o ano atual destacado.
5. **Modo anomalia** no calendário (toggle): `(focos − mediana do mês) / mediana`, em %, com rampa divergente acessível (`PuOr`, centrada em 0).

**Pronto quando:** o cartão mostra rótulo e % coerentes com o gráfico de barras.

## B7 — Aba Trends (1 h)
- Linha da **série anual** (soma por ano), com a faixa 2001–2011 em outra cor ("MODIS converted").
- Barras de **sazonalidade** (mediana por mês).

**Pronto quando:** os dois gráficos aparecem e mudam com a região.

## B8 — Downloads · R10 (1 h)
1. `st.download_button` com o CSV da região: `year, month, hotspots, anomaly_pct, incomplete, source`.
2. Nome do arquivo com a data e a região (ex.: `hotspots_calendar_2001-2025_bbox.csv`).
3. PNG do calendário: use o botão de câmera nativo do Plotly (aparece ao passar o mouse) e diga isso no texto de ajuda.

**Pronto quando:** o CSV baixado abre no Excel com as colunas certas.

## B9 — Aba Methodology · R11 (1 h)
1. Se `docs/metodologia.md` existir (escrito pela Pessoa A em A10), mostre com `st.markdown`; senão, mostre um texto provisório.
2. Mostre as figuras de `reports/` com `st.image` **só se o arquivo existir** (`Path(...).exists()`), e as métricas de `reports/metrics.json` com `st.json` se ele existir.
3. Enquanto A não entrega: deixe um texto provisório e as figuras que já existem (`v2_serie_anual.png`, `v6_mapa_k.png`, `b4_curva_deteccao.png`).

**Pronto quando:** a aba mostra texto, figuras e métricas sem erro mesmo se `metrics.json` ainda não existir.

## B10 — Acabamento e acessibilidade (1 h)
- Todas as cores de `viridis`/`PuOr`; nada que dependa só de vermelho × verde.
- Textos de ajuda (`help=`) nos filtros; unidades sempre visíveis ("hotspots / month").
- Aviso fixo: **"Hotspots are satellite detections, not number of fires or burned area."**
- Testar no celular (largura estreita) e com região vazia (sem focos).

**Pronto quando:** checklist acima verificado com 3 regiões.

## B11 — Trocar o mock pelo dado real
Quando a Pessoa A avisar que passou o **Checkpoint 2**: troque `DADOS` para `data/processed/harmonized.parquet`, rode o app e confira 3 regiões (Pantanal, Matopiba, Acre).

**Pronto quando:** o app funciona com o arquivo real e o salto de 2012 não aparece no calendário.

---

## Ordem sugerida e tempo total (~13 h)
B0 → B1 → B2 → B3 → B4 → **B5** → B8 → B6 → B7 → B9 → B10 → B11
(B5 e B8 primeiro: são o mínimo que o desafio pede — calendário + CSV.)

## Se o tempo apertar (corte nesta ordem)
B7 → modo anomalia do B6 (mantém o cartão) → polígono no B3 (fica retângulo + lat/lon) → B9 vira imagens estáticas.
**Nunca corte:** B3 (pelo menos lat/lon), B4, B5, B8.

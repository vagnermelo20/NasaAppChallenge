# AGENTS.md — instruções para agentes de código (Codex, Claude, etc.)

Projeto NASA Space Apps 2026 — *MODIS and VIIRS Hot Spots Harmonization*.
Spec-Driven Development: **leia `specs/spec.md`, `specs/plan.md` e `specs/tasks.md` antes de qualquer mudança.**

## Onde está cada coisa
- `specs/tasks.md` — lista de tarefas, dividida entre Pessoa A (dados), Pessoa B (front-end) e Juntos.
- `specs/frontend_pessoa_B.md` — passo a passo do front-end (B0–B11), com critério de "pronto" em cada passo.
- `notebooks/` — análise e pipeline de dados (Pessoa A). Já executados; não apague.
- `app/` — site em Streamlit (Pessoa B). `app/make_mock.py` gera dados de teste.
- `data/processed/` — `grid_monthly.parquet` (versionado); `harmonized.parquet` (real, Pessoa A); `harmonized_mock.parquet` (local, não versionado).
- `data/raw/` — dados brutos do FIRMS, fora do git (gerados por `notebooks/01_dados.ipynb`).

## Regras
1. Rode tudo a partir da raiz do repositório, com o Python do `.venv` (`.venv\Scripts\python` no Windows, `.venv/bin/python` no Linux/Mac).
2. Faça **só a tarefa pedida** (ex.: "faça o B3"). Ao concluir, verifique o critério "Pronto quando" e marque `[x]` no `specs/tasks.md`.
3. **Não mude o contrato de dados** (`plan.md`, seção "Contrato entre as duas frentes") sem pedir.
4. **Não apague** notebooks, figuras de `reports/`, specs ou a skill em `.claude/skills/` — são reaproveitados na apresentação.
5. Não versione dados brutos, `.venv`, segredos (`.env`, MAP_KEY) nem o mock.
6. Interface do site em **inglês**; cores acessíveis (`viridis`, `PuOr`); sempre avisar que foco detectado ≠ incêndio ≠ área queimada.
7. Commits: mensagem `<ID da tarefa>: <o que fez>` (ex.: `B4: consulta da região em DuckDB`). `git pull` antes de começar.

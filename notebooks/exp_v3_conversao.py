"""Experimento v3: conversão não proporcional (lei de potência) e quantile mapping contra o fator k (v2).
Mesma régua: ano deixado de fora 2012–2021, região 2° × mês, VIIRS >= 100, % dentro de ±20%.
Rodar da raiz: .venv/Scripts/python notebooks/exp_v3_conversao.py
"""
import sys
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
g = pd.read_parquet('data/processed/grid_sat.parquet')
g = g[g.ano.between(2012, 2021)]
g['qy'], g['qx'] = (g.lat // 2).astype(int), (g.lon // 2).astype(int)
g['by'], g['bx'] = (g.lat // 5).astype(int), (g.lon // 5).astype(int)
r = g.pivot_table(index=['qy', 'qx', 'ano', 'mes'], columns='satellite', values='n', aggfunc='sum', fill_value=0).reset_index()
blocos = g.groupby(['qy', 'qx'])[['by', 'bx']].agg(lambda s: s.mode()[0]).reset_index()
r = r.merge(blocos, on=['qy', 'qx'])
r['M'] = r.Terra + r.Aqua; r['V'] = r['S-NPP']
r['est'] = (r.mes - 1) // 3                     # estação (trimestre) para o QM

def prever(tr, te):
    out = te[['qy', 'qx', 'ano', 'mes', 'V', 'M']].copy()
    # v2 simplificado: k = ΣV/ΣM por bloco × mês (fallback nacional do mês)
    kb = tr.groupby(['by', 'bx', 'mes']).apply(lambda d: d.V.sum() / max(d.M.sum(), 1), include_groups=False).rename('k')
    kn = tr.groupby('mes').apply(lambda d: d.V.sum() / d.M.sum(), include_groups=False)
    k = te.join(kb, on=['by', 'bx', 'mes']).k.fillna(te.mes.map(kn))
    out['v2'] = te.M * k
    # (A) lei de potência: log V = a + β log M, por bloco × mês, ponderada por M; encolhe β para o nacional
    nac = np.polyfit(np.log1p(tr.M[tr.M > 0]), np.log1p(tr.V[tr.M > 0]), 1, w=np.sqrt(tr.M[tr.M > 0]))
    pars = {}
    for key, d in tr[tr.M > 0].groupby(['by', 'bx', 'mes']):
        if len(d) >= 8 and d.M.nunique() > 3:
            b, a = np.polyfit(np.log1p(d.M), np.log1p(d.V), 1, w=np.sqrt(d.M))
            w = len(d) / (len(d) + 20)                 # encolhimento para o nacional
            pars[key] = (w * b + (1 - w) * nac[0], w * a + (1 - w) * nac[1])
    ab = np.array([pars.get((by, bx, m), tuple(nac)) for by, bx, m in zip(te.by, te.bx, te.mes)])
    out['pot'] = np.expm1(ab[:, 1] + ab[:, 0] * np.log1p(te.M))
    # (B) quantile mapping por bloco × estação, em log1p
    qm = np.empty(len(te))
    for i, (by, bx, s, m) in enumerate(zip(te.by, te.bx, te.est, te.M)):
        d = tr[(tr.by == by) & (tr.bx == bx) & (tr.est == s)]
        if len(d) < 20: d = tr[tr.est == s]
        p = (d.M <= m).mean()
        qm[i] = np.quantile(d.V, min(max(p, 0.0), 1.0))
    out['qm'] = qm
    return out

res = pd.concat([prever(r[r.ano != y], r[r.ano == y]) for y in range(2012, 2022)])
ev = res[res.V >= 100]
print(f'região 2° × mês, VIIRS >= 100, n = {len(ev):,}')
for col, nome in [('v2', 'v2 (fator k bloco×mês)'), ('pot', 'A: lei de potência V=c·M^β'), ('qm', 'B: quantile mapping')]:
    d = (ev[col] / ev.V - 1).abs()
    an = res.groupby('ano')[[col, 'V']].sum(); ea = (an[col] / an.V - 1).abs().mean()
    print(f'{nome:30s} ±20% {np.mean(d <= .2):6.1%} | mediana {d.median():6.1%} | erro anual Brasil {ea:5.1%}')
print('β nacional (1 = proporcional):', round(np.polyfit(np.log1p(r.M[r.M > 0]), np.log1p(r.V[r.M > 0]), 1, w=np.sqrt(r.M[r.M > 0]))[0], 3))

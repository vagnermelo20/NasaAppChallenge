# Uso (da raiz do repo): .venv/Scripts/python notebooks/exp_debate_covariaveis.py <pasta>/feats_2deg.parquet ; depois .venv/Scripts/python notebooks/exp_debate_metodos.py <pasta>
"""Teste das ideias escolhidas no debate. Métrica fixada antes: região 2°×mês, VIIRS>=100, LOYO 2012–2021, % dentro de ±20%.
Teste final: 2022–2025 com tudo calibrado em 2012–2021."""
import sys, numpy as np, pandas as pd
sys.stdout.reconfigure(encoding='utf-8'); rng = np.random.default_rng(0)
D = sys.argv[1]
g = pd.read_parquet('data/processed/grid_sat.parquet')
g = g[g.ano.between(2012, 2025)].groupby(['lat', 'lon', 'ano', 'mes', 'satellite'], as_index=False).n.sum()
cells = g[['lat', 'lon']].drop_duplicates().reset_index(drop=True); cells['c'] = cells.index
g = g.merge(cells, on=['lat', 'lon']); NC, NY, NCAL = len(cells), 14, 10
arr = {s: np.zeros((NC, NY, 12)) for s in ['Terra', 'Aqua', 'S-NPP']}
for s, d in g.groupby('satellite'):
    np.add.at(arr[s], (d.c.values, d.ano.values - 2012, d.mes.values - 1), d.n.values)
T, A, V = arr['Terra'], arr['Aqua'], arr['S-NPP']
def fac(lado): return pd.factorize((cells.lat // lado).astype(int).astype(str) + '_' + (cells.lon // lado).astype(int).astype(str))[0]
blk, q2 = fac(5), fac(2)
def gs(x, idx): out = np.zeros((idx.max() + 1,) + x.shape[1:]); np.add.at(out, idx, x); return out
bT, bA, bV, gV = gs(T, blk), gs(A, blk), gs(V, blk), gs(V, q2)
def k(bm, sat, anos, LAM=100):
    num, den = bV[:, anos].sum(1), bm[:, anos].sum(1)
    nac = V[:, anos].sum((0, 1)) / sat[:, anos].sum((0, 1))
    k5 = np.where(den >= 30, num / np.where(den > 0, den, 1), nac[None, :])[blk]
    return (gV[:, anos].sum(1)[q2] + LAM * k5) / (gs(sat, q2)[:, anos].sum(1)[q2] + LAM)
def est_ano(y, anos):
    kT, kA = k(bT, T, anos), k(bA, A, anos)
    return (T[:, y] + A[:, y]) / (1 / kT + 1 / kA)
P = np.zeros_like(V)
for y in range(NY):
    anos = [a for a in range(NCAL) if a != y]          # LOYO dentro de 2012–2021; 2022+ usa os 10 anos
    P[:, y] = est_ano(y, anos)
# agrega para regiões 2°
qy, qx = (cells.lat // 2).astype(int).values, (cells.lon // 2).astype(int).values
reg = pd.factorize(pd.Series(qy).astype(str) + '_' + pd.Series(qx).astype(str))[0]
R = lambda x: gs(x, reg)
RP, RV, RT, RA = R(P), R(V), R(T), R(A)
ry = pd.DataFrame({'r': range(reg.max() + 1)}).merge(pd.DataFrame({'r': reg, 'qy': qy, 'qx': qx}).drop_duplicates('r'))
rows = []
for y in range(NY):
    for m in range(12):
        rows.append(pd.DataFrame({'r': ry.r, 'qy': ry.qy, 'qx': ry.qx, 'ano': 2012 + y, 'mes': m + 1,
                                  'est': RP[:, y, m], 'v': RV[:, y, m], 't': RT[:, y, m], 'a': RA[:, y, m]}))
df = pd.concat(rows, ignore_index=True)
F = pd.read_parquet(f'{D}/feats_2deg.parquet')
df = df.merge(F, on=['qy', 'qx', 'ano', 'mes'], how='left')
df['n_modis'] = df.n_modis.fillna(0)
df['x_frp'] = df.logfrp_p90; df['x_aglo'] = np.log(df.focos_por_celula); df['x_noite'] = df.f_noite
df['lta'] = np.log((df.t + 1) / (df.a + 1))
df['y'] = np.log((df.v + .5) / (df.est + .5))
X = ['x_frp', 'x_aglo', 'x_tA', 'x_noite']

def ajusta_prediz(tr, te, embaralha=False):
    tr, te = tr.copy(), te.copy()
    clim = tr.groupby(['r', 'mes']).lta.mean().rename('lta_c')            # anomalia Terra/Aqua vs climatologia do treino
    for d in (tr, te):
        d['x_tA'] = (d.lta - d.join(clim, on=['r', 'mes']).lta_c).fillna(0)
    tr = tr[(tr.n_modis >= 5) & tr[X].notna().all(1)]
    mu, sd = tr[X].mean(), tr[X].std()
    Z = ((tr[X] - mu) / sd).values
    if embaralha: Z = Z[rng.permutation(len(Z))]
    w = np.sqrt(np.minimum(tr.n_modis.values, 500))
    Zb = np.c_[np.ones(len(Z)), Z] * w[:, None]; yb = tr.y.values * w
    beta = np.linalg.solve(Zb.T @ Zb + np.diag([0] + [1.0] * len(X)), Zb.T @ yb)
    Zt = ((te[X] - mu) / sd).fillna(0).values
    if embaralha: Zt = Zt[rng.permutation(len(Zt))]
    adj = np.where(te.n_modis >= 5, np.c_[np.ones(len(Zt)), Zt] @ beta, 0)
    return te.est * np.exp(adj), beta

def metrica(v, p):
    d = np.abs(p / v - 1); return np.mean(d <= .2), np.median(d), np.mean(d <= .3)
cal = df[df.ano <= 2021]; res = {}; betas = []
for nome, emb in [("regressão", False), ("controle embaralhado", True)]:
    pred = []
    for y in range(2012, 2022):
        p, b = ajusta_prediz(cal[cal.ano != y], cal[cal.ano == y], emb); pred.append(p)
        if not emb: betas.append(b)
    res[nome] = pd.concat(pred)
ev = cal.v >= 100
print('=== LOYO 2012–2021, região 2° × mês, VIIRS ≥ 100 (n =', ev.sum(), ')')
for nome, p in [('método atual', cal.est), ('+ regressão covariáveis', res['regressão']), ('+ controle embaralhado', res['controle embaralhado'])]:
    a, med, a30 = metrica(cal.v[ev], p[ev]); print(f'{nome:26s} ±20% {a:6.1%} | mediana {med:5.1%} | ±30% {a30:6.1%}')
B = np.array(betas); print('coeficientes (intercepto,', ', '.join(X), ') média:', B.mean(0).round(3), '| mesmo sinal nas 10 dobras:', (np.sign(B) == np.sign(B.mean(0))).all(0))
anos_melhora = sum(metrica(cal.v[ev & (cal.ano == y)], res['regressão'][ev & (cal.ano == y)])[0] > metrica(cal.v[ev & (cal.ano == y)], cal.est[ev & (cal.ano == y)])[0] for y in range(2012, 2022))
print('anos em que a regressão melhora ±20%:', anos_melhora, 'de 10')

# --- teto binomial: k perfeito, só ruído de amostragem com a contagem real
c2 = cal[ev & (cal.n_modis > 0)]
p_det = np.clip((c2.t + c2.a) / c2.v, 1e-3, 1)
sim = [np.mean(np.abs(rng.binomial(c2.v.astype(int), p_det) / (c2.v * p_det) - 1) <= .2) for _ in range(20)]
print(f'\n=== Teto binomial simulado (k perfeito, contagens reais): ±20% {np.mean(sim):.1%}')
for lim in [100, 300, 1000]:
    s = cal.v >= lim; a, med, _ = metrica(cal.v[s], cal.est[s]); a2, _, _ = metrica(cal.v[s], res['regressão'][s])
    print(f'  meses com VIIRS ≥ {lim:4d}: atual ±20% {a:.1%} | com regressão {a2:.1%} | n={s.sum()}')

# --- faixa de incerteza calibrada (quantis dos resíduos LOYO dos OUTROS anos, por faixa de n_modis)
melhor = res['regressão'] if metrica(cal.v[ev], res['regressão'][ev])[0] > metrica(cal.v[ev], cal.est[ev])[0] else cal.est
r = np.log((cal.v + .5) / (melhor + .5)); faixa = pd.cut(cal.n_modis, [-1, 20, 50, 150, 500, 1e9])
cob90 = cob80 = 0; larg = []; tot = 0
for y in range(2012, 2022):
    tr, te = (cal.ano != y) & ev, (cal.ano == y) & ev
    for f in faixa.cat.categories:
        rt = r[tr & (faixa == f)]; m = te & (faixa == f)
        if m.sum() == 0 or len(rt) < 30: continue
        lo9, hi9, lo8, hi8 = rt.quantile([.05, .95, .10, .90])
        cob90 += ((r[m] >= lo9) & (r[m] <= hi9)).sum(); cob80 += ((r[m] >= lo8) & (r[m] <= hi8)).sum(); tot += m.sum()
        larg += [np.expm1((hi9 - lo9) / 2)] * int(m.sum())
print(f'\n=== Faixa calibrada (LOYO): cobertura 90% nominal = {cob90/tot:.1%} | 80% nominal = {cob80/tot:.1%} | meia-largura mediana da faixa de 90% ≈ ±{np.median(larg):.0%}')

# --- teste final 2022–2025 (calibrado só em 2012–2021)
fut = df[df.ano >= 2022]; pf, _ = ajusta_prediz(cal, fut); evf = fut.v >= 100
a, med, _ = metrica(fut.v[evf], fut.est[evf]); a2, med2, _ = metrica(fut.v[evf], pf[evf])
print(f'\n=== Teste final 2022–2025: atual ±20% {a:.1%} (mediana {med:.1%}) | com regressão ±20% {a2:.1%} (mediana {med2:.1%})')

# --- escala anual e trimestral (mesma previsão LOYO, só agregando no tempo)
for nome, chave in [('trimestre', (cal.mes - 1) // 3), ('ano', 0)]:
    a = cal.assign(per=chave).groupby(['r', 'ano', 'per'])[['v', 'est']].sum(); a = a[a.v >= 300]
    d = np.abs(a.est / a.v - 1)
    print(f'{nome:9s} região 2°: ±20% {np.mean(d <= .2):.1%} | ±10% {np.mean(d <= .1):.1%} | mediana {np.median(d):.1%} | n={len(a)}')

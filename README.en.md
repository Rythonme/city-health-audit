# CHIA — City Health Index Audit

> An open-source **measurement audit** of in-use city health indices — not another city ranking.
> This is a condensed English summary. **The Chinese README is the authoritative version.**

[![status: early public release](https://img.shields.io/badge/status-early--public--release-blue)](#)
[![data: real open data](https://img.shields.io/badge/data-real--open--data-teal)](#)

## What this is

Policy makers already rely heavily on city health indices (e.g., Tsinghua Urban Health Index covering ~296 Chinese cities; the 2018 National Healthy City evaluation system). These indices mix **health outcomes** with **determinants** into one weighted score, then use "the index went up" to argue health improved — a circular structure no one has externally audited.

CHIA does not build a new index. It asks three questions about this class of indices:

1. **Is the score verifiable at all?** Cross-source consistency (yearbook PM2.5 × WHO, 263 matched cities, r=0.976, MAPE 2.4%), coverage, data lineage, known-groups validity (East/Central/West: g=0.64, p<0.0001).
2. **Are the published grades stable?** Under fully random Dirichlet weights (5,000 draws — a "total ignorance" reference frame), only **12% of city-years keep their quintile grade with ≥0.8 probability**; middle grades (B/C/D) are stable only 24–31% of the time. Even under *plausible* ±20% perturbation around baseline weights, ~41.5% of city-years are unstable.
3. **Which construction choice matters most?** First-order variance decomposition: normalization choice > between-dimension weights > within-dimension weights (confirming Saisana et al. 2005).

## Audit object & boundary

The current audit targets a **transparent reference implementation of the published frameworks** (TUHI / 2018 national system) built from real open data — plus a WHO cross-source check. We have **not yet** audited TUHI's published scores directly; that is the top roadmap item. Until then, robustness conclusions apply to this class of index construction, not to any specific published number.

## Data

- **China City Statistical Yearbook** prefecture panel, 302 cities × 2003–2024 (public compiled .dta 2003–2018 + extraction from 2020–2025 volume Excel tables for 2019–2024; overlapping years match byte-for-byte), 21 reproducible indicators.
- **WHO Ambient Air Quality Database V6.1** as an independent source for PM2.5 cross-validation.
- No simulated data anywhere. Outcome anchors (mortality/morbidity) are **not available** at prefecture level in open data — this gap is reported honestly, never imputed.

## Reproduce

```bash
git clone <THIS_REPO_URL> && cd city-health-audit
python scripts/fetch_data.py     # verify SHA256 of raw inputs
python scripts/build_data.py     # rebuild panel, index, audits, site data
python -m http.server 8000 --directory docs   # open http://localhost:8000
node tests/app_smoke.mjs         # website smoke test
```

## Positioning

| TUHI-style product | CHIA |
|---|---|
| Exact ranks and scores | Grades only, never ranked within a grade, with grade-stability probabilities |
| Answers "who is healthier" | Answers "can this score be trusted" |
| One deterministic number | Uncertainty, scenario switching ("change the weighting, watch grades flip"), transition matrix |
| Raw data not public | Raw inputs shipped in-repo with SHA256 verification |

## License

Code MIT; docs & indicator dictionary CC BY 4.0; derived data ODbL 1.0. Redistribution of raw data follows the original publishers' terms (see `data/raw/SOURCE.md`).

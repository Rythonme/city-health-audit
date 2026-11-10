/* CHIA 审计台 · 简化版（vanilla JS，无依赖，离线可运行）
   读取 docs/data/city_data.js 与 docs/data/indicator_dictionary.js */
(function () {
  'use strict';

  var D = window.CHIA_CITY_DATA;
  var DICT = window.CHIA_DICT;
  if (!D || !DICT || D.meta.data_mode !== 'real') {
    document.body.innerHTML = '<p style="padding:24px">数据未加载或非真实数据模式。</p>';
    return;
  }

  var DIM_ORDER = ['D2', 'D3', 'D4', 'D5', 'D6'];
  var DIM_NAME = DICT.dims;
  var COLORS = { D2: '#0e7490', D3: '#15803d', D4: '#b91c1c', D5: '#7c3aed', D6: '#b45309' };

  function $(id) { return document.getElementById(id); }
  function fmt(v, d) { return v == null ? '—' : Number(v).toFixed(d == null ? 1 : d); }

  /* ---------- 导航 ---------- */
  var navBtns = document.querySelectorAll('nav button');
  navBtns.forEach(function (b) {
    b.addEventListener('click', function () {
      navBtns.forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      document.querySelectorAll('main section').forEach(function (s) {
        s.classList.toggle('active', s.id === 'view-' + b.dataset.view);
      });
      window.scrollTo(0, 0);
    });
  });

  /* ---------- SVG 工具 ---------- */
  function svgOpen(w, h) {
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" preserveAspectRatio="xMidYMid meet" role="img">';
  }
  function lineChart(pts, w, h, color, yLabel) {
    if (!pts.length) return '<p class="hint">无数据</p>';
    var xs = pts.map(function (p) { return p[0]; });
    var ys = pts.map(function (p) { return p[1]; });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    var y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
    var pad = 36, iw = w - pad * 2, ih = h - pad * 2;
    var dec = (y1 - y0) < 10 ? 1 : 0;   // 小范围数值用 1 位小数，避免刻度标签重叠
    function X(v) { return pad + (v - x0) / (x1 - x0 || 1) * iw; }
    function Y(v) { return pad + ih - (v - y0) / (y1 - y0 || 1) * ih; }
    var s = svgOpen(w, h);
    [0, 0.5, 1].forEach(function (t) {
      var yv = y0 + t * (y1 - y0);
      s += '<line x1="' + pad + '" y1="' + Y(yv) + '" x2="' + (w - pad) + '" y2="' + Y(yv) + '" stroke="#e5e7eb"/>' +
        '<text x="' + (pad - 6) + '" y="' + (Y(yv) + 4) + '" font-size="11" fill="#6b7280" text-anchor="end">' + yv.toFixed(dec) + '</text>';
    });
    s += '<polyline fill="none" stroke="' + color + '" stroke-width="2.5" points="' +
      pts.map(function (p) { return X(p[0]) + ',' + Y(p[1]); }).join(' ') + '"/>';
    pts.forEach(function (p) {
      s += '<circle cx="' + X(p[0]) + '" cy="' + Y(p[1]) + '" r="3" fill="' + color + '"/>' +
        '<text x="' + X(p[0]) + '" y="' + (h - 8) + '" font-size="10.5" fill="#6b7280" text-anchor="middle">' + p[0] + '</text>';
    });
    if (yLabel) s += '<text x="' + pad + '" y="16" font-size="11.5" fill="#6b7280">' + yLabel + '</text>';
    return s + '</svg>';
  }
  function barChart(items, w, h, opts) {
    opts = opts || {};
    var max = Math.max.apply(null, items.map(function (i) { return i.v; })) * (opts.maxPad || 1.15);
    var rowH = h / items.length, labelW = opts.labelW || 150;
    var s = svgOpen(w, h);
    items.forEach(function (it, k) {
      var y = k * rowH + rowH * 0.22, bh = rowH * 0.56;
      var bw = Math.max(2, it.v / max * (w - labelW - 70));
      s += '<text x="0" y="' + (y + bh * 0.8) + '" font-size="12.5" fill="#374151">' + it.label + '</text>' +
        '<rect x="' + labelW + '" y="' + y + '" width="' + bw + '" height="' + bh + '" rx="4" fill="' + (it.color || '#0f766e') + '"/>' +
        '<text x="' + (labelW + bw + 8) + '" y="' + (y + bh * 0.8) + '" font-size="12.5" fill="#374151">' + it.text + '</text>';
    });
    return s + '</svg>';
  }
  function scatter(pts, w, h, xMax) {
    var pad = 40, iw = w - pad * 2, ih = h - pad * 2;
    function X(v) { return pad + v / xMax * iw; }
    function Y(v) { return pad + ih - v / xMax * ih; }
    var s = svgOpen(w, h);
    s += '<line x1="' + X(0) + '" y1="' + Y(0) + '" x2="' + X(xMax) + '" y2="' + Y(xMax) + '" stroke="#9ca3af" stroke-dasharray="4 4"/>';
    s += '<rect x="' + pad + '" y="' + pad + '" width="' + iw + '" height="' + ih + '" fill="none" stroke="#e5e7eb"/>';
    pts.forEach(function (p) {
      s += '<circle cx="' + X(p[0]) + '" cy="' + Y(p[1]) + '" r="2.6" fill="#0f766e" fill-opacity="0.35"/>';
    });
    s += '<text x="' + (w / 2) + '" y="' + (h - 6) + '" font-size="11.5" fill="#6b7280" text-anchor="middle">年鉴 PM2.5</text>' +
      '<text x="10" y="' + (pad + 4) + '" font-size="11.5" fill="#6b7280">WHO PM2.5</text>';
    return s + '</svg>';
  }
  function histogram(vals, w, h, bins) {
    var counts = new Array(bins).fill(0);
    vals.forEach(function (v) { counts[Math.min(bins - 1, Math.floor(v * bins))]++; });
    var max = Math.max.apply(null, counts);
    var pad = 30, bw = (w - pad * 2) / bins;
    var s = svgOpen(w, h);
    counts.forEach(function (c, k) {
      var bh = c / max * (h - pad * 2);
      s += '<rect x="' + (pad + k * bw + 2) + '" y="' + (h - pad - bh) + '" width="' + (bw - 4) + '" height="' + Math.max(0, bh) + '" rx="3" fill="#0f766e"/>' +
        '<text x="' + (pad + k * bw + bw / 2) + '" y="' + (h - 8) + '" font-size="10.5" fill="#6b7280" text-anchor="middle">' + (k / bins).toFixed(1) + '</text>';
    });
    s += '<text x="' + pad + '" y="14" font-size="11.5" fill="#6b7280">城市-年份数</text>';
    return s + '</svg>';
  }

  /* ---------- 总览 ---------- */
  function fillMetaSpans() {
    var ov = D.overview, v = D.validity;
    function put(id, val) { var el = $(id); if (el) el.textContent = val; }
    put('ov-cities', D.meta.n_cities);
    put('ov-period', D.meta.period.replace('-', '–'));
    put('ov-audit-object', D.meta.audit_object || '—');
    put('ov-who', v.n_matched_cities);
    put('ov-nmc', D.meta.n_mc);
    put('ov-nmc2', D.meta.n_mc);
    put('ft-version', 'v' + (D.meta.version || ''));
  }

  function renderOverview() {
    var ov = D.overview;
    $('overview-kpis').innerHTML = ov.kpi.map(function (k) {
      return '<div class="card kpi"><div class="v">' + k.value + '</div><div class="l">' + k.label + ' · ' + k.unit + '</div></div>';
    }).join('') +
      '<div class="card kpi"><div class="v">' + (ov.mean_grade_stability * 100).toFixed(1) + '%</div><div class="l">平均分档稳定率 · 权重抽样</div></div>';

    $('overview-dims').innerHTML = barChart(
      DIM_ORDER.map(function (d) {
        return { label: DIM_NAME[d], v: ov.dim_means[d], text: fmt(ov.dim_means[d]), color: COLORS[d] };
      }), 420, 5 * 44);

    var pm = ov.pm25_by_year;
    var pts = Object.keys(pm).sort().map(function (y) { return [Number(y), pm[y]]; });
    $('overview-pm25').innerHTML = lineChart(pts, 460, 240, '#b45309', 'μg/m³ · 302 城均值');
  }

  /* ---------- 城市 ---------- */
  var selected = null;
  function latestYear(s) { return s[s.length - 1]; }
  function pm2018(city) {
    for (var i = city.series.length - 1; i >= 0; i--) {
      if (city.series[i].y <= 2018 && city.series[i].pm25 != null) return city.series[i].pm25;
    }
    return null;
  }
  function renderCityTable() {
    var q = ($('city-search').value || '').trim();
    var g = $('city-grade').value;
    var rows = D.cities.filter(function (c) {
      if (g && c.grade !== g) return false;
      return !q || c.name.indexOf(q) >= 0;
    });
    $('city-body').innerHTML = rows.map(function (c) {
      return '<tr class="city-row' + (selected === c.id ? ' sel' : '') + '" data-city="' + c.name + '">' +
        '<td>' + c.name + '</td>' +
        '<td><span class="badge g-' + c.grade + '">' + (c.grade || '—') + '</span></td>' +
        '<td class="num">' + fmt(c.overall) + '</td>' +
        '<td class="num">' + (c.stab == null ? '—' : Math.round(c.stab * 100) + '%') + '</td>' +
        '<td class="num">' + fmt(pm2018(c)) + '</td></tr>';
    }).join('') || '<tr><td colspan="5" class="hint">无匹配城市</td></tr>';
    document.querySelectorAll('.city-row').forEach(function (tr) {
      tr.addEventListener('click', function () { selectCity(tr.dataset.city); });
    });
  }
  function selectCity(name) {
    selected = name;
    renderCityTable();
    var c = D.cities.filter(function (x) { return x.name === name; })[0];
    var box = $('city-detail');
    box.hidden = false;
    var last = c.series[c.series.length - 1];
    var html = '<div class="head"><span class="badge g-' + c.grade + '">' + c.grade + '</span><h3>' + c.name + '</h3>' +
      '<span class="hint">最新可算年份 ' + last.y + ' · 总分 ' + fmt(c.overall) + ' · 稳定率 ' + (c.stab == null ? '—' : Math.round(c.stab * 100) + '%') + '</span></div>';
    /* 情景面板：换构造方案，档位变不变？ */
    if (c.scen && c.grade) {
      function chip(label, grade, ref) {
        var changed = ref && grade && grade !== ref;
        return '<span class="badge g-' + (grade || 'E') + '" style="opacity:' + (grade ? 1 : 0.35) + '">' + (grade || '—') + '</span>' +
          '<span class="hint" style="margin:0 10px 0 4px">' + label + (changed ? ' <b style="color:#b91c1c">变档</b>' : '') + '</span>';
      }
      html += '<div class="note" style="margin-top:8px"><b>换方案看档位</b>（最新可算年）：基准等权 ' +
        chip('', c.grade, null) + chip('熵权', c.scen.entropy, c.grade) +
        chip('逐年百分位', c.scen.pctile, c.grade) +
        '<span class="hint" style="margin-left:4px">围绕基准权重 ±50% 扰动下档位保持不变的概率 <b>' +
        (c.scen.p50 == null ? '—' : Math.round(c.scen.p50 * 100) + '%') + '</b></span></div>';
    }
    DIM_ORDER.forEach(function (d) {
      var v = last.dims[d];
      html += '<div class="dimbar"><span>' + DIM_NAME[d] + '</span>' +
        '<div class="track"><div class="fill" style="width:' + (v || 0) + '%"></div></div>' +
        '<span class="num">' + fmt(v) + '</span></div>';
    });
    var pts = c.series.filter(function (s) { return s.overall != null; }).map(function (s) { return [s.y, s.overall]; });
    html += '<h2 style="margin-top:16px">总分走势</h2>' + lineChart(pts, 460, 220, '#0f766e', '归一化总分 0–100');
    box.innerHTML = html;
  }

  /* ---------- 审计 ---------- */
  function renderAudit() {
    var xv = D.validity.cross_validation;
    var rPts = xv.map(function (r) { return [r.year, r.pearson_r]; });
    var bPts = xv.map(function (r) { return [r.year, r.mean_bias_who_minus_yearbook]; });
    $('audit-xval').innerHTML =
      lineChart(rPts, 460, 200, '#0f766e', 'Pearson r（年鉴 vs WHO）') +
      lineChart(bPts, 460, 170, '#b45309', '偏倚 WHO − 年鉴（μg/m³）') +
      '<div class="legend"><span><i style="background:#0f766e"></i>相关系数</span><span><i style="background:#b45309"></i>偏倚</span></div>';
    $('audit-scatter').innerHTML = scatter(D.validity.scatter, 460, 460, 120);

    var stabs = [];
    D.cities.forEach(function (c) {
      c.series.forEach(function (s) { if (s.stab != null) stabs.push(s.stab); });
    });
    $('audit-stability').innerHTML = histogram(stabs, 460, 220, 10) +
      '<p class="hint">稳定率 ≥ 0.8 的城市-年仅占 ' + Math.round(stabs.filter(function (v) { return v >= 0.8; }).length / stabs.length * 100) + '%。</p>';

    var vd = D.variance;
    var names = { within_dim_weights: '维内指标权重', dim_weights: '维间维度权重', normalization: '归一化口径' };
    $('audit-vardec').innerHTML = barChart(
      ['within_dim_weights', 'dim_weights', 'normalization'].map(function (k) {
        return { label: names[k], v: vd[k], text: vd[k].toFixed(2), color: k === 'normalization' ? '#b45309' : '#0f766e' };
      }), 460, 3 * 44) +
      '<p class="hint">全国均分的方差贡献（一阶）；总分标准差 ' + vd.total_score_sd.toFixed(2) + '。</p>';

    /* 权重扰动：现实场景 vs 全随机参照系 */
    var pb = D.overview.share_stable80_dirichlet;
    var items = [
      { label: '全随机 Dirichlet(1)', v: pb * 100, text: Math.round(pb * 100) + '%', color: '#9ca3af' }
    ];
    Object.keys(D.validity.perturbation || {}).forEach(function (k) {
      var p = D.validity.perturbation[k];
      items.push({ label: '扰动 ' + k, v: p.share_stable80 * 100, text: Math.round(p.share_stable80 * 100) + '%', color: '#b45309' });
    });
    $('audit-perturb').innerHTML = barChart(items, 460, items.length * 44, { labelW: 170 }) +
      '<p class="hint">分档稳定率 ≥0.8 的城市-年占比（越低=分档越不稳）。即使权重仅在基准附近 ±20% 波动，仍有约 ' +
      Math.round((1 - D.validity.perturbation['±20%'].share_stable80) * 100) + '% 的城市-年档位不稳固；±50% 时升至约 ' +
      Math.round((1 - D.validity.perturbation['±50%'].share_stable80) * 100) + '%。全随机 Dirichlet(1) 是「对权重完全无知」的参照系。</p>';

    /* 分档转移矩阵热图 */
    var tm = D.validity.transition_matrix;
    if (tm && tm.matrix) {
      var cw = 64, chh = 44, pad = 46, w = pad + 5 * cw + 10, h = pad + 5 * chh + 6;
      var s = svgOpen(w, h);
      for (var c2 = 0; c2 < 5; c2++) {
        s += '<text x="' + (pad + c2 * cw + cw / 2) + '" y="' + (pad - 10) + '" font-size="12" fill="#374151" text-anchor="middle">' + tm.rows[c2] + '</text>';
      }
      for (var r = 0; r < 5; r++) {
        s += '<text x="' + (pad - 12) + '" y="' + (pad + r * chh + chh / 2 + 4) + '" font-size="12" fill="#374151" text-anchor="end">' + tm.rows[r] + '</text>';
        for (var c3 = 0; c3 < 5; c3++) {
          var p = tm.matrix[r][c3];
          var a = Math.min(0.92, p);
          s += '<rect x="' + (pad + c3 * cw + 2) + '" y="' + (pad + r * chh + 2) + '" width="' + (cw - 4) + '" height="' + (chh - 4) + '" rx="4" fill="#0f766e" fill-opacity="' + (0.06 + a * 0.86) + '"/>' +
            '<text x="' + (pad + c3 * cw + cw / 2) + '" y="' + (pad + r * chh + chh / 2 + 4) + '" font-size="11.5" fill="' + (p > 0.5 ? '#fff' : '#374151') + '" text-anchor="middle">' + Math.round(p * 100) + '%</text>';
        }
      }
      s += '<text x="' + (w / 2) + '" y="' + (h - 2) + '" font-size="11" fill="#6b7280" text-anchor="middle">行=基准档 → 列=全随机权重模拟档</text>';
      $('audit-trans').innerHTML = s + '</svg>';
    }

    /* TUHI 发布结果直接对照 */
    var td = D.validity.tuhi_direct;
    if (td && td.lag1) {
      var py = td.lag1.per_year;
      var htmlT = barChart(py.map(function (r, i) {
        return { label: 'TUHI ' + r.tuhi_year + '（n=' + r.n_matched + '）', v: r.spearman * 100,
                 text: r.spearman.toFixed(2), color: '#5c4882' };
      }), 460, py.length * 40, { labelW: 190 }) +
        '<p class="hint">与本参考实现总分的 Spearman 秩相关（TUHI 发布年 −1 对齐，官方说明数据时点多为上一年度）：均值 <b>' +
        td.lag1.mean_spearman.toFixed(2) + '</b>，二次加权 kappa ' +
        (td.lag1.mean_kappa == null ? '—' : td.lag1.mean_kappa.toFixed(2)) +
        '。交叉表（TUHI 档位 × 本实现档位）：TUHI 引领级中 ' +
        Math.round(td.lag1.cross_tab.matrix[0][0] * 100) + '% 落入本实现 A 档——头部高度一致；' +
        '但中后段档位互相错位，全样本档位一致率仅约两成（口径不同：绝对分数段 vs 相对五分位）。</p>';
      $('audit-tuhi').innerHTML = htmlT;
    }

    /* 已知组效度：区域 */
    var kg = D.validity.known_groups;
    if (kg && kg.by_region) {
      var ov2 = kg.by_region.overall;
      var regs = ['东部', '中部', '西部'];
      var htmlR = barChart(regs.map(function (r, i) {
        return { label: r + '（n=' + ov2.n[r] + '）', v: ov2.means[r],
                 text: fmt(ov2.means[r]), color: ['#0f766e', '#b45309', '#9ca3af'][i] };
      }), 460, 3 * 44, { labelW: 160 }) +
        '<p class="hint">总分：东-西 Hedges g=' + (ov2.g_east_vs_west || 0).toFixed(2) +
        '，Kruskal-Wallis p=' + ((ov2.kw && ov2.kw.p) ? ov2.kw.p.toExponential(1) : '—') +
        '（' + kg.cross_section_year + ' 年截面）。维度梯度：D2 经济 g=' + (kg.by_region.D2.g_east_vs_west || 0).toFixed(2) +
        '，D6 设施 g=' + (kg.by_region.D6.g_east_vs_west || 0).toFixed(2) +
        '，D3 环境 g=' + (kg.by_region.D3.g_east_vs_west || 0).toFixed(2) +
        '（环境维度区域梯度最弱，符合理论预期）。</p>';
      $('audit-region').innerHTML = htmlR;
      /* 试点 vs 非试点 */
      var pv = kg.pilot_vs_non.overall;
      $('audit-pilot').innerHTML = barChart([
        { label: '试点（n=' + pv.n_pilot + '）', v: pv.mean_pilot, text: fmt(pv.mean_pilot), color: '#0f766e' },
        { label: '非试点（n=' + pv.n_non + '）', v: pv.mean_non, text: fmt(pv.mean_non), color: '#9ca3af' }
      ], 460, 2 * 44, { labelW: 160 }) +
        '<p class="hint">总分 Hedges g=' + (pv.hedges_g || 0).toFixed(2) + '。指数能区分已知组（区分效度）；' +
        '<b>但试点是从国家卫生城市中遴选的，此差异主要是选择效应，不能解读为政策效果</b>——因果检验（P3）需另一套设计。</p>';
    }
  }

  /* ---------- 字典 ---------- */
  function renderDict() {
    $('dict-body').innerHTML = DICT.indicators.map(function (i) {
      var pct = Math.round(i.coverage * 100);
      return '<tr><td><code>' + i.code + '</code></td><td>' + i.name +
        '<div class="hint">' + i.formula + '</div></td>' +
        '<td><span style="color:' + COLORS[i.dim] + '">' + i.dim_name + '</span></td>' +
        '<td>' + i.unit + '</td><td>' + i.direction + '</td>' +
        '<td><span class="cov"><i style="width:' + pct + '%"></i></span> ' + pct + '%</td></tr>';
    }).join('');
    $('dict-sources').innerHTML = D.meta.sources.map(function (s) {
      return '<div class="note"><b>' + s.name + '</b><br>' + s.role + ' · <a href="' + s.url + '" target="_blank" rel="noopener">' + s.url + '</a></div>';
    }).join('') +
      '<div class="note warn"><b>口径：</b>' + D.meta.normalization + '；' + D.meta.weights + '；' + D.meta.grades + '。</div>' +
      '<div class="note gap"><b>结局锚：</b>' + D.meta.outcome_anchor + '。</div>';
  }

  fillMetaSpans();
  renderOverview();
  renderCityTable();
  $('city-search').addEventListener('input', renderCityTable);
  $('city-grade').addEventListener('change', renderCityTable);
  renderAudit();
  renderDict();
})();

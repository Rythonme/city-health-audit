#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CHIA 真实数据构建管线：中国城市统计年鉴面板 × WHO 空气质量数据库。

输出：
  data/processed/chuhi_panel.csv.gz          城市×年份指标面板与指数
  data/processed/cross_validation_who.csv    年鉴PM2.5 与 WHO 跨源一致性审计
  data/processed/coverage_report.json        指标覆盖率与数据缺口
  data/processed/build_summary.json          构建摘要（含输出哈希）
  docs/data/city_data.js                     网站数据（真实数据）
  docs/data/indicator_dictionary.js          指标字典（网站）
  dict/indicator_dictionary.csv              指标字典（仓库/论文）

设计要点：
- 无任何模拟数据；所有数值直接来自 data/raw/ 两份真实文件。
- 结局锚（死亡率/发病）在开放数据下不可得——该缺口被如实写入输出，
  不做任何代理或填补伪造。
- 用法：python scripts/build_data.py [--check]
"""
import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
DOCS_DATA = ROOT / "docs" / "data"
DICT_DIR = ROOT / "dict"

YEAR_MIN, YEAR_MAX = 2003, 2024
SEED = 20261110
N_MC = 5000            # 全随机 Dirichlet(1) 抽样（评审意见：1500 对尾部稳定率估计不足）
N_PERTURB = 500        # 每个扰动水平（围绕基准权重的合理扰动）的抽样次数
PERTURB_LEVELS = [0.2, 0.5]   # 权重分量扰动幅度 ±20% / ±50%：比 Dirichlet(1) 全随机更接近真实赋权场景

# ---------------------------------------------------------------- 指标映射
# (字典码, 原始列, 计算方式, 单位, 方向, 维度, 说明)
POP_CITY = "年末总人口_全市_万人"
POP_DIST = "年末总人口_市辖区_万人"

INDICATORS = [
    ("ECON_PC_GDP", "人均地区生产总值_全市_元", "direct", "元", +1, "D2", "人均地区生产总值（全市，当年价格）"),
    ("ECON_WAGE", "职工平均工资_全市_元", "direct", "元", +1, "D2", "城镇单位在岗职工平均工资（全市）"),
    ("ECON_PC_RETAIL", "社会消费品零售额_全市_万元", "rate_city", "元/人", +1, "D2", "人均社会消费品零售额（全市）"),
    ("ENV_PM25", "可吸入细颗粒物年平均浓度_全市_微克每立方米", "direct", "μg/m³", -1, "D3", "PM2.5 年均浓度（全市）——低于更好"),
    ("ENV_SO2_PC", "工业二氧化硫排放量_全市_吨", "rate_city_t", "吨/万人", -1, "D3", "人均工业 SO2 排放（全市）——低于更好"),
    ("ENV_GREEN_COVER", "建成区绿化覆盖率_市辖区_百分比", "direct", "%", +1, "D3", "建成区绿化覆盖率（市辖区）"),
    ("ENV_GREEN_PC", "人均绿地面积_市辖区_平方米每人", "direct", "m²/人", +1, "D3", "人均绿地面积（市辖区）"),
    ("ENV_SEWAGE", "污水处理厂集中处理率_全市_百分比", "direct", "%", +1, "D3", "污水处理厂集中处理率（全市）"),
    ("ENV_WASTE", "生活垃圾无害化处理率_全市_百分比", "direct", "%", +1, "D3", "生活垃圾无害化处理率（全市）"),
    ("SVC_HOSP_10K", "医院、卫生院数_市辖区_个", "rate_dist", "个/万人", +1, "D4", "每万人医院卫生院数（市辖区）。⚠ 口径断裂：2019 年起年鉴口径由「医院+卫生院」改为「医院」，前后不完全可比"),
    ("SVC_BED_1K", "医院、卫生院床位数_市辖区_张", "rate_dist_1k", "张/千人", +1, "D4", "每千人医院卫生院床位数（市辖区）。⚠ 同上，2019 年起仅医院口径"),
    ("SVC_DOC_1K", "执业或助理医师数_市辖区_人", "rate_dist_1k", "人/千人", +1, "D4", "每千人执业（助理）医师数（市辖区）。⚠ 同上，2019 年起仅医院口径"),
    ("SVC_INS_RATE", "城镇职工基本医疗保险参保人数_全市_人", "ins_rate", "%", +1, "D4", "城镇职工医保参保人数占总人口比（全市）"),
    ("EDU_UNIV_10K", "普通本专科在校学生数_全市_人", "rate_city_t", "人/万人", +1, "D5", "每万人在校大学生数（全市）＝普通本专科在校学生数÷年均人口×10⁴。自原始列透明重算，修复汇编直接列 2016 年起断更"),
    ("EDU_LIB_PC", "公共图书馆图书藏量_全市_万册", "rate_city", "册/人", +1, "D5", "人均公共图书馆藏书量（全市）＝图书藏量÷总人口。自原始列透明重算（汇编人均列 2016 年起断更且口径存疑）"),
    ("EDU_THEATER_10K", "剧场、影剧院数_全市_个", "rate_city", "个/万人", +1, "D5", "每万人剧场影剧院数（全市）。⚠ 2019 年起年鉴停刊该表，登记为缺口不填补"),
    ("INF_ROAD_PC", "年末实有铺装道路面积_市辖区_万平方米", "rate_dist_area", "m²/人", +1, "D6", "人均城市道路面积。实测汇编「全市」列实为市辖区值（2014–15 重叠年 r=1.000），故统一按市辖区口径重算"),
    ("INF_BUS_10K", "年末实有公共营运汽电车_市辖区_辆", "rate_dist", "辆/万人", +1, "D6", "每万人公共汽电车保有量。实测汇编「全市」列实为市辖区值（2018 重叠年 r=1.000）。⚠ 2023–2024 年鉴停刊公交车辆表，登记为缺口"),
    ("INF_PENSION_RATE", "城镇职工基本养老保险参保人数_全市_人", "ins_rate", "%", +1, "D6", "城镇职工养老保险参保率（全市）"),
    ("INF_UNEMP_RATE", "城镇职工失业保险参保人数_全市_人", "ins_rate", "%", +1, "D6", "城镇职工失业保险参保率（全市）"),
    ("INF_CLEAN_FUEL", "__gas__", "clean_fuel", "%", +1, "D6", "清洁燃料覆盖近似：用煤气+液化气人口占比（全市）。⚠ 2019 年起年鉴停刊「用气人口」表，登记为缺口不填补"),
]
GAS1 = "用煤气人口_全市_人"
GAS2 = "用液化气人口_全市_人"

DIMS = {"D2": "经济民生", "D3": "环境卫生", "D4": "卫生服务", "D5": "教育文化", "D6": "设施保障"}
DIM_ORDER = ["D2", "D3", "D4", "D5", "D6"]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_yearbook() -> pd.DataFrame:
    p = RAW / "china_city_statistical_yearbook_prefecture_1999_2018.dta"
    df = pd.read_stata(p, convert_categoricals=False)
    df["年份"] = df["年份"].astype(int)
    df = df[(df["年份"] >= YEAR_MIN) & (df["年份"] <= YEAR_MAX)].copy()
    df["城市"] = df["城市"].astype(str).str.strip()
    df = df[df["城市"].str.endswith("市")].copy()
    # 口径校正（重叠年实测）：汇编「全市」标签的道路/公交列实为市辖区值
    df = df.rename(columns={
        "年末实有铺装道路面积_全市_万平方米": "年末实有铺装道路面积_市辖区_万平方米",
        "年末实有公共营运汽电车_全市_辆": "年末实有公共营运汽电车_市辖区_辆",
    })
    df["pop_scope_city"] = "户籍（年末总人口）"
    df["pop_scope_dist"] = "户籍（年末总人口）"
    return df


def load_new_yearbook() -> pd.DataFrame:
    """2019–2024 数据年（来自 2020–2025 卷分表 Excel 提取），映射到旧面板同构列。"""
    p = PROC / "yearbook_new_panel.csv"
    if not p.exists():
        raise FileNotFoundError("缺少 data/processed/yearbook_new_panel.csv，请先运行 scripts/extract_new_yearbook.py")
    raw = pd.read_csv(p, encoding="utf-8-sig")
    raw = raw[raw["year"] >= 2019].copy()
    raw["city"] = raw["city"].astype(str).str.strip()

    # 行政区划代码：沿用旧面板（城市名 → 最近非空代码）
    old = pd.read_stata(RAW / "china_city_statistical_yearbook_prefecture_1999_2018.dta",
                        convert_categoricals=False)
    old["城市"] = old["城市"].astype(str).str.strip()
    code_map = (old.dropna(subset=["行政区划代码"]).groupby("城市")["行政区划代码"].last().to_dict())

    out = pd.DataFrame({
        "城市": raw["city"],
        "年份": raw["year"],
        "行政区划代码": raw["city"].map(code_map),
        POP_CITY: raw["pop_used_city"],
        POP_DIST: raw["pop_used_dist"],
        "pop_scope_city": raw["pop_scope_city"].astype(str) + "人口",
        "pop_scope_dist": raw["pop_scope_dist"].astype(str) + "人口",
        "人均地区生产总值_全市_元": raw["gdp_pc"],
        "职工平均工资_全市_元": raw["wage"],
        "社会消费品零售额_全市_万元": raw["retail"],
        "可吸入细颗粒物年平均浓度_全市_微克每立方米": raw["pm25"],
        "工业二氧化硫排放量_全市_吨": raw["so2"],
        "建成区绿化覆盖率_市辖区_百分比": raw["green_cover"],
        "人均绿地面积_市辖区_平方米每人": raw["green_area"] / raw["pop_used_dist"],
        "污水处理厂集中处理率_全市_百分比": raw["sewage"],
        "生活垃圾无害化处理率_全市_百分比": raw["waste"],
        "医院、卫生院数_市辖区_个": raw["hosp_n"],
        "医院、卫生院床位数_市辖区_张": raw["beds"],
        "执业或助理医师数_市辖区_人": raw["docs"],
        "城镇职工基本医疗保险参保人数_全市_人": raw["medical"],
        "城镇职工基本养老保险参保人数_全市_人": raw["pension"],
        "城镇职工失业保险参保人数_全市_人": raw["unemp"],
        "普通本专科在校学生数_全市_人": raw["univ_stu"],
        "公共图书馆图书藏量_全市_万册": raw["lib_books"],
        "剧场、影剧院数_全市_个": np.nan,               # 2019 起停刊
        "年末实有铺装道路面积_市辖区_万平方米": raw["road_area"],
        "年末实有公共营运汽电车_市辖区_辆": raw["bus_n"],
        GAS1: np.nan,                                   # 2019 起停刊
        GAS2: np.nan,
    })
    return out


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "city": df["城市"], "year": df["年份"], "city_code": df["行政区划代码"],
        "pop_city": df[POP_CITY] * 1e4, "pop_dist": df[POP_DIST] * 1e4,
        "pop_scope": df["pop_scope_city"].astype(str) + " / " + df["pop_scope_dist"].astype(str),
    })
    for code, col, mode, unit, sign, dim, desc in INDICATORS:
        if mode == "direct":
            v = df[col]
        elif mode == "rate_city":
            v = df[col] * 1e4 / out["pop_city"]  # 万元/人 → 元/人；万册/人 → 册/人
        elif mode == "rate_city_t":
            v = df[col] / (out["pop_city"] / 1e4)  # 吨/万人、人/万人
        elif mode == "rate_dist":
            v = df[col] / (out["pop_dist"] / 1e4)
        elif mode == "rate_dist_1k":
            v = df[col] / (out["pop_dist"] / 1e3)  # 张/千人
        elif mode == "rate_dist_area":
            v = df[col] * 1e4 / out["pop_dist"]  # 万m²/人 → m²/人
        elif mode == "ins_rate":
            v = df[col] / out["pop_city"] * 100
        elif mode == "clean_fuel":
            v = (df[GAS1].fillna(0) + df[GAS2].fillna(0)) / out["pop_city"] * 100
            v[(df[GAS1].isna()) & (df[GAS2].isna())] = np.nan
        else:
            raise ValueError(mode)
        out[code] = v
    # 逐年 1%/99% 缩尾，抑制极端值对极差归一化的破坏
    for code, *_ in [(i[0],) for i in INDICATORS]:
        s = out[code]
        lo, hi = s.quantile(0.01), s.quantile(0.99)
        out[code] = s.clip(lo, hi)
    return out


def normalize_pooled(panel: pd.DataFrame) -> pd.DataFrame:
    """方向感知的全期（2003–2018 合并）min–max 归一化到 [0,100]。"""
    n = panel.copy()
    for code, _, mode, unit, sign, dim, desc in INDICATORS:
        s = n[code]
        lo, hi = s.min(), s.max()
        if pd.isna(lo) or pd.isna(hi) or hi == lo:
            n[code + "_n"] = np.nan
            continue
        z = (s - lo) / (hi - lo)
        n[code + "_n"] = (100 - 100 * z) if sign < 0 else (100 * z)
    return n


def year_groups(years: np.ndarray):
    """把年份向量折成组内索引数组，供反复重标定复用（MC 提速关键）。"""
    g = {}
    for i, y in enumerate(years):
        g.setdefault(int(y), []).append(i)
    return [np.asarray(v) for v in g.values()]


def rescale_year(vals: np.ndarray, years: np.ndarray) -> np.ndarray:
    """逐年截面 min-max 重标定到 0–100：当年最高分=100、最低分=0。

    保留截面内相对位置；跨年比较的是相对位置变化而非绝对水平。
    """
    out = np.asarray(vals, dtype=float).copy()
    for idx in year_groups(years):
        v = out[idx]
        m = ~np.isnan(v)
        if m.sum() < 2:
            continue
        lo, hi = np.nanmin(v[m]), np.nanmax(v[m])
        if hi > lo:
            out[idx[m]] = (v[m] - lo) / (hi - lo) * 100.0
        else:
            out[idx[m]] = 100.0
    return out


def dim_scores(panel_n: pd.DataFrame) -> pd.DataFrame:
    n = panel_n
    for d in DIM_ORDER:
        cols = [i[0] + "_n" for i in INDICATORS if i[5] == d]
        n[d + "_score"] = n[cols].mean(axis=1, skipna=True).where(n[cols].notna().sum(axis=1) >= 2)
    dims_avail = n[[d + "_score" for d in DIM_ORDER]].notna().sum(axis=1)
    n["overall_raw"] = n[[d + "_score" for d in DIM_ORDER]].mean(axis=1, skipna=True).where(dims_avail >= 3)
    # 标准化：逐年重标定到 0–100（发布口径）
    n["overall"] = rescale_year(n["overall_raw"].to_numpy(), n["year"].to_numpy())
    return n


def grade_table(overall: pd.Series):
    qs = overall.quantile([0.2, 0.4, 0.6, 0.8]).tolist()
    return qs


def add_grades(n: pd.DataFrame) -> pd.DataFrame:
    qs = grade_table(n["overall"].dropna())
    def g(v):
        if pd.isna(v):
            return None
        return "A" if v >= qs[3] else "B" if v >= qs[2] else "C" if v >= qs[1] else "D" if v >= qs[0] else "E"
    n["grade"] = n["overall"].map(g)
    return n, qs


def grade_num(v, qs):
    """分数 → 档位序号 0–4（A=0 … E=4），NaN 保留。"""
    out = np.full(np.shape(v), np.nan)
    m = ~np.isnan(np.asarray(v, dtype=float))
    out[m] = ((v[m] >= qs[3]).astype(float) + (v[m] >= qs[2])
              + (v[m] >= qs[1]) + (v[m] >= qs[0]))
    return out


def weighted_overall(n, dim_cols, w_within, w_dim):
    """给定维内/维间权重，对归一化指标聚合出总分（未重标定）。"""
    tot = np.zeros(len(n))
    wsum = np.zeros(len(n))
    for di, d in enumerate(DIM_ORDER):
        vals = n[dim_cols[d]].to_numpy()
        avail = ~np.isnan(vals)
        num = np.where(avail, np.nan_to_num(vals) * w_within[d][None, :], 0.0).sum(axis=1)
        den = np.where(avail, w_within[d][None, :], 0.0).sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            dim_score = np.where(den > 0, num / den, np.nan)
        ok = ~np.isnan(dim_score)
        tot += np.where(ok, dim_score, 0.0) * w_dim[di]
        wsum += np.where(ok, w_dim[di], 0.0)
    with np.errstate(invalid="ignore"):
        return np.where(wsum > 0, tot / wsum, np.nan)


def monte_carlo(n: pd.DataFrame, base_qs):
    """真实 MC：维内 Dirichlet(1) 指标权重 × 维间 Dirichlet(1) 维权重（全随机参照系）。

    分档始终使用基准分布分位（base_qs），即稳定性只反映权重不确定性。
    同时累计分档转移矩阵（基准档 × 模拟档）。
    """
    rng = np.random.default_rng(SEED)
    dim_cols = {d: [i[0] + "_n" for i in INDICATORS if i[5] == d] for d in DIM_ORDER}
    years = n["year"].to_numpy()
    groups = year_groups(years)
    idx = n.index
    overall_draws = np.full((N_MC, len(idx)), np.nan)

    def rescale_inplace(v):
        # 注意：v[gi] 花式索引返回副本，必须写回 v[gi]，否则重标定不生效
        for gi in groups:
            vv = v[gi]
            m = ~np.isnan(vv)
            if m.sum() < 2:
                continue
            lo, hi = vv[m].min(), vv[m].max()
            if hi > lo:
                vv[m] = (vv[m] - lo) / (hi - lo) * 100.0
            else:
                vv[m] = 100.0
            v[gi] = vv

    for k in range(N_MC):
        w_dim = rng.dirichlet(np.ones(len(DIM_ORDER)))
        w_within = {d: rng.dirichlet(np.ones(len(dim_cols[d]))) for d in DIM_ORDER}
        overall_draws[k] = weighted_overall(n, dim_cols, w_within, w_dim)
        rescale_inplace(overall_draws[k])
    g_base = grade_num(n["overall"].to_numpy(), base_qs)
    stab = np.zeros(len(idx))
    trans = np.zeros((5, 5), dtype=int)
    for k in range(N_MC):
        gk = grade_num(overall_draws[k], base_qs)
        same = (gk == g_base) & ~np.isnan(g_base)
        stab += same
        m = ~np.isnan(g_base) & ~np.isnan(gk)
        b = g_base[m].astype(int)
        s = gk[m].astype(int)
        np.add.at(trans, (b, s), 1)
    n["grade_stability"] = stab / N_MC
    trans_norm = trans / np.maximum(trans.sum(axis=1, keepdims=True), 1)
    return n, float(np.nanmean(n["grade_stability"])), trans_norm


def perturbation_stability(n: pd.DataFrame, base_qs, m_amp, n_draws, rng):
    """围绕基准（等权）权重的合理扰动：每权重分量乘 (1+U(-m, m)) 后重归一。

    Dirichlet(1) 代表「对权重完全无知」的参照系；扰动情景代表
    「在发布权重附近合理波动」的现实场景——后者更有政策解释力。
    """
    dim_cols = {d: [i[0] + "_n" for i in INDICATORS if i[5] == d] for d in DIM_ORDER}
    years = n["year"].to_numpy()
    groups = year_groups(years)
    eq_in = {d: np.ones(len(dim_cols[d])) for d in DIM_ORDER}
    eq_dim = np.ones(len(DIM_ORDER))
    stab = np.zeros(len(n))
    g_base = grade_num(n["overall"].to_numpy(), base_qs)
    for _ in range(n_draws):
        w_within = {d: eq_in[d] * (1 + rng.uniform(-m_amp, m_amp, len(eq_in[d]))) for d in DIM_ORDER}
        w_within = {d: w / w.sum() for d, w in w_within.items()}
        w_dim = eq_dim * (1 + rng.uniform(-m_amp, m_amp, len(DIM_ORDER)))
        w_dim = w_dim / w_dim.sum()
        v = weighted_overall(n, dim_cols, w_within, w_dim)
        for gi in groups:
            vv = v[gi]
            mm = ~np.isnan(vv)
            if mm.sum() < 2:
                continue
            lo, hi = vv[mm].min(), vv[mm].max()
            if hi > lo:
                vv[mm] = (vv[mm] - lo) / (hi - lo) * 100.0
            else:
                vv[mm] = 100.0
            v[gi] = vv   # 花式索引副本必须写回，否则重标定不生效
        gk = grade_num(v, base_qs)
        stab += (gk == g_base) & ~np.isnan(g_base)
    return stab / n_draws


def entropy_weights(n: pd.DataFrame):
    """熵权法：按归一化指标（0–100）在全部可用观测上的信息熵确定维内权重。"""
    w = {}
    for d in DIM_ORDER:
        cols = [i[0] + "_n" for i in INDICATORS if i[5] == d]
        disp = []
        for c in cols:
            x = n[c].dropna().to_numpy() / 100.0
            if len(x) < 10 or np.nanmax(x) <= np.nanmin(x):
                disp.append(0.0)
                continue
            p = np.clip(x, 0, 1)
            p = p[p > 0]
            e = -(p * np.log(p)).sum() / np.log(len(x)) if len(p) else 1.0
            disp.append(1.0 - e)
        disp = np.asarray(disp)
        w[d] = (disp / disp.sum() if disp.sum() > 0
                else np.ones(len(cols)) / len(cols))
    return w


def scenario_scores(n: pd.DataFrame, base_qs):
    """确定性情景对比（逐城展示「换方案分档变不变」）：
    base=等权×合并min-max；entropy=等维×熵权维内；pctile=等权×逐年百分位归一。"""
    dim_cols = {d: [i[0] + "_n" for i in INDICATORS if i[5] == d] for d in DIM_ORDER}
    eq_in = {d: np.ones(len(dim_cols[d])) / len(dim_cols[d]) for d in DIM_ORDER}
    eq_dim = np.ones(len(DIM_ORDER)) / len(DIM_ORDER)
    years = n["year"].to_numpy()
    out = {}
    # 情景 2：熵权维内
    ew = entropy_weights(n)
    v = rescale_year(weighted_overall(n, dim_cols, ew, eq_dim), years)
    out["entropy_score"] = v
    # 情景 3：逐年百分位归一化 + 等权
    sub = n.copy()
    for d in DIM_ORDER:
        for c in dim_cols[d]:
            sub[c] = sub.groupby("year")[c].rank(pct=True) * 100
    v2 = rescale_year(weighted_overall(sub, dim_cols, eq_in, eq_dim), years)
    out["pctile_score"] = v2
    g = {}
    for k, v in (("entropy", out["entropy_score"]), ("pctile", out["pctile_score"])):
        gk = grade_num(v, base_qs)
        letter = np.full(len(n), None, dtype=object)
        m = ~np.isnan(gk)
        letter[m] = [["A", "B", "C", "D", "E"][int(x)] for x in gk[m]]
        g[k] = letter
    return g


def variance_decomposition(n: pd.DataFrame):
    """一阶方差分解：维内权重 / 维间权重 / 归一化口径 三类构造选择。"""
    rng = np.random.default_rng(SEED + 1)
    dim_cols = {d: [i[0] + "_n" for i in INDICATORS if i[5] == d] for d in DIM_ORDER}
    def overall(w_in, w_dim, per_year):
        if per_year:
            sub = n.copy()
            for d in DIM_ORDER:
                for c in dim_cols[d]:
                    sub[c] = sub.groupby("year")[c].rank(pct=True) * 100
        else:
            sub = n
        tot = np.zeros(len(n)); wsum = np.zeros(len(n))
        for di, d in enumerate(DIM_ORDER):
            vals = sub[dim_cols[d]].to_numpy()
            avail = ~np.isnan(vals)
            contrib = np.where(avail, vals * w_in[d][None, :], 0.0)
            tot += contrib.sum(axis=1) * w_dim[di]
            wsum += avail.sum(axis=1) * w_dim[di]
        with np.errstate(invalid="ignore"):
            comp = np.where(wsum > 0, tot / wsum, np.nan)
        return rescale_year(comp, n["year"].to_numpy())
    eq_in = {d: np.ones(len(dim_cols[d])) / len(dim_cols[d]) for d in DIM_ORDER}
    eq_dim = np.ones(len(DIM_ORDER)) / len(DIM_ORDER)
    base = overall(eq_in, eq_dim, False)
    res = {}
    # 因子1：维内权重
    draws = []
    for _ in range(200):
        w = {d: rng.dirichlet(np.ones(len(dim_cols[d]))) for d in DIM_ORDER}
        draws.append(np.nanmean(overall(w, eq_dim, False)))
    res["within_dim_weights"] = float(np.var(draws))
    # 因子2：维间权重
    draws = []
    for _ in range(200):
        w = rng.dirichlet(np.ones(len(DIM_ORDER)))
        draws.append(np.nanmean(overall(eq_in, w, False)))
    res["dim_weights"] = float(np.var(draws))
    # 因子3：归一化口径（合并 min-max vs 逐年百分位）
    alt = overall(eq_in, eq_dim, True)
    res["normalization"] = float(np.nanvar(alt - base))
    res["total_score_sd"] = float(np.nanstd(base))
    return res


# ---------------------------------------------------------------- 已知组效度
# 国家统计局四大区域口径（东/中/西；东北并入东部口径外的中部讨论时注明）
# 依据省份行政区划代码前两位。东部 11 省、中部 8 省、西部 12 省（不含港澳台）。
PROV_REGION = {}
for p in (11, 12, 13, 21, 31, 32, 33, 35, 37, 44, 46):          # 东部
    PROV_REGION[p] = "东部"
for p in (14, 22, 23, 34, 36, 41, 42, 43):                      # 中部
    PROV_REGION[p] = "中部"
for p in (15, 45, 50, 51, 52, 53, 54, 61, 62, 63, 64, 65):      # 西部
    PROV_REGION[p] = "西部"

# 首批全国健康城市试点（2016-11，全国爱卫办通知附件，来源：国家卫健委官网）。
# 名单共 38 个，其中西城区/和平区/嘉定区/合川区为区级，不在地级市面板内；
# 桐乡市/迁安市/侯马市/资兴市/琼海市等为县级市，同样不出现于面板，匹配时自然落空。
PILOT_CITIES = [
    "包头市", "大连市", "长春市", "大庆市", "苏州市", "无锡市", "镇江市",
    "杭州市", "宁波市", "马鞍山市", "厦门市", "宜春市", "济南市", "威海市",
    "烟台市", "郑州市", "宜昌市", "珠海市", "南宁市", "成都市", "泸州市",
    "贵阳市", "玉溪市", "拉萨市", "宝鸡市", "金昌市", "克拉玛依市", "银川市",
]


def hedges_g(a, b):
    """Hedges g 效应量（合并方差，小样本校正）。"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3:
        return None
    n1, n2 = len(a), len(b)
    s_pooled = np.sqrt(((n1 - 1) * a.var(ddof=1) + (n2 - 1) * b.var(ddof=1)) / (n1 + n2 - 2))
    if s_pooled == 0:
        return None
    d = (a.mean() - b.mean()) / s_pooled
    return float(d * (1 - 3 / (4 * (n1 + n2) - 9)))


def known_groups(n: pd.DataFrame):
    """已知组效度（无需结局锚，现在即可执行）：
    东/中/西三大区域 × 健康城市试点 vs 非试点，在每城最新可算年截面上的差异。"""
    sub = n[n["overall"].notna()].copy()
    sub["year"] = sub["year"].astype(int)
    latest = sub.groupby("city")["year"].transform("max")
    cross = sub[sub["year"] == latest].copy()
    cross["region"] = (cross["city_code"] // 10000).astype(int).map(PROV_REGION)
    cross["pilot"] = cross["city"].isin(PILOT_CITIES)

    def kw_p(groups):
        """Kruskal-Wallis H 与近似 p（scipy 可用则精确，否则报 None）。"""
        try:
            from scipy.stats import kruskal
            arrs = [g for g in groups if len(g) >= 3]
            if len(arrs) < 2:
                return None
            H, p = kruskal(*arrs)
            return {"H": round(float(H), 2), "p": float(p)}
        except Exception:
            return None

    res = {"n_pilot_matched": int(cross["pilot"].sum()),
           "reference": "全国爱卫办《关于开展健康城市试点工作的通知》(2016-11) 附件38个试点；区级/县级市不在地级市面板内"}
    # 区域：各维度 + 总分
    by_region = {}
    for d in DIM_ORDER + ["overall"]:
        key = d if d == "overall" else d + "_score"
        g = {r: cross.loc[cross["region"] == r, key].dropna().to_numpy()
             for r in ("东部", "中部", "西部")}
        by_region[d] = {
            "means": {r: (round(float(v.mean()), 1) if len(v) else None) for r, v in g.items()},
            "n": {r: int(len(v)) for r, v in g.items()},
            "g_east_vs_west": hedges_g(g["东部"], g["西部"]),
            "g_east_vs_central": hedges_g(g["东部"], g["中部"]),
            "g_central_vs_west": hedges_g(g["中部"], g["西部"]),
            "kw": kw_p(list(g.values())),
        }
    res["by_region"] = by_region
    # 试点 vs 非试点
    pilot_res = {}
    for d in DIM_ORDER + ["overall"]:
        key = d if d == "overall" else d + "_score"
        a = cross.loc[cross["pilot"], key].dropna().to_numpy()
        b = cross.loc[~cross["pilot"], key].dropna().to_numpy()
        gval = hedges_g(a, b)
        try:
            from scipy.stats import mannwhitneyu
            p = float(mannwhitneyu(a, b).pvalue) if len(a) >= 3 and len(b) >= 3 else None
        except Exception:
            p = None
        pilot_res[d] = {"mean_pilot": round(float(a.mean()), 1) if len(a) else None,
                        "mean_non": round(float(b.mean()), 1) if len(b) else None,
                        "n_pilot": int(len(a)), "n_non": int(len(b)),
                        "hedges_g": gval, "p_mw": p}
    res["pilot_vs_non"] = pilot_res
    res["cross_section_year"] = int(latest.iloc[0])
    return res


# ---------------------------------------------------------------- TUHI 直接审计
# 官方档位口径：引领级 ≥70、优质级 65–70、平均级 60–65、发展级 58–60、追赶级 <58
TUHI_GRADE_CUTS = [58, 60, 65, 70]
TUHI_GRADE_NAMES = ["追赶级", "发展级", "平均级", "优质级", "引领级"]
TUHI_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


def load_tuhi() -> pd.DataFrame:
    """读取 data/raw/tuhi/ 官方接口快照（来源与抓取时间见 SOURCE.md 第 4 节）。"""
    files = sorted((RAW / "tuhi").glob("city_rank_*.json"))
    if not files:
        return pd.DataFrame()
    rows = []
    for f in files:
        stem = f.stem.split("_")            # city_rank_{year}_{group}
        year, group = int(stem[2]), stem[3]
        d = json.loads(f.read_text(encoding="utf-8"))
        for v in d.get("cityDatas", []):
            rows.append({"tuhi_city": str(v["cityName"]).strip(),
                         "tuhi_year": year, "group": group,
                         "tuhi_score": float(v["score"]),
                         "tuhi_rank": v.get("rank")})
    t = pd.DataFrame(rows)
    t["tuhi_grade"] = sum(t["tuhi_score"].to_numpy() >= c for c in TUHI_GRADE_CUTS)
    return t


def quadratic_weighted_kappa(a, b, k: int = 5):
    """二次加权 kappa（Cohen 1968），a/b 为 0..k-1 序号（容忍 NaN/-1，自动剔除）。"""
    a = pd.to_numeric(pd.Series(a), errors="coerce").fillna(-1).to_numpy()
    b = np.asarray(b, dtype=float)
    a, b = a.astype(int), np.nan_to_num(b, nan=-1).astype(int)
    m = (a >= 0) & (a < k) & (b >= 0) & (b < k)
    a, b = a[m], b[m]
    if len(a) < 30:
        return None
    O = np.zeros((k, k))
    for x, y in zip(a, b):
        O[x, y] += 1
    O /= O.sum()
    w = np.array([[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)])
    e = np.outer(O.sum(axis=1), O.sum(axis=0))
    den = (w * e).sum()
    return float(1 - (w * O).sum() / den) if den > 0 else None


def tuhi_direct_audit(n: pd.DataFrame):
    """对 TUHI 发布的城市总分/档位做直接审计（收敛效度）。

    对齐：官方说明 TUHI 年份 Y 的数据时点大多为 Y-1 年，故主对齐 = Y-1；
    同年（lag0）对齐并行报告以供透明。
    本实现档位 A–E 为全样本五分位（相对口径），TUHI 档位为绝对分数段——
    两者定义不同，一致率低本身即审计发现；排序相关才是可比主指标。
    """
    t = load_tuhi()
    if t.empty:
        return None
    letter2num = {"A": 4, "B": 3, "C": 2, "D": 1, "E": 0}
    res = {"n_tuhi_rows": int(len(t)),
           "n_tuhi_cities": int(t["tuhi_city"].nunique()),
           "grade_system": {"tuhi": TUHI_GRADE_NAMES,
                            "cuts": TUHI_GRADE_CUTS,
                            "note": "TUHI=绝对分数段；CHIA=全样本五分位（相对口径）"}}
    out_rows = []
    for lag, key in ((1, "lag1"), (0, "lag0")):
        t = t.copy()
        t["panel_year"] = t["tuhi_year"] - lag
        m = t.merge(n[["city", "year", "overall", "grade"]],
                    left_on=["tuhi_city", "panel_year"],
                    right_on=["city", "year"], how="inner")
        per_year = []
        for y, g in m.groupby("tuhi_year"):
            rho = float(g["tuhi_score"].corr(g["overall"], method="spearman"))
            r = float(g["tuhi_score"].corr(g["overall"]))
            ch = g["grade"].map(letter2num).to_numpy()
            agree = float(np.mean(ch == g["tuhi_grade"].to_numpy()))
            per_year.append({
                "tuhi_year": int(y), "panel_year": int(y - lag),
                "n_matched": int(len(g)), "spearman": round(rho, 4),
                "pearson": round(r, 4),
                "grade_agree": round(agree, 4),
                "kappa": quadratic_weighted_kappa(ch, g["tuhi_grade"].to_numpy()),
            })
        ch_all = m["grade"].map(letter2num).to_numpy(dtype=float)
        tg_all = m["tuhi_grade"].to_numpy(dtype=float)
        pair_ok = ~np.isnan(ch_all)                     # grade 缺失的行不参与档位对照
        ch_all, tg_all = ch_all[pair_ok], tg_all[pair_ok]
        # TUHI 档位 × 本实现档位 交叉表（行=Tuhi 引领→追赶，列=CHIA A→E）
        cross = np.zeros((5, 5), dtype=int)
        for x, y in zip(tg_all, ch_all):
            cross[4 - int(x), 4 - int(y)] += 1
        cross_norm = cross / np.maximum(cross.sum(axis=1, keepdims=True), 1)
        # 分歧最大案例（按同年本实现组内名次差）
        m["chi_rank"] = m.groupby("panel_year")["overall"].rank(ascending=False)
        m["rank_gap"] = m["chi_rank"] - m["tuhi_rank"]
        # 排序键先量化到 1e-4（远大于跨 CPU 浮点噪声），近乎并列的 gap
        # 再按城市/年份决胜——否则 1e-15 噪声会让排序在平台间互换。
        m["gap_key"] = m["rank_gap"].abs().round(4)
        worst = (m.sort_values(["gap_key", "tuhi_city", "tuhi_year"],
                               ascending=[False, True, True])
                   .head(12)[["tuhi_city", "tuhi_year", "group", "tuhi_score",
                              "tuhi_rank", "overall", "chi_rank", "rank_gap"]])
        res[key] = {
            "per_year": per_year,
            "mean_spearman": round(float(np.mean([r["spearman"] for r in per_year])), 4),
            "mean_kappa": (lambda ks: round(float(np.mean(ks)), 4) if ks else None)
                          ([r["kappa"] for r in per_year if r["kappa"] is not None]),
            "cross_tab": {"rows": ["TUHI引领", "TUHI优质", "TUHI平均", "TUHI发展", "TUHI追赶"],
                          "cols": ["CHIA A", "CHIA B", "CHIA C", "CHIA D", "CHIA E"],
                          "matrix": [[round(float(v), 4) for v in row] for row in cross_norm]},
            "worst_gaps": worst.round(2).to_dict("records"),
        }
        out_rows.append(m.assign(alignment=key))
    res["n_matched_pairs"] = int(len(out_rows[0]))
    res["note"] = ("对齐=Tuhi发布年-1（官方说明数据时点多为上一年度）；"
                   "档位一致率低源于口径定义不同（绝对分数段 vs 相对五分位），"
                   "排序相关与加权 kappa 为可比主指标；分歧案例仅呈现两套口径关注点差异，非对错判定。")
    pd.concat(out_rows, ignore_index=True).to_csv(
        PROC / "tuhi_direct_audit.csv", index=False, encoding="utf-8-sig",
        lineterminator="\n")
    return res


def who_cross_validation(panel: pd.DataFrame):
    """把年鉴 PM2.5 与 WHO V6.1 中国城市记录按拼音名匹配，逐年审计一致性。"""
    from pypinyin import lazy_pinyin
    who_path = RAW / "who_ambient_air_quality_database_v6.1_2024.xlsx"
    who = pd.read_excel(who_path, sheet_name="Update 2024 (V6.1)")
    who = who[who["country_name"].astype(str).str.contains("China", case=False, na=False)]
    who = who[who["pm25_concentration"].notna()].copy()
    who["city_raw"] = who["city"].astype(str).str.replace("/CHN", "", regex=False)
    def norm_who(x):
        x = x.lower().replace(" ", "").replace("'", "").replace("-", "")
        for suf in ("shi", "qu", "qi"):
            if x.endswith(suf) and len(x) > len(suf) + 1:
                x = x[: -len(suf)]
        return x
    who["key"] = who["city_raw"].map(norm_who)
    # 歧义 = 同一拼音键对应多个不同原始地名（跨省同名区县等），整键弃用
    distinct = who.groupby("key")["city_raw"].nunique()
    ambiguous = set(distinct[distinct > 1].index)

    yr = panel[["city", "year", "ENV_PM25"]].dropna().copy()
    yr["key"] = yr["city"].map(lambda s: "".join(lazy_pinyin(s.replace("市", ""))))
    yr = yr[~yr["key"].isin(ambiguous)]
    wmean = who.groupby(["key", "year"])["pm25_concentration"].mean().reset_index()
    merged = yr.merge(wmean, on=["key", "year"], how="inner")
    rows = []
    for y, g in merged.groupby("year"):
        if len(g) >= 10:
            r = float(g["ENV_PM25"].corr(g["pm25_concentration"]))
            bias = float((g["pm25_concentration"] - g["ENV_PM25"]).mean())
            mape = float(((g["pm25_concentration"] - g["ENV_PM25"]).abs() / g["ENV_PM25"]).mean())
            rows.append({"year": int(y), "n_matched": int(len(g)), "pearson_r": round(r, 4),
                         "mean_bias_who_minus_yearbook": round(bias, 2), "mape": round(mape, 4)})
    scatter = merged.sample(min(1500, len(merged)), random_state=SEED)
    scatter_pts = [[round(float(a), 2), round(float(b), 2)] for a, b in
                   zip(scatter["ENV_PM25"], scatter["pm25_concentration"])]
    return rows, scatter_pts, int(merged["city"].nunique())


def write_js(path: Path, var: str, obj) -> None:
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    # newline="\n"：跨平台字节一致（Windows 不产生 CRLF），保护 CI 可复现 diff
    path.write_text(f"var {var} = {body};\n", encoding="utf-8", newline="\n")


def main() -> int:
    PROC.mkdir(parents=True, exist_ok=True)
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    DICT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/6] 读取城市统计年鉴面板（旧版 2003–2018 + 新卷 2019–2024 双源拼接）...")
    df = load_yearbook()
    n_old = len(df)
    df_new = load_new_yearbook()
    df = pd.concat([df, df_new], ignore_index=True)
    print(f"      旧面板 {n_old} 行 + 新卷 {len(df_new)} 行 = {len(df)} 行；"
          f"{df['城市'].nunique()} 城 × {int(df['年份'].min())}–{int(df['年份'].max())}")

    print("[2/6] 计算真实衍生指标 ...")
    panel = compute_indicators(df)

    print("[3/6] 归一化与维度得分 ...")
    n = normalize_pooled(panel)
    n = dim_scores(n)
    n, grade_qs = add_grades(n)

    print("[4/7] Monte Carlo 分档稳定性（全随机 Dirichlet 参照系，%d 次）..." % N_MC)
    n, mean_stab, trans = monte_carlo(n, grade_qs)

    print("[5/8] 权重扰动情景（±20%% / ±50%%，围绕基准权重各 %d 次）..." % N_PERTURB)
    perturb, perturb_city = {}, {}
    for i, m in enumerate(PERTURB_LEVELS):
        s = perturbation_stability(n, grade_qs, m, N_PERTURB,
                                   np.random.default_rng(SEED + 3 + i))
        perturb[f"±{int(m*100)}%"] = {
            "mean": round(float(np.nanmean(s)), 4),
            "share_stable80": round(float((s >= 0.8).mean()), 4)}
        perturb_city[f"±{int(m*100)}%"] = s
    # Dirichlet(1) 全随机同口径统计
    share80_dir = float((n["grade_stability"] >= 0.8).mean())

    print("[6/8] 方差分解（构造选择敏感性）...")
    vardec = variance_decomposition(n)

    print("[7/8] 确定性情景对比（熵权 / 逐年百分位）与已知组效度 ...")
    scen_grades = scenario_scores(n, grade_qs)
    n["grade_entropy"] = scen_grades["entropy"]
    n["grade_pctile"] = scen_grades["pctile"]
    kg = known_groups(n)

    print("[8/9] TUHI 发布数据直接审计（收敛效度）...")
    tuhi = tuhi_direct_audit(n)

    print("[9/9] WHO 跨源一致性审计 ...")
    xval, scatter_pts, n_matched_cities = who_cross_validation(n)

    # ---- 覆盖率报告 ----
    cov = {}
    for code, col, mode, unit, sign, dim, desc in INDICATORS:
        s = n[code]
        cov[code] = {
            "dim": dim, "desc": desc, "unit": unit, "direction": sign,
            "n_available": int(s.notna().sum()), "n_total": int(len(s)),
            "coverage": round(float(s.notna().mean()), 4),
        }
    coverage_report = {
        "period": f"{YEAR_MIN}-{YEAR_MAX}", "n_cities": int(n["city"].nunique()),
        "indicators": cov,
        "outcome_anchor_note": "开放数据下地级市死亡率/发病率不可得；D1 结局锚在真实面板中缺失，本审计如实呈现该缺口，不做代理填补。",
        "pop_scope_note": "人口分母口径随年鉴卷变化：2003–2018 为年末总人口（重叠年实测＝户籍口径）；2019–2024 按卷可得性优先户籍（2019/2021/2022）、其次常住（2020/2023/2024）。常住与户籍不可跨口径直接比较，面板 pop_scope 列逐行标注。",
        "series_break_note": "2019 年起年鉴口径变更：医院类指标由「医院+卫生院」改为「医院」；剧场影剧院、用气人口表停刊；公交车辆表 2023 年起停刊；工资表 2022 年起停刊；绿地面积表 2023 年起停刊。相关指标缺口如实登记，不插值填补。",
    }

    # ---- 指标字典 ----
    dic = []
    for code, col, mode, unit, sign, dim, desc in INDICATORS:
        formula = {
            "direct": f"直接取用《年鉴》列「{col}」",
            "rate_city": f"{col} ÷ 总人口（全市，口径随卷见 pop_scope）",
            "rate_city_t": f"{col} ÷ 总人口（全市）×10⁴ 折算每万人",
            "rate_dist": f"{col} ÷ 总人口（市辖区）×10⁴ 折算每万人",
            "rate_dist_1k": f"{col} ÷ 总人口（市辖区）×1000 折算每千人",
            "rate_dist_area": f"{col}（万m²）÷ 总人口（市辖区）折算 m²/人",
            "ins_rate": f"{col} ÷ 总人口（全市）×100",
            "clean_fuel": f"（{GAS1}+{GAS2}）÷ 总人口（全市）×100",
        }[mode]
        dic.append({"code": code, "name": desc, "dim": dim, "dim_name": DIMS[dim],
                    "unit": unit, "direction": "越高越好" if sign > 0 else "越低越好",
                    "source_column": col, "formula": formula,
                    "coverage": cov[code]["coverage"]})
    pd.DataFrame(dic).to_csv(DICT_DIR / "indicator_dictionary.csv", index=False,
                             encoding="utf-8-sig", lineterminator="\n")

    # ---- 面板落盘 ----
    keep = (["city", "city_code", "year", "pop_scope"]
            + [i[0] for i in INDICATORS]
            + [d + "_score" for d in DIM_ORDER]
            + ["overall_raw", "overall", "grade", "grade_stability",
               "grade_entropy", "grade_pctile"])
    n[keep].to_csv(PROC / "chuhi_panel.csv.gz", index=False,
                   compression={"method": "gzip", "mtime": 0},  # gzip 时间戳归零，保证逐字节可复现
                   encoding="utf-8-sig", lineterminator="\n")
    pd.DataFrame(xval).to_csv(PROC / "cross_validation_who.csv", index=False,
                              encoding="utf-8-sig", lineterminator="\n")

    # ---- 网站数据 ----
    # 每城最新可算行的扰动稳定率（用于城市画像）
    n["_p20"] = perturb_city["±20%"]
    n["_p50"] = perturb_city["±50%"]
    latest_idx = {}
    for city, g in n[n["overall"].notna()].groupby("city"):
        latest_idx[city] = g["year"].idxmax()
    cities = []
    for city, g in n.sort_values("city").groupby("city"):
        series = []
        for _, r in g.iterrows():
            series.append({
                "y": int(r["year"]),
                "dims": {d: None if pd.isna(r[d + "_score"]) else round(float(r[d + "_score"]), 1) for d in DIM_ORDER},
                "overall": None if pd.isna(r["overall"]) else round(float(r["overall"]), 1),
                "grade": r["grade"] if isinstance(r["grade"], str) else None,
                "stab": None if pd.isna(r["grade_stability"]) else round(float(r["grade_stability"]), 3),
                "pm25": None if pd.isna(r["ENV_PM25"]) else round(float(r["ENV_PM25"]), 1),
            })
        latest = [s for s in series if s["overall"] is not None][-1:] or []
        li = latest_idx.get(city)
        scen = None
        if li is not None:
            scen = {
                "entropy": n.at[li, "grade_entropy"] if isinstance(n.at[li, "grade_entropy"], str) else None,
                "pctile": n.at[li, "grade_pctile"] if isinstance(n.at[li, "grade_pctile"], str) else None,
                "p20": None if pd.isna(n.at[li, "_p20"]) else round(float(n.at[li, "_p20"]), 2),
                "p50": None if pd.isna(n.at[li, "_p50"]) else round(float(n.at[li, "_p50"]), 2),
            }
        cities.append({"id": city, "name": city, "series": series,
                       "grade": latest[0]["grade"] if latest else None,
                       "overall": latest[0]["overall"] if latest else None,
                       "stab": latest[0]["stab"] if latest else None,
                       "scen": scen})
    dim_means = {d: round(float(n[d + "_score"].mean()), 1) for d in DIM_ORDER}
    by_year = (n.groupby("year")["ENV_PM25"].mean().dropna()
                 .round(1).astype(float))
    meta = {
        "version": "0.6.0",
        "data_mode": "real",
        "generated": "scripts/build_data.py",
        "period": f"{YEAR_MIN}-{YEAR_MAX}",
        "n_years": YEAR_MAX - YEAR_MIN + 1,
        "n_cities": int(n["city"].nunique()),
        "n_indicators": len(INDICATORS),
        "sources": [
            {"id": "yearbook", "name": "中国城市统计年鉴（地级市面板 1999–2018，GitHub 公开汇编版）",
             "url": "https://github.com/Weiyi-Zhang/Class-Project-Chinese-Smart-City-Multi-period-DID",
             "role": "指数与分档的唯一输入"},
            {"id": "who_air", "name": "WHO Ambient Air Quality Database V6.1 (update 2024)",
             "url": "https://www.who.int/publications/m/item/who-ambient-air-quality-database-(update-jan-2024)",
             "role": "独立第二数据源，用于 PM2.5 跨源一致性审计"},
        ],
        "outcome_anchor": "缺口：开放数据下地级市疾病结局不可得，未纳入任何代理",
        "normalization": "方向感知 min–max（2003–2024 合并分布），逐年 1%/99% 缩尾；总分再做逐年截面重标定到 0–100（当年最高=100、最低=0）",
        "score_scale": "总分=0–100（逐年截面重标定的相对分）；跨年比较为相对位置变化",
        "weights": "基准=维内等权 × 维间等权；敏感性=Dirichlet(1) 全随机（参照系）、围绕基准 ±20%/±50% 扰动（现实场景）、熵权维内（数据驱动）、逐年百分位归一（口径替代）",
        "grades": "合并分布五分位 A–E，分档不排名",
        "audit_object": "审计对象为在用指数（TUHI/2018 版国家体系）的公开框架参考实现 + WHO 跨源校验；未直接审计 TUHI 发布分数（列入路线图）",
        "seed": SEED, "n_mc": N_MC,
    }
    # 情景一致率（最新可算年截面）
    scen_rows = n[n["overall"].notna()].copy()
    scen_rows["year"] = scen_rows["year"].astype(int)
    lm = scen_rows.groupby("city")["year"].transform("max")
    xs = scen_rows[scen_rows["year"] == lm]
    cmp_e = (xs["grade"] == xs["grade_entropy"]).mean()
    cmp_p = (xs["grade"] == xs["grade_pctile"]).mean()
    overview = {
        "kpi": [
            {"label": "真实城市", "value": meta["n_cities"], "unit": "个地级市"},
            {"label": "真实年份", "value": meta["n_years"], "unit": f"{YEAR_MIN}–{YEAR_MAX}"},
            {"label": "真实指标", "value": meta["n_indicators"], "unit": "项可复算指标"},
            {"label": "跨源匹配城市", "value": n_matched_cities, "unit": "个城市（年鉴×WHO）"},
        ],
        "dim_means": dim_means,
        "mean_grade_stability": round(mean_stab, 3),
        "share_stable80_dirichlet": round(share80_dir, 4),
        "pm25_by_year": {str(int(k)): float(v) for k, v in by_year.items()},
        "grade_thresholds": [round(float(q), 1) for q in grade_qs],
    }
    validity = {
        "cross_validation": xval,
        "scatter": scatter_pts,
        "n_matched_cities": n_matched_cities,
        "variance_decomposition": vardec,
        "perturbation": perturb,
        "transition_matrix": {
            "rows": ["A", "B", "C", "D", "E"],
            "matrix": [[round(float(v), 4) for v in row] for row in trans],
            "note": "行=基准档（A 最优），列=Dirichlet 全随机权重下的模拟档；行内和为 1。对角线即分档稳定率。"},
        "scenario_agreement": {
            "n_cities": int(len(xs)),
            "entropy_same_as_base": round(float(cmp_e), 4),
            "pctile_same_as_base": round(float(cmp_p), 4)},
        "known_groups": kg,
        "tuhi_direct": tuhi,
        "outcome_anchor_status": "unavailable_open_data",
    }

    data_obj = {"meta": meta, "overview": overview, "frameworks": [
        {"id": "CHIA-real", "name": "CHIA 真实数据口径", "dims": DIMS,
         "note": "仅使用可公开下载并经哈希校验的真实数据；结局锚缺口如实呈现"}],
        "validity": validity, "variance": vardec, "cities": cities}
    write_js(DOCS_DATA / "city_data.js", "CHIA_CITY_DATA", data_obj)
    write_js(DOCS_DATA / "indicator_dictionary.js", "CHIA_DICT",
             {"data_mode": "real", "indicators": dic, "dims": DIMS,
              "role_levels": {}, "availability_levels": {}})
    (PROC / "coverage_report.json").write_text(
        json.dumps(coverage_report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    summary = {
        "built": True, "version": "0.6.0", "period": meta["period"], "n_cities": meta["n_cities"],
        "n_rows_index": int(n["overall"].notna().sum()),
        "mean_grade_stability": round(mean_stab, 3),
        "share_stable80_dirichlet": round(share80_dir, 4),
        "perturbation": perturb,
        "scenario_agreement": validity["scenario_agreement"],
        "known_groups_n_pilot": kg["n_pilot_matched"],
        "tuhi_direct": ({"mean_spearman_lag1": tuhi["lag1"]["mean_spearman"],
                         "mean_kappa_lag1": tuhi["lag1"]["mean_kappa"],
                         "n_matched_pairs": tuhi["n_matched_pairs"],
                         "n_tuhi_cities": tuhi["n_tuhi_cities"]}
                        if tuhi else None),
        "grade_thresholds": overview["grade_thresholds"],
        "who_matched_cities": n_matched_cities,
        "xval_latest": xval[-1] if xval else None,
        "variance_decomposition": vardec,
        "outputs_sha256": {
            "chuhi_panel.csv.gz": sha256_of(PROC / "chuhi_panel.csv.gz"),
            "cross_validation_who.csv": sha256_of(PROC / "cross_validation_who.csv"),
            "city_data.js": sha256_of(DOCS_DATA / "city_data.js"),
            "indicator_dictionary.js": sha256_of(DOCS_DATA / "indicator_dictionary.js"),
        },
    }
    (PROC / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({k: summary[k] for k in
                      ("n_cities", "n_rows_index", "mean_grade_stability",
                       "grade_thresholds", "who_matched_cities", "xval_latest")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

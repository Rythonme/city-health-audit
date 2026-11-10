# -*- coding: utf-8 -*-
"""从《中国城市统计年鉴》2019–2025 卷分表 Excel 提取地级市面板。

- 输入：data/raw/yearbook_vols/{2019..2025}/*.xlsx（按统计表拆分）
- 输出：data/processed/yearbook_new_panel.csv（数据年 2018–2024，列名与
        旧 .dta 面板的源列对齐，便于 build_data.py 直接拼接）
        data/processed/overlap_audit_2018.csv（2019 卷 × 旧面板重叠年交叉审计）

用法：python scripts/extract_new_yearbook.py
仅依赖 pandas + 标准库。表定位按文件名关键词（各卷表号会变动），
列定位按中文表头关键词 + 全市/市辖区范围标签，不写死列号。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VOL_DIR = ROOT / "data" / "raw" / "yearbook_vols"
PROC = ROOT / "data" / "processed"
VOLS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
# vol Y 的统计数据年 = Y-1；但 2019 卷仅用于重叠年审计，拼接从 2019 数据年开始
DATA_YEAR = {v: v - 1 for v in VOLS}
MERGE_MIN_YEAR = 2019  # 数据年 >= 此值才进入正式面板

OLD_DTA = ROOT / "data" / "raw" / "china_city_statistical_yearbook_prefecture_1999_2018.dta"

# ---------------------------------------------------------------- 表定位（文件名关键词）
TABLES = {
    "pop": (["人口数", "人口及户数"], []),
    "gdp": (["地区生产总值"], ["构成"]),
    "wage": (["在岗职工人数及工资", "劳动力就业及收入"], []),
    "retail": (["社会消费品零售总额"], []),
    "air": (["细颗粒物年平均浓度", "空气质量状况"], []),
    "so2": (["二氧化硫"], []),
    "green": (["绿地面积"], []),
    "hosp": (["医院、床位和医生数"], []),
    "soc": (["社会保障主要指标"], []),
    "stu": (["学生数"], ["专任", "学校数"]),
    "culture": (["文化体育设施"], []),
    "muni": (["市政公用事业"], []),
    "bus": (["公共汽车", "城市交通"], []),
    "gas": (["煤气及液化石油气", "天然气及液化石油气", "天然气供应"], []),
}

# ---------------------------------------------------------------- 字段定位
# (输出名, 必含关键词, 排除关键词, 范围 city/dist/None, 序号选匹配)
FIELDS = {
    "pop": [
        ("pop_hj_city", ["户籍人口"], ["城镇"], "city"),
        ("pop_hj_dist", ["户籍人口"], ["城镇"], "dist"),
        ("pop_avg_city", ["年平均人口"], [], "city"),
        ("pop_avg_dist", ["年平均人口"], [], "dist"),
        ("pop_cz_city", ["常住人口"], ["城镇", "城镇化"], "city"),
        ("pop_cz_dist", ["常住人口"], ["城镇", "城镇化"], "dist"),
    ],
    "gdp": [("gdp_pc", ["人均地区生产总值"], [], "city")],
    "wage": [("wage", ["职工平均工资"], [], "city")],
    "retail": [("retail", ["社会消费品零售总额"], [], "city")],
    "air": [
        ("pm25", ["细颗粒物年平均浓度"], [], None),
        ("sewage", ["污水处理厂集中处理率"], [], None),
        ("waste", ["生活垃圾无害化处理率"], [], None),
    ],
    "so2": [("so2", ["工业二氧化硫排放量"], [], None)],
    "green": [
        ("green_area", ["绿地面积"], ["公园"], None),
        ("green_cover", ["建成区绿化覆盖率"], [], None),
    ],
    "hosp": [
        ("hosp_n", ["医院数"], ["床位"], "dist"),
        ("beds", ["医院床位数"], [], "dist"),
        ("docs", ["医师数"], [], "dist"),
    ],
    "soc": [
        ("pension", ["养老保险参保人数"], [], "city"),
        ("medical", ["医疗保险参保人数"], [], "city"),
        ("unemp", ["失业保险参保人数"], [], "city"),
    ],
    "stu": [("univ_stu", ["本专科"], [], "city")],
    "culture": [("lib_books", ["公共图书馆图书藏量"], [], "city")],
    "muni": [("road_area", ["城市道路面积"], [], "dist")],
    "bus": [("bus_n", ["营运车辆数"], ["出租"], "dist")],
}

# gas 表单独处理：两组「居民家庭用量」按列序取
GAS_SPECS = [
    ("gas_fam", ["供气总量"], ["液化"]),
    ("gas_fam2", ["居民家庭用量"], ["液化"]),
    ("lpg_fam", ["家庭用量"], []),
]

CITY_END = "市"
EXCLUDE_CITY = ("省", "自治区", "兵团", "合计", "总计", "单位", "农垦")


def _norm(s: str) -> str:
    """表头/城市名归一：清除所有空白（含 CRLF）、全角括号转半角。"""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    s = re.sub(r"\s+", "", str(s))
    s = s.replace("（", "(").replace("）", ")").replace(",", "")
    return s


def find_table(d: Path, key: str):
    pats, excl = TABLES[key]
    hits = [p for p in sorted(d.glob("*.xlsx"))
            if any(k in p.name for k in pats) and not any(e in p.name for e in excl)]
    # stu 特例：要「学生数（一）/在校学生数(一)」
    if key == "stu":
        hits = [p for p in hits if re.search(r"学生数[(（]一[)）]", p.name)]
    return hits[0] if hits else None


def parse_table(path: Path, specs):
    """解析一张分表：返回 {out_name: {city: value}} 与调试信息。

    specs: [(out_name, must_include, exclude, scope)]；gas 用 ordered 处理。
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    grid = df.values.tolist()
    ncol = max(len(r) for r in grid)
    grid = [r + [None] * (ncol - len(r)) for r in grid]

    # 1) 表头行：cell0 归一后恰为「城市」
    hr = None
    for i, row in enumerate(grid):
        if _norm(row[0]) == "城市":
            hr = i
            break
    if hr is None:
        return {}, f"no header row in {path.name}"

    # 2) 数据起始行：cell0 以「市」结尾（排除表头「城市」）
    dr = None
    for i in range(hr + 1, len(grid)):
        c0 = _norm(grid[i][0])
        if c0 == "城市":
            continue
        if c0.endswith(CITY_END) and not any(x in c0 for x in EXCLUDE_CITY):
            dr = i
            break
    if dr is None:
        return {}, f"no data rows in {path.name}"

    # 3) 列标签 = hr..dr-1 各行文本拼接
    labels = {}
    scopes = {}
    for c in range(2, ncol):
        parts = []
        for i in range(hr, dr):
            t = _norm(grid[i][c])
            if t:
                parts.append(t)
        lab = "".join(parts)
        labels[c] = lab
        if "市辖区" in lab or "Districtsunder" in lab or "Districtsund" in lab:
            scopes[c] = "dist"
        elif "全市" in lab or "TotalCity" in lab:
            scopes[c] = "city"
        else:
            scopes[c] = None

    # 4) 数据行
    rows = {}
    for i in range(dr, len(grid)):
        c0 = _norm(grid[i][0])
        if c0 == "城市":
            continue
        if not c0.endswith(CITY_END) or any(x in c0 for x in EXCLUDE_CITY):
            continue
        rows[c0] = i

    out, dbg = {}, []
    for spec in specs:
        if len(spec) == 4:
            name, must, excl, scope = spec
            cand = [c for c in range(2, ncol)
                    if all(k in labels[c] for k in must)
                    and not any(e in labels[c] for e in excl)
                    and (scope is None or scopes[c] == scope or scopes[c] is None)]
            if not cand and scope is not None:  # 宽容：无范围标签时回退
                cand = [c for c in range(2, ncol)
                        if all(k in labels[c] for k in must)
                        and not any(e in labels[c] for e in excl)]
            if not cand:
                dbg.append(f"{name}: NO MATCH")
                out[name] = {}
                continue
            col = cand[0]
            out[name] = {city: _num(grid[i][col]) for city, i in rows.items()}
        else:  # ordered (gas)
            name, must, excl = spec
            cand = [c for c in range(2, ncol)
                    if all(k in labels[c] for k in must)
                    and not any(e in labels[c] for e in excl)]
            if len(cand) < 1:
                dbg.append(f"{name}: NO MATCH")
                out[name] = {}
                continue
            col = cand[-1] if name == "lpg_fam" else cand[0]
            out[name] = {city: _num(grid[i][col]) for city, i in rows.items()}
    return out, "; ".join(dbg)


def _num(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v) if v != 0 else np.nan  # 0 值（如三沙市人口）按缺失处理，防止除零
    s = str(v).replace(",", "").strip()
    if s in ("", "-", "…", "...", "#N/A"):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def pick_pop(rec: dict, suffix: str = "city"):
    """按 户籍 > 常住 > 年平均 优先级选定分母（与旧面板「年末总人口=户籍」对齐），
    返回 (值, 口径标签)。suffix: 'city' | 'dist'。"""
    for base, tag in [("hj", "户籍"), ("cz", "常住"), ("avg", "年平均")]:
        v = rec.get(f"pop_{base}_{suffix}")
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            return v, tag
    return np.nan, "无"


def main() -> int:
    PROC.mkdir(parents=True, exist_ok=True)
    all_rows, log = [], []
    for vol in VOLS:
        d = VOL_DIR / str(vol)
        if not d.exists():
            log.append(f"vol {vol}: missing dir")
            continue
        parsed = {}
        for key in TABLES:
            p = find_table(d, key)
            if p is None:
                log.append(f"vol {vol} [{key}]: table not found")
                parsed[key] = ({}, f"table not found")
                continue
            if key == "gas":
                specs = GAS_SPECS
            else:
                specs = FIELDS[key]
            rec, dbg = parse_table(p, specs)
            parsed[key] = (rec, dbg)
            if dbg:
                log.append(f"vol {vol} [{key}] {p.name}: {dbg}")
            else:
                log.append(f"vol {vol} [{key}] {p.name}: ok ({len(rec) if isinstance(rec, dict) else 0})")

        # 以 pop 表的城市集合为骨架
        pop_rec = parsed["pop"][0]
        cities = set()
        for k, v in pop_rec.items():
            cities |= set(v.keys())
        year = DATA_YEAR[vol]
        for city in sorted(cities):
            row = {"city": city, "year": year, "vol": vol}
            for key, (rec, _) in parsed.items():
                for fname, series in rec.items():
                    row[fname] = series.get(city, np.nan)
            row["pop_used_city"], row["pop_scope_city"] = pick_pop(row, "city")
            row["pop_used_dist"], row["pop_scope_dist"] = pick_pop(row, "dist")
            all_rows.append(row)

    raw = pd.DataFrame(all_rows)
    out_csv = PROC / "yearbook_new_panel.csv"
    raw.to_csv(out_csv, index=False, encoding="utf-8-sig", lineterminator="\n")

    # ---------------------------------------------------------------- 重叠年审计（vol2019=数据2018 × 旧面板）
    old = pd.read_stata(OLD_DTA, convert_categoricals=False)
    old["城市"] = old["城市"].astype(str).str.strip()
    old18 = old[old["年份"] == 2018].set_index("城市")
    new18 = raw[raw["year"] == 2018].copy()
    new18["city"] = new18["city"].str.strip()
    new18 = new18.set_index("city")

    audit = []
    pairs = [
        ("pop_hj_city", "年末总人口_全市_万人", "户籍人口(全市) × 旧年末总人口"),
        ("pop_avg_city", "年末总人口_全市_万人", "年平均人口(全市) × 旧年末总人口"),
        ("gdp_pc", "人均地区生产总值_全市_元", None),
        ("wage", "职工平均工资_全市_元", None),
        ("retail", "社会消费品零售额_全市_万元", None),
        ("pm25", "可吸入细颗粒物年平均浓度_全市_微克每立方米", None),
        ("so2", "工业二氧化硫排放量_全市_吨", None),
        ("green_cover", "建成区绿化覆盖率_市辖区_百分比", None),
        ("green_area", "绿地面积_市辖区_公顷", None),
        ("sewage", "污水处理厂集中处理率_全市_百分比", None),
        ("waste", "生活垃圾无害化处理率_全市_百分比", None),
        ("hosp_n", "医院、卫生院数_市辖区_个", None),
        ("beds", "医院、卫生院床位数_市辖区_张", None),
        ("docs", "执业或助理医师数_市辖区_人", None),
        ("pension", "城镇职工基本养老保险参保人数_全市_人", None),
        ("medical", "城镇职工基本医疗保险参保人数_全市_人", None),
        ("unemp", "城镇职工失业保险参保人数_全市_人", None),
        ("lib_books", "公共图书馆图书藏量_全市_万册", None),
        ("road_area", "年末实有铺装道路面积_全市_万平方米", None),
        ("bus_n", "年末实有公共营运汽电车_全市_辆", None),
    ]
    for ncol, ocol, note in pairs:
        if ocol not in old18.columns:
            audit.append({"field": ncol, "old_col": ocol, "n": 0, "pearson_r": None,
                          "median_rel_diff": None, "note": "旧面板无此列"})
            continue
        joined = pd.DataFrame({"n": new18[ncol], "o": old18[ocol]}).dropna() if ncol in new18.columns else pd.DataFrame()
        if len(joined) < 10:
            audit.append({"field": ncol, "old_col": ocol, "n": len(joined), "pearson_r": None,
                          "median_rel_diff": None, "note": "重叠不足" + (f"；{note}" if note else "")})
            continue
        r = float(joined["n"].corr(joined["o"]))
        med = float(((joined["n"] - joined["o"]).abs() / joined["o"].abs().replace(0, np.nan)).median())
        audit.append({"field": ncol, "old_col": ocol, "n": len(joined), "pearson_r": round(r, 4),
                      "median_rel_diff": round(med, 4), "note": note or ""})
    audit_df = pd.DataFrame(audit)
    audit_csv = PROC / "overlap_audit_2018.csv"
    audit_df.to_csv(audit_csv, index=False, encoding="utf-8-sig", lineterminator="\n")

    print(f"[extract] rows={len(raw)} years={sorted(raw['year'].unique())} cities={raw['city'].nunique()}")
    print(audit_df.to_string(index=False))
    print("\n[log]")
    for l in log:
        print("  ", l)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""CI 语义可复现检查：重建产物 vs 已提交产物，按容差比对。

为什么不用 `git diff` 逐字节比对：不同 CPU 的 SIMD 求和顺序会产生
~1e-10 量级的浮点噪声，经归一化/重标定放大后落入显示位（如 41.4 vs
41.5），字节比对在跨平台下永远无法通过；而结构性的错误（陈旧产物、
口径变化、行序错乱）仍会被本检查以定量上限捕获并打印明细。

判定规则：
- 数值：|a-b| <= 0.1001（吸收 1 位小数显示翻转）或相对差 <= 1e-6；
- CSV 逐列：不匹配行占比 <= 0.1%（首条不符行随注解输出）；
- 字符串（档位字母等）：同上 0.1% 上限；行数/列/行序不一致直接 FAIL；
- build_summary 的 outputs_sha256 本身跨平台必然不同，不参与比对。

用法：python scripts/check_repro.py  （在仓库根目录，重建之后运行）
"""
import gzip
import io
import json
import subprocess
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    ("data/processed/chuhi_panel.csv.gz", "csv"),
    ("data/processed/cross_validation_who.csv", "csv"),
    ("data/processed/tuhi_direct_audit.csv", "csv"),
    ("data/processed/yearbook_new_panel.csv", "csv"),
    ("data/processed/overlap_audit_2018.csv", "csv"),
    ("data/processed/coverage_report.json", "json"),
    ("data/processed/build_summary.json", "summary"),
    ("dict/indicator_dictionary.csv", "csv"),
    ("docs/data/city_data.js", "js"),
    ("docs/data/indicator_dictionary.js", "js"),
]

RTOL = 1e-6
ABS_DISPLAY = 0.1001   # 吸收 1 位小数显示位翻转（跨 CPU 浮点噪声）
FRAC_ALLOW = 0.001     # 每列允许 0.1% 离散翻转


def committed_bytes(rel: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"HEAD:{rel}"], capture_output=True, check=True
    ).stdout


def load_df(data: bytes, rel: str) -> pd.DataFrame:
    if rel.endswith(".gz"):
        data = gzip.decompress(data)
    return pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")


def num_ok(a, b):
    if pd.isna(a) and pd.isna(b):
        return True
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    return abs(a - b) <= ABS_DISPLAY or np.isclose(a, b, rtol=RTOL, atol=1e-12)


def walk(a, b, path, diffs):
    """深度比对（JSON/JS）：收集至多 20 条差异明细。"""
    if len(diffs) >= 20:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                diffs.append(f"{path}.{k}: 仅一侧存在")
            else:
                walk(a[k], b[k], f"{path}.{k}", diffs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: 长度 {len(a)} vs {len(b)}")
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", diffs)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        if isinstance(a, int) and isinstance(b, int):
            if a != b:
                diffs.append(f"{path}: 整数 {a} vs {b}")
        elif not num_ok(a, b):
            diffs.append(f"{path}: {a} vs {b}")
    elif type(a) is not type(b) and a != b:
        diffs.append(f"{path}: 类型 {type(a).__name__} vs {type(b).__name__}")
    elif a != b and not (pd.isna(a) and pd.isna(b)):
        diffs.append(f"{path}: {a!r} vs {b!r}")


def check_pair(rel: str, kind: str) -> list:
    old = committed_bytes(rel)
    new = (ROOT / rel).read_bytes()

    if kind in ("json", "js"):
        if kind == "js":
            parse = lambda d: json.loads(
                d.decode("utf-8-sig").split("=", 1)[1].strip().rstrip(";"))
        else:
            parse = lambda d: json.loads(d.decode("utf-8-sig"))
        diffs = []
        walk(parse(old), parse(new), rel, diffs)
        return diffs

    if kind == "summary":
        a, b = json.loads(old.decode("utf-8-sig")), json.loads(new.decode("utf-8-sig"))
        a.pop("outputs_sha256", None), b.pop("outputs_sha256", None)
        diffs = []
        walk(a, b, rel, diffs)
        return diffs

    df_old, df_new = load_df(old, rel), load_df(new, rel)
    if list(df_old.columns) != list(df_new.columns):
        return [f"{rel}: 列不一致 {list(df_old.columns)[:6]}... vs {list(df_new.columns)[:6]}..."]
    if len(df_old) != len(df_new):
        return [f"{rel}: 行数 {len(df_old)} vs {len(df_new)}"]
    diffs = []
    allow = max(1, int(len(df_old) * FRAC_ALLOW))
    for col in df_old.columns:
        o, n = df_old[col], df_new[col]
        if pd.api.types.is_numeric_dtype(o) and pd.api.types.is_numeric_dtype(n):
            bad = ~np.isclose(o.astype(float), n.astype(float),
                              rtol=RTOL, atol=1e-12, equal_nan=True)
            bad |= ~(  # 数值容差外的显示位翻转
                (np.abs(np.nan_to_num(o.astype(float)) - np.nan_to_num(n.astype(float))) <= ABS_DISPLAY)
                | (o.isna() & n.isna()))
        else:
            bad = (o.astype(str) != n.astype(str)) & ~(o.isna() & n.isna())
        nbad = int(bad.sum())
        if nbad > allow:
            i = int(np.argmax(bad.to_numpy()))
            diffs.append(f"{rel}.{col}: {nbad}/{len(df_old)} 行不符（上限 {allow}），首例行{i}: {o.iloc[i]!r} vs {n.iloc[i]!r}")
    return diffs


def main() -> int:
    try:
        missing = [rel for rel, _ in TARGETS if not (ROOT / rel).exists()]
        if missing:
            print("::error::产物缺失: %s" % missing)
            return 1
        all_diffs = []
        for rel, kind in TARGETS:
            d = check_pair(rel, kind)
            print(("[%s] %s" % ("OK  " if not d else "DIFF", rel)) + ("" if not d else f"  ({len(d)} 项)"))
            all_diffs.extend(d)
        if all_diffs:
            print("\n=== 差异明细 ===")
            for d in all_diffs:
                print("::error::" + d.replace("\n", " ")[:180])
            return 1
        print("PASS：全部产物与已提交版本语义一致。")
        return 0
    except Exception:
        print("::error::检查器异常：" + traceback.format_exc()[-800:])
        return 1


if __name__ == "__main__":
    sys.exit(main())

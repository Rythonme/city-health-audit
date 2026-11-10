#!/usr/bin/env python3
"""CI 语义可复现检查：重建产物 vs 已提交产物，按容差比对。

为什么不用 `git diff` 逐字节比对：不同 CPU 的 SIMD 求和顺序会产生
~1e-15 量级的浮点噪声，经归一化放大后落入输出的小数位，字节比对在
跨平台下永远无法通过；而结构性的错误（陈旧产物、口径变化、行序错乱）
仍会被本检查捕获并打印明细。

用法：python scripts/check_repro.py  （在仓库根目录，重建之后运行）
"""
import gzip
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# (路径, 类型)——与 build_summary.outputs_sha256 覆盖的产物对齐，
# 另加 data/processed 的中间产物。
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

RTOL, ATOL = 1e-9, 1e-9


def committed_bytes(rel: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"HEAD:{rel}"], capture_output=True, check=True
    ).stdout


def load_df(data: bytes, rel: str) -> pd.DataFrame:
    if rel.endswith(".gz"):
        data = gzip.decompress(data)
    return pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")


def walk(a, b, path, diffs):
    """深度比对：数值用容差，其余精确。收集至多 20 条差异明细。"""
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
        if not np.isclose(a, b, rtol=RTOL, atol=ATOL, equal_nan=True):
            diffs.append(f"{path}: {a} vs {b}")
    elif type(a) is not type(b) and a != b:
        diffs.append(f"{path}: 类型 {type(a).__name__} vs {type(b).__name__}")
    elif a != b and not (pd.isna(a) and pd.isna(b)):
        diffs.append(f"{path}: {a!r} vs {b!r}")


def check_pair(rel: str, kind: str) -> list:
    """返回该产物的差异明细列表（空 = 通过）。"""
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

    # summary：除 outputs_sha256 外逐字段容差比对（sha 本身跨平台必然不同）
    if kind == "summary":
        a, b = json.loads(old.decode("utf-8-sig")), json.loads(new.decode("utf-8-sig"))
        a.pop("outputs_sha256", None), b.pop("outputs_sha256", None)
        diffs = []
        walk(a, b, rel, diffs)
        return diffs

    # csv：逐列比对
    df_old, df_new = load_df(old, rel), load_df(new, rel)
    if list(df_old.columns) != list(df_new.columns):
        return [f"{rel}: 列不一致 {list(df_old.columns)} vs {list(df_new.columns)}"]
    if len(df_old) != len(df_new):
        return [f"{rel}: 行数 {len(df_old)} vs {len(df_new)}"]
    diffs = []
    for col in df_old.columns:
        o, n = df_old[col], df_new[col]
        if pd.api.types.is_numeric_dtype(o) and pd.api.types.is_numeric_dtype(n):
            bad = ~np.isclose(o.astype(float), n.astype(float),
                              rtol=RTOL, atol=ATOL, equal_nan=True)
            if bad.any():
                i = int(np.argmax(bad.to_numpy()))
                diffs.append(f"{rel}.{col}: {len(bad)} 行不符，首例行{i} {o.iloc[i]} vs {n.iloc[i]}")
        else:
            bad = ~(o.astype(str) == n.astype(str))
            if bad.any():
                i = int(np.argmax(bad.to_numpy()))
                diffs.append(f"{rel}.{col}: {len(bad)} 行不符，首例行{i} {o.iloc[i]!r} vs {n.iloc[i]!r}")
    return diffs


def main() -> int:
    missing = [rel for rel, _ in TARGETS if not (ROOT / rel).exists()]
    if missing:
        print("FAIL：产物缺失", missing)
        return 1
    all_diffs = []
    for rel, kind in TARGETS:
        d = check_pair(rel, kind)
        tag = "OK  " if not d else "DIFF"
        print(f"[{tag}] {rel}" + ("" if not d else f"  ({len(d)} 项)"))
        all_diffs.extend(d)
    if all_diffs:
        print("\n=== 差异明细（至多 20 条）===")
        for d in all_diffs:
            print("::error::" + d.replace("\n", " ")[:180])
            print(" -", d)
        print("\n结论：重建产物与已提交产物存在超出容差的差异——"
              "若为少量边界档位/舍入差异，属已知跨平台浮点噪声；若为结构性差异，产物已陈旧或口径变更。")
        return 1
    print("PASS：全部 10 项产物与已提交版本语义一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

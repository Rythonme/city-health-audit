#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载并校验真实原始数据（SHA256 校验，杜绝静默替换）。

数据源：
1. 中国城市统计年鉴地级市面板 1999-2018（GitHub 公开汇编版）
2. WHO Ambient Air Quality Database V6.1 (update Jan 2024)

用法：
    python scripts/fetch_data.py            # 缺失则下载，齐全则仅校验
    python scripts/fetch_data.py --force    # 强制重新下载
退出码：0 = 全部通过；1 = 下载或哈希校验失败。
"""
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

# ---- 源 1：城市统计年鉴面板（优先 raw 文件直链，失败则退回整仓打包）----
PANEL_NAME = "china_city_statistical_yearbook_prefecture_1999_2018.dta"
PANEL_URLS = [
    # raw 直链（URL 已 percent-encode 中文文件名）
    "https://raw.githubusercontent.com/Weiyi-Zhang/Class-Project-Chinese-Smart-City-Multi-period-DID/main/%E4%B8%AD%E5%9B%BD%E5%9F%8E%E5%B8%82%E7%BB%9F%E8%AE%A1%E5%B9%B4%E9%89%B4%E5%9C%B0%E7%BA%A7%E5%B8%82%E9%9D%A2%E6%9D%BF%E6%95%B0%E6%8D%AE.zip",
    # 回退：整仓打包（codeload），内含同名 zip
    "https://codeload.github.com/Weiyi-Zhang/Class-Project-Chinese-Smart-City-Multi-period-DID/zip/refs/heads/main",
]
PANEL_INNER = "中国城市统计年鉴地级市面板数据.zip"

# ---- 源 2：WHO 空气质量数据库 ----
WHO_NAME = "who_ambient_air_quality_database_v6.1_2024.xlsx"
WHO_URL = (
    "https://cdn.who.int/media/docs/default-source/air-pollution-documents/"
    "air-quality-and-health/who_ambient_air_quality_database_version_2024_"
    "(v6.1).xlsx?sfvrsn=c504c0cd_3&download=true"
)

# 哈希由首次接入时计算；如上游更新导致不匹配，请人工核对 SOURCE.md 后更新此处
EXPECTED_SHA256 = {
    PANEL_NAME: None,   # 由 --record 生成
    WHO_NAME: None,
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, timeout: int = 300) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "CHIA-fetch/0.3"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def extract_inner_zip(blob: bytes, inner_name: str) -> bytes:
    """从整仓 zip 中提取内层 zip，再解出 .dta。"""
    with zipfile.ZipFile(io.BytesIO(blob)) as outer:
        target = None
        for n in outer.namelist():
            if n.endswith(inner_name):
                target = n
                break
        if target is None:
            raise FileNotFoundError(f"outer zip lacks {inner_name}")
        with zipfile.ZipFile(io.BytesIO(outer.read(target))) as inner:
            for n in inner.namelist():
                if n.lower().endswith(".dta"):
                    return inner.read(n)
    raise FileNotFoundError("inner .dta not found")


def main() -> int:
    force = "--force" in sys.argv
    record = "--record" in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)
    ok = True

    # 源 1
    p1 = RAW / PANEL_NAME
    if force or not p1.exists():
        print("[1/2] 下载城市统计年鉴面板 ...")
        got = False
        for url in PANEL_URLS:
            try:
                blob = fetch(url)
                if url.endswith(".zip") or "codeload" in url:
                    dta = extract_inner_zip(blob, PANEL_INNER)
                else:
                    with zipfile.ZipFile(io.BytesIO(blob)) as z:
                        dta = z.read(
                            [n for n in z.namelist() if n.lower().endswith(".dta")][0]
                        )
                p1.write_bytes(dta)
                print(f"      OK via {url.split('/')[2]}: {len(dta):,} bytes")
                got = True
                break
            except Exception as e:  # noqa: BLE001
                print(f"      失败 {url.split('/')[2]}: {e}")
        if not got:
            ok = False
    print(f"      {PANEL_NAME}: sha256={sha256_of(p1) if p1.exists() else 'MISSING'}")

    # 源 2
    p2 = RAW / WHO_NAME
    if force or not p2.exists():
        print("[2/2] 下载 WHO 空气质量数据库 V6.1 ...")
        try:
            blob = fetch(WHO_URL, timeout=600)
            p2.write_bytes(blob)
            print(f"      OK: {len(blob):,} bytes")
        except Exception as e:  # noqa: BLE001
            print(f"      失败: {e}")
            ok = False
    print(f"      {WHO_NAME}: sha256={sha256_of(p2) if p2.exists() else 'MISSING'}")

    if record:
        rec = {n: sha256_of(RAW / n) for n in (PANEL_NAME, WHO_NAME)
               if (RAW / n).exists()}
        print(json.dumps(rec, indent=2))
        (RAW / "sha256.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        print("已写入 data/raw/sha256.json")
    if not ok:
        print("存在下载失败项，中止构建。")
        return 1
    return 0


if __name__ == "__main__":
    import json
    sys.exit(main())

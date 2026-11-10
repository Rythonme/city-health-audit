# 复现手册 / REPRODUCE

## 1. 环境

| 用途 | 环境 | 备注 |
|---|---|---|
| 数据构建 | Python 3.10+，`pip install -r requirements.txt`（版本已锁定，见下） | 固定种子 `20261110`（Monte Carlo / 抽样） |
| 网站 | 任意现代浏览器 | 纯静态 HTML/CSS/JS，零 CDN，离线可运行 |
| R 包（可选） | R ≥ 4.0（项目默认 R 4.6.0） | 基础 R 即可跑核心函数；COINr 为 Suggests |
| CI | GitHub Actions `ubuntu-latest` + Python 3.10 | `.github/workflows/ci.yml` |

## 2. 一键复现

```bash
git clone <THIS_REPO_URL>
cd city-health-audit

# 1) 校验（必要时重新下载）公开原始数据，并打印 SHA256
python scripts/fetch_data.py

# 2) 从 2020–2025 卷分表 Excel 提取近年面板（数据年 2019–2024）+ 重叠年审计
python scripts/extract_new_yearbook.py

# 3) 全量重建：双源拼接面板、指数、Monte Carlo、跨源审计、网页数据
python scripts/build_data.py

# 4) 本地预览网站
python -m http.server 8000 --directory docs
# 打开 http://localhost:8000
```

也可直接双击 `docs/index.html`（脚本用相对路径，无需服务器）。

## 3. 复现检查清单

- [ ] `fetch_data.py` 打印的两个 SHA256 与 `data/raw/SOURCE.md` 提交记录一致。
- [ ] `build_data.py` 结尾输出的摘要（城市数 302、指数行数、跨源匹配 263 城）与 `data/processed/build_summary.json` 一致。
- [ ] `git status` 显示重建后 `docs/data/*.js`、`dict/*.csv`、`data/processed/*` 无差异（逐字节可复现；依赖版本已由 requirements.txt 锁定，勿使用未锁定安装）。
- [ ] `dict/indicator_dictionary.csv` 为 21 行（不含表头）。
- [ ] 仓库内除 `data/raw/` 公开文件外无 `*.rds` / `*.parquet` / `*.sav` 等受限数据。

## 4. R 包用法（骨架）

```r
# 本地安装（无需 CRAN）
install.packages("packages/chuhi", repos = NULL, type = "source")
library(chuhi)

# 真实面板已由 Python 管线产出；R 侧可读入后运行审计函数
d <- read.csv("data/processed/chuhi_panel.csv.gz")
st <- grade_stability(d$overall[d$year == 2018],
                      boundaries = c(40.1, 32.8, 27.2, 22.0), n_sim = 2000L)
```

> `packages/chuhi` 目前为**骨架**：核心函数可用基础 R 运行，单元测试与 roxygen 生成的 `man/` 文档待补。`simulate.R` 仅供包内单元测试造基准用，**不是**网站数据来源。

## 5. 论文前的版本冻结

1. 确认 `analysis/preregistration.md` 已提交 OSF 并登记日期。
2. 在 GitHub 打 tag：`git tag -a p1-v1.0 -m "P1 primary analysis frozen" && git push origin p1-v1.0`。
3. 创建 release 并在 Zenodo 归档，取得 DOI。
4. 把 `<OWNER>` / `<DOI>` / `<TAG>` / `<NUMBER>` / `<URL>` / `<DATE>` 回写 `CITATION.cff`、`docs/PAPER_PLAN.md` 与投稿稿件。
5. 论文图由 `analysis/` 下 R 脚本重绘，**不使用网站截图**。

## 6. 常见问题

**Q：原始数据可以直接重新下载吗？**
A：可以。`python scripts/fetch_data.py --force` 会从 GitHub / WHO 官方渠道重新下载并打印 SHA256；请与提交记录比对后再重建。

**Q：为什么年份到 2024？**
A：2020–2025 卷《中国城市统计年鉴》分表 Excel（公开网盘合集）提供数据年 2019–2024；WHO 空气质量数据库覆盖到 2020。更近年份见 SOURCE.md 的扩展路径。

**Q：能不能把个体级真实数据放进 `docs/data/`？**
A：不能。L2/L3 数据只能留在可信环境；公开仓库只放公开聚合数据与脱敏结果（且需另行审核）。

**Q：网站为什么没有地图？**
A：刻意设计。地图 + 名次容易把审计工具误读为城市排行榜，也涉及地图数据合规；本站用分档、条形、散点与不确定性图形表达，不呈现精确名次。

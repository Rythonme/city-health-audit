# chuhi — R 包骨架

`chuhi` 是 [CHIA 项目](../../README.md) 的 **COINr 上层效度审计层**，不是又一个通用复合指标包。

## 分工

| 能力 | 归属 |
|---|---|
| 指标筛选、标准化、赋权、聚合、Monte Carlo 全局敏感性、方差分解 | `COINr`（CRAN，JRC/OECD 支持） |
| 结局锚隔离、`S_det`/`S_mix` 配对对照、Δr / ΔRMSE、分档稳定性、字典与谱系 | `chuhi`（本包） |

## 安装与示例

```r
install.packages("packages/chuhi", repos = NULL, type = "source")
library(chuhi)

d <- simulate_benchmark()                       # 教学用长表
d$D1_next <- stats::ave(d$D1, d$city_id, FUN = function(v) c(v[-1], NA))
a <- d[stats::complete.cases(d), ]

res <- outcome_anchor_audit(
  score_det = a$score_det, score_mix = a$score_mix,
  outcome = a$D1, next_outcome = a$D1_next
)
res$delta_r        # 表面效度虚高
res$delta_rmse     # 增量预测价值

st <- grade_stability(d$score_det[d$year == 2016], boundaries = c(68, 62, 56, 50))
summary(st)

dict <- read_dictionary("dict/indicator_dictionary.csv")
nrow(dict)         # 36
```

## 当前状态（v0.1.0 骨架）

- [x] 核心函数用基础 R 可运行，无强制第三方依赖。
- [x] NAMESPACE / DESCRIPTION / LICENSE / roxygen 注释齐备。
- [ ] `man/*.Rd` 文档：待运行 `roxygen2::roxygenise()` 生成。
- [ ] `tests/testthat/`：待补单元测试（Δr 方向、CV 折分配、边界附近稳定性）。
- [ ] 真实 Monte Carlo：当前 `grade_stability()` 为简化扰动，真实分析须改为五类构造选择联合抽样（见 `docs/METHODS.md`）。
- [ ] `DESCRIPTION` 中维护者邮箱为占位，提交 JOSS/CRAN 前替换。

> 权威数据基准为 `scripts/build_data.py` 从真实公开数据构建的面板（见 `data/processed/`）；本 R 模拟器仅用于包内单元测试与教学示例。

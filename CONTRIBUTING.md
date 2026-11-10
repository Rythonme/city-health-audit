# 贡献指南 / Contributing

感谢参与 CHIA。这是一个**测量学审计**项目，最欢迎的贡献不是「再加一个指标」，而是让结论更可核查。

## 欢迎的 contribution

- 指标口径勘误（附来源与年份，尤其 2018 版国家体系与公开年报的口径变化）；
- 效度检验方法的改进（效标效度、交叉验证设计、响应效度、MAUP 稳健性）；
- 可复现性修复：种子、依赖版本、`--check` 一致性、CI 覆盖；
- 网站可访问性与「反排名误读」的设计改进；
- 中文系统检索（CNKI / 万方 / 维普）题录补充与 PRISMA-ScR 流程完善。

## 不接受的 contribution

- 在站内加入精确城市名次、名次地图或「最健康城市」类表述；
- 上传任何个体级疾病监测、EHR、医保结算或部门报送明细数据；
- 把演示口径的分档结果当作官方城市评价引用或转发；
- 用指数变动直接作因果宣称。

## 开发约定

1. 所有数据由 `scripts/fetch_data.py`（下载 + SHA256 校验）与 `scripts/build_data.py`（全量构建，固定种子 `20261110`）从真实公开数据生成；**不要手工编辑** `docs/data/*.js`、`dict/indicator_dictionary.csv` 与 `data/processed/*`。
2. 提交前运行：
   ```bash
   python scripts/fetch_data.py
   python scripts/build_data.py
   git status   # 确认重建无差异
   ```
3. 网站为纯静态、零 CDN 依赖；新增可视化请保持离线可运行，并沿用独立数据文件模式。
4. 论文相关改动须同步更新 `docs/PAPER_PLAN.md` 与 `analysis/preregistration.md`，并在发布前打代码 tag。
5. 提交信息用简体中文或英文均可，请说明「改了什么、为什么」。

## 报告问题

Issue 请包含：复现步骤、期望行为、实际行为、运行环境（OS / Python 或 R 版本）。若涉及数据口径，请附**公开可核验**的来源链接。

行为准则见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

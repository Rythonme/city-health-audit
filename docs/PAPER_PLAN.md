# SCI 布局 / PAPER PLAN

> 状态：**谋划中，文章后置**。用户决策（2026-11-10）：优先开发 GitHub 开源项目，按 SCI 布局谋划，后续再考虑文章。
> 本文件定义「仓库如何长成论文」，不定义「论文倒逼仓库」。所有题目、期刊、时间均为草案，未投稿、未注册。

## 0. 原则

1. **开源先行**：仓库版本、Zenodo DOI、OSF 预注册是论文的**输入证据**，不是论文发表后的附赠品。
2. **文章后置**：不因投稿节奏倒逼数据或结论；每篇投稿前必须有冻结的代码 tag + 预注册分析计划 + 数据可得性声明。
3. **一篇一问**：P1 回答「结局入分是否虚高效标效度」，P2 回答「工具是否可复现」，P3 回答「指数是否响应」。概念框架并入 P1 引言，不单独投（易被判 commentary）。
4. **不与在用的指数竞争**：全文统一「审计 / 互补」表述，不发布城市排名。

## 1. 论文矩阵

| | **P1 主论文** | **P2 工具 / 数据论文** | **P3 响应效度论文** |
|---|---|---|---|
| 工作标题 | *Does adding health outcomes to a healthy-city index inflate its validity? An outcome-anchored audit of in-use city health indices in China* | *CHIA: an open-source validation harness and real-data benchmark for auditing city health indices* | *Responsiveness of city health composite indices to a real-world policy shock* |
| 科学问题 | Q1（+Q2 部分） | 可复现性 / 方法学工具 | Q3 |
| **主要终点** | **Δr**（含/不含 D1 与同年独立结局的年龄标化相关差）与 **ΔRMSE**（对 t+1 年结局的 5 折交叉验证误差差） | 管线从原始数据逐字节复现、审计函数单元测试覆盖、跨源一致性审计（年鉴 × WHO）通过 | 分域指数对政策冲击的响应方向与时滞（检验**工具**，非检验政策） |
| 次要终点 | CFA 五维结构、已知组区分度、D1 权重 0→0.4 扫描的「虚高效应曲线」 | 指标字典元数据完整率、CI 通过率、网站可访问性 | D1 结局滞后 2–4 年、人口构成校正后的公平指标稳健性 |
| 设计 | 观察性测量学审计；同一城市 × 年份样本构造两套可比分数 | 方法学 / 软件论文；真实公开数据 + 单元测试 | 事件研究 + 合成控制 + 安慰剂（准实验） |
| 数据 | L1 公开真实数据（年鉴 302 城 × 2003–2018 + WHO；方法学演示）+ L2 聚合面板（主分析，含结局锚） | 仅 L1 | L2 + 政策文本编码 |
| 目标期刊（稳妥） | *Health & Place* / *International Journal of Health Geographics* / *BMC Public Health* / *BMC Medical Research Methodology* / *Public Health* | *Journal of Open Source Software* / *The R Journal* / *SoftwareX* / *Scientific Data* | *Journal of Urban Health* / *Cities* / *BMC Public Health* |
| 目标期刊（冲刺） | *Social Science & Medicine* / *The Lancet Regional Health – Western Pacific* | *Scientific Data*（若开放聚合数据集） | *Health & Place* |
| 前置条件 | 中文系统检索 + PRISMA-ScR、L2 结局集、OSF 预注册、代码 tag `p1-v1.0` | 仓库公开 + CI 通过 + Zenodo DOI（**最先具备条件**） | WP4 完成 + 政策文本双人编码 Kappa |
| 预计图表 | 3 图 2 表：Δr/RMSE 双轴时序、散点 + 回归、虚高效应曲线、体系对比表、效度汇总表 | 2 图 1 表：流程图、灵敏度曲线、函数清单表 | 3 图：事件研究图、分域滞后热图、安慰剂分布 |

> 投稿前按当年 JCR 分区与期刊 scope 复核；本表不标注影响因子数值。

## 2. 从仓库到论文的映射

| 仓库产物 | 对应论文 | 论文中的角色 |
|---|---|---|
| `scripts/fetch_data.py` + `scripts/build_data.py` + `data/raw/`、`data/processed/` | P1（方法学验证）、P2 | 真实公开数据基准与可复现管线；跨源一致性审计 |
| `dict/indicator_dictionary.csv` + `metadata_schema.yaml` | P1、P2 | 指标清单与元数据规范，附录可公开 |
| `packages/chuhi/R/audit.R`：`outcome_anchor_audit()` | **P1 核心分析** | 主要终点的计算实现 |
| `docs/index.html` 效度审计 / 不确定性视图 | P1 图 1–2、P2 图 1 | 图表原型（论文图由 R 脚本重绘，不直接截图） |
| `analysis/preregistration.md` | P1、P3 | OSF 预注册正文来源 |
| `docs/DATA_AVAILABILITY.md` | 全部 | Data availability statement 模板 |
| `.github/workflows/ci.yml` | P2 | 可复现性证据 |
| `PUBLISH.md` + Zenodo DOI | 全部 | Code availability statement |

## 3. 审稿人 6 问与备答

| 审稿人可能问 | 备答要点 |
|---|---|
| 「这不就是又一个城市健康指数吗？」 | 不发布新排名；审计对象是**在用的** 2018 版 / TUHI 式体系；主要终点是效标效度与循环论证后果，不是城市得分。 |
| 「COINr 已做 Monte Carlo 敏感性，为什么自己写包？」 | `chuhi` 是 COINr 上层**效度审计层**：标准化/聚合/敏感性调用 COINr，本包只补结局锚隔离、Δr/ΔRMSE 对照、响应效度、谱系与发布规范。README 明确分工并引用。 |
| 「ADI/SDI 早用死亡率作效标，新在哪？」 | 新在对象（城市级、跨部门、**政策在用**的健康城市指数）与新问题（结局入分的循环论证、指数响应效度）；附系统检索与 PRISMA-ScR 证明检索范围内未见。 |
| 「数据在哪？能复现吗？」 | 三层发布：L1 全公开（两份公开原始数据随仓库分发 + `fetch_data.py` 哈希校验 + `build_data.py` 全量重建 + Zenodo DOI）；L2 申请可得并给出伦理批件号与路径；L3 不公开并说明可信环境。 |
| 「疾病监测有上报强度偏倚，凭什么当金标准？」 | 元数据阈值（覆盖率、ICD 版本）、低质量指标不插补、监测系统变更情景敏感性；明确写入 limitation，并做阴性对照。 |
| 「与 TUHI / 2018 版什么关系？会不会重复？」 | 以它们的公开分数与指标清单为**输入**，补它们未做的外部效度检验；定位互补，全文不出现竞争性排名。 |

## 4. 数据可得性语句模板（投稿时按实填充）

**英文**
> All code, the indicator dictionary, the metadata schema and the real-data benchmark (China City Statistical Yearbook prefecture panel 2003–2018 and the WHO Ambient Air Quality Database V6.1, both distributed in the repository) are publicly available at `https://github.com/<OWNER>/city-health-audit` (MIT / CC BY 4.0 / ODbL), archived at Zenodo DOI `<DOI>` and frozen at tag `<TAG>`. De-identified city-level aggregate tables used for the primary analysis (including the outcome anchor) are available from the corresponding author under a data use agreement and ethics approval `<NUMBER>`; individual-level surveillance, EHR and claims data are not publicly available and were analysed only within a trusted environment. The analysis plan was preregistered at OSF `<URL>` on `<DATE>`.

**中文**
> 代码、指标字典、元数据规范与真实数据基准（《中国城市统计年鉴》地级市面板 2003–2018 与 WHO 环境空气质量数据库 V6.1，均随仓库分发）已公开于 `<仓库 URL>`（MIT / CC BY 4.0 / ODbL），Zenodo 归档 DOI `<DOI>`，投稿版本冻结于标签 `<TAG>`。主分析所用脱敏城市级聚合表（含结局锚）可在签署数据使用协议并提供伦理批件 `<编号>` 后向通讯作者申请；个体级监测、电子病历与医保数据不公开，仅在可信环境内分析。分析计划已于 `<日期>` 在 OSF 预注册 `<URL>`。

## 5. 预注册与版本冻结流程

1. 把 `analysis/preregistration.md` 提交 OSF，登记主要终点 Δr / ΔRMSE、分析计划、排除规则与敏感性分析。
2. P1 主分析定稿前打 tag `p1-v1.0`；tag 之后只修 bug，方法变更须写入预注册修订记录。
3. 每张论文图由 `analysis/` 下的 R 脚本重绘（不用网站截图），脚本与 tag 一并归档。
4. 阴性结果照实报告；若 Δr 不显著或增量预测价值为正，按预注册结论报告，不改写假说。

## 6. 时间线（对应 V1.1 工作包）

| 阶段 | 仓库状态 | 论文动作 |
|---|---|---|
| M0–M3 | 公开仓库 + 网站 + CI + 真实公开数据基准 | **无投稿**；仅完成 P2 素材 |
| M3–M6 | OSF 预注册草案、Zenodo DOI、中文系统检索 | P2 可择期先投（工具论文不依赖真实数据） |
| M6–M15 | L2 面板 + `chuhi` 主分析 + tag `p1-v1.0` | **P1 投稿** |
| M12–M24 | 政策文本编码 + 响应效度分析 | P3 投稿 |
| 滚动 | 年度基准审计简报（非论文） | 不改变主要终点 |

## 7. 明确不做

- 不投「中国城市健康度排行榜」类论文；
- 不把概念框架单独投成原创研究论文；
- 不用网站截图当论文图；
- 不在预注册前先跑主分析再挑终点；
- 不把演示口径的分档与跨源一致性数值当作正式效应量写进摘要。

## 8. 待补元数据（发布前替换占位）

`<OWNER>`、`<DOI>`、`<TAG>`、`<NUMBER>`（伦理批件）、`<URL>`（OSF）、`<DATE>`。作者、贡献者声明、利益冲突与基金信息尚未填写，投稿前按期刊要求补齐。

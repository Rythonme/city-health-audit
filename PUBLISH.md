# 公开自检与发布 / PUBLISH

> 用户决策（2026-11-10）：**先公开**。本文件是公开前的自检清单与一键发布命令。
> 仓库已按「公开」标准准备：**不含任何个体级/受限数据**；全部数值为真实公开数据计算结果。

## 1. 公开前自检（逐项打勾）

- [x] `docs/data/*.js` 含 `"data_mode":"real"` 标记，数值全部来自两份公开原始数据。
- [x] 原始数据来源、引用与 SHA256 已写入 `data/raw/SOURCE.md`；两份公开文件随仓库分发以保可复现。
- [x] 无个体级疾病监测、EHR、医保结算、部门报送明细；无姓名、身份证、手机号、住址等个人信息。
- [x] `.gitignore` 已排除 `data/private/`、`data/restricted/`、`*.parquet`、`*.sav`、`*.rds`（仅放行 `data/raw/` 两份公开文件）。
- [x] 许可证齐全：代码 MIT、文档/字典 CC BY 4.0、派生数据 ODbL 1.0（见 `LICENSE`）。
- [x] `CITATION.cff` 存在；`<OWNER>` 占位在首次发布前替换。
- [x] 不含城市精确名次、不含地图、不含「最健康城市」表述。
- [x] CI 可复现：`python scripts/build_data.py` 重建后无 git diff。
- [x] README 首段即为数据声明，明确「真实公开数据 + 不发布排名」。

**发布前请人工再跑一次**（在本机终端执行）：

```bash
cd city-health-audit
python scripts/fetch_data.py                 # 哈希校验原始数据
python scripts/build_data.py                 # 重建全部输出
git status                                   # 确认重建无差异
grep -R -n -E "身份证|手机号|patient_id|id_card|居民身份" --exclude-dir=.git . || echo "no PII-like strings"
find . -type f \( -name "*.rds" -o -name "*.parquet" -o -name "*.sav" \) -print
```

## 2. 首次发布命令（需用户在本机终端执行）

> WorkBuddy 会话不擅自向外部仓库推送。以下命令请在你自己的终端运行；GitHub Pages 源设为 `docs/`。

```bash
cd "F:/00在研项目/04_健康城市/04_开源项目/city-health-audit"

git init
git add .
git commit -m "Initial public release: CHIA measurement audit toolkit (real open data)"
git branch -M main
git remote add origin https://github.com/<OWNER>/city-health-audit.git
git push -u origin main
```

推送后在仓库 Settings → Pages → Build and deployment 选择 **Deploy from a branch / main / docs**，得到站点 `https://<OWNER>.github.io/city-health-audit/`。

## 3. 发布后三件事（按顺序）

1. **Zenodo 归档**：连接仓库 → 发布 release `v0.3.0` → 铸造 DOI，把 DOI 写入 `CITATION.cff` 与 `docs/REPRODUCE.md`。
2. **OSF 预注册**：把 `analysis/preregistration.md` 提交到 OSF，登记主要终点与分析计划，链接回写 `docs/PAPER_PLAN.md`。
3. **代码冻结**：每篇论文投稿前打 tag（如 `p1-v1.0`），并在论文 Data/Code availability 中给出 tag 与 Zenodo DOI。

## 4. 「先公开」策略的含义

- 仓库**不设私有期**：从第一版起即公开，社区可立即复核指标口径、原始数据与构建管线。
- 公开的是**方法、代码、字典、公开数据基准与审计结论的呈现方式**；个体级/受限数据永远走 L2/L3，不进入公开仓库。
- 公开顺序先于论文：仓库版本号、Zenodo DOI 与 OSF 预注册将成为论文可复现性与预注册的证据，而不是论文的附属品。

## 5. 后续真实数据接入的红线

任何 L2/L3 数据只能在**本地可信环境**处理，只导出 k-匿名后的聚合结果；若某指标（如疾病结局锚）需要受限数据才能补齐，必须在 `dict/` 登记为「可得性缺口」，**不得静默删除指标**（发布规范四条禁令之一）。

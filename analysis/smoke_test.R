# CHIA smoke test — 从仓库根目录运行：
#   Rscript analysis/smoke_test.R
# 验证 chuhi 核心函数在真实数据面板上能跑通。

source("packages/chuhi/R/audit.R")

d <- read.csv("data/processed/chuhi_panel.csv.gz", encoding = "UTF-8")
stopifnot(nrow(d) > 4000, length(unique(d$city)) >= 300)

# 真实面板的分档阈值（见 data/processed/build_summary.json）
qs <- c(42.2, 30.0, 23.1, 16.4)
st <- grade_stability(d$overall[d$year == 2018 & !is.na(d$overall)],
                      boundaries = qs, n_sim = 2000L)

dict <- read.csv("dict/indicator_dictionary.csv", encoding = "UTF-8")

cat("[chuhi smoke test · real data]\n")
cat("  panel rows       :", nrow(d), "\n")
cat("  cities           :", length(unique(d$city)), "\n")
cat("  index rows       :", sum(!is.na(d$overall)), "\n")
cat("  mean overall     :", round(mean(d$overall, na.rm = TRUE), 2), "\n")
cat("  stability range  :", paste(round(range(st), 3), collapse = " - "), "\n")
cat("  dictionary rows  :", nrow(dict), "\n")

stopifnot(
  sum(!is.na(d$overall)) > 4000L,
  all(st >= 0 & st <= 1),
  nrow(dict) == 21L
)
cat("  STATUS           : OK\n")

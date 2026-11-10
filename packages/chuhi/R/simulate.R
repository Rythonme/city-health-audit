# R/simulate.R — 包内单元测试与教学用简化模拟器
# 注意：权威数据基准是 scripts/build_data.py 构建的真实公开数据面板（data/processed/）。
# 本 R 模拟器仅供测试审计函数的方向性使用，不代表任何真实城市。

#' 生成教学用城市-年份长表
#'
#' @param n_cities 城市数。
#' @param years 年份向量。
#' @param seed 随机种子。
#' @param w 「结局入分」权重。
#' @return data.frame(city_id, year, D1, score_det, score_mix)
simulate_benchmark <- function(n_cities = 60L, years = 2016:2025,
                               seed = 20261110L, w = 0.20) {
  set.seed(seed)
  dim_off <- c(2.2, -1.4, 1.1, -2.6, 0.4)
  parts <- vector("list", n_cities * length(years))
  k <- 0L
  for (i in seq_len(n_cities)) {
    base <- 55 + 6 * stats::rnorm(1)
    for (ti in seq_along(years)) {
      t <- ti - 1L
      d <- base + dim_off + 0.5 * t + stats::rnorm(5, 0, 2)
      det <- mean(d)
      d1 <- 50 + 0.75 * (det - 55) + stats::rnorm(1, 0, 3)
      k <- k + 1L
      parts[[k]] <- data.frame(
        city_id = sprintf("C%03d", i),
        year = years[ti],
        D1 = round(d1, 2),
        score_det = round(det, 2),
        score_mix = round((1 - w) * det + w * d1, 2),
        stringsAsFactors = FALSE
      )
    }
  }
  do.call(rbind, parts)
}

#' 读取指标字典
#'
#' @param path indicator_dictionary.csv 路径。
#' @return data.frame
read_dictionary <- function(path) {
  stopifnot(length(path) == 1L, file.exists(path))
  utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE,
                  fileEncoding = "UTF-8")
}

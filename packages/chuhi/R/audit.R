# R/audit.R — 效度审计核心函数（基础 R 可运行）
# chuhi 只做「结局锚隔离 + 效标/预测效度对照 + 分档稳定性」，
# 标准化 / 赋权 / 聚合 / 全局敏感性交给 COINr。

#' 单个分数的效标效度与交叉验证误差
#'
#' @param score 指数分数向量。
#' @param outcome 同年 D1 结局锚向量。
#' @param next_outcome t+1 年 D1 结局锚向量；提供时计算 5 折 CV RMSE。
#' @param folds 交叉验证折数，默认 5。
#' @return list(r, r2, n, cv_rmse)
criterion_validity <- function(score, outcome, next_outcome = NULL, folds = 5L) {
  stopifnot(is.numeric(score), is.numeric(outcome), length(score) == length(outcome))
  keep <- is.finite(score) & is.finite(outcome)
  x <- score[keep]
  y <- outcome[keep]
  r <- suppressWarnings(stats::cor(x, y, method = "pearson"))
  res <- list(r = as.numeric(r), r2 = as.numeric(r^2), n = length(x), cv_rmse = NA_real_)
  if (!is.null(next_outcome)) {
    stopifnot(length(next_outcome) == length(score))
    target <- next_outcome[keep]
    res$cv_rmse <- .cv_rmse(x, target, as.integer(folds))
  }
  res
}

.cv_rmse <- function(x, y, folds) {
  n <- length(x)
  if (n < folds * 3L) return(NA_real_)
  fold <- (seq_len(n) - 1L) %% folds
  pred <- rep(NA_real_, n)
  for (f in seq_len(folds) - 1L) {
    tr <- fold != f
    te <- !tr
    if (sum(tr) < 3L || !any(te)) next
    dat <- data.frame(x = x[tr], y = y[tr])
    fit <- stats::lm(y ~ x, data = dat)
    pred[te] <- as.numeric(stats::predict(fit, newdata = data.frame(x = x[te])))
  }
  ok <- is.finite(pred) & is.finite(y)
  if (!any(ok)) return(NA_real_)
  sqrt(mean((pred[ok] - y[ok])^2))
}

#' 主要终点：含/不含 D1 两套分数的效标效度对照
#'
#' Δr > 0 而 ΔRMSE <= 0 表示「结局入分」制造了表面效度，
#' 却没有带来对独立/未来结局的增量预测价值。
#'
#' @param score_det 决定因素层分数（D1 不参与）。
#' @param score_mix 复现现行做法的分数（含 D1）。
#' @param outcome 同年 D1 结局锚。
#' @param next_outcome t+1 年 D1 结局锚。
#' @param folds CV 折数。
#' @param n_boot Δr 的 Bootstrap 次数。
#' @param seed 随机种子。
#' @return list(r_det, r_mix, delta_r, ci_delta_r, cv_rmse_det, cv_rmse_mix, delta_rmse, n)
outcome_anchor_audit <- function(score_det, score_mix, outcome, next_outcome,
                                folds = 5L, n_boot = 1000L, seed = 20261110L) {
  stopifnot(is.numeric(score_det), is.numeric(score_mix),
            length(score_det) == length(score_mix),
            length(score_det) == length(outcome),
            length(score_det) == length(next_outcome))
  keep <- is.finite(score_det) & is.finite(score_mix) &
    is.finite(outcome) & is.finite(next_outcome)
  a <- criterion_validity(score_det[keep], outcome[keep], next_outcome[keep], folds)
  b <- criterion_validity(score_mix[keep], outcome[keep], next_outcome[keep], folds)
  delta_r <- b$r - a$r
  delta_rmse <- a$cv_rmse - b$cv_rmse

  if (!is.null(seed)) set.seed(seed)
  n <- sum(keep)
  sd_ <- score_det[keep]
  sm_ <- score_mix[keep]
  oc_ <- outcome[keep]
  bs <- replicate(n_boot, {
    i <- sample.int(n, n, replace = TRUE)
    if (length(unique(sd_[i])) < 2L || length(unique(oc_[i])) < 2L) return(NA_real_)
    suppressWarnings(stats::cor(sm_[i], oc_[i]) - stats::cor(sd_[i], oc_[i]))
  })
  bs <- bs[is.finite(bs)]
  ci <- if (length(bs) > 20L) as.numeric(stats::quantile(bs, c(0.025, 0.975))) else c(NA_real_, NA_real_)

  list(
    r_det = a$r, r_mix = b$r, delta_r = delta_r,
    ci_delta_r = ci, n_boot_used = length(bs),
    cv_rmse_det = a$cv_rmse, cv_rmse_mix = b$cv_rmse,
    delta_rmse = delta_rmse, n = a$n
  )
}

#' Monte Carlo 分档稳定性
#'
#' 对分数施加构造选择扰动，统计每城档位保持不变的比例。
#' 真实分析应改为对权重/标准化/聚合/插补/指标集联合抽样（见 METHODS.md）。
#'
#' @param score 分数向量。
#' @param boundaries 档位下界（降序或任意顺序均可），如 c(68, 62, 56, 50)。
#' @param n_sim 模拟次数。
#' @param sd 扰动标准差。
#' @param seed 随机种子。
#' @return 每城分档稳定性（0–1）向量
grade_stability <- function(score, boundaries, n_sim = 10000L,
                            sd = 1.2, seed = 20261110L) {
  stopifnot(is.numeric(score), is.numeric(boundaries), length(boundaries) > 0L)
  b <- sort(boundaries, decreasing = TRUE)
  grade <- function(v) vapply(v, function(z) sum(z < b) + 1L, integer(1L))
  base <- grade(score)
  if (!is.null(seed)) set.seed(seed)
  changed <- integer(length(score))
  for (k in seq_len(n_sim)) {
    changed <- changed + as.integer(grade(score + stats::rnorm(length(score), 0, sd)) != base)
  }
  1 - changed / n_sim
}

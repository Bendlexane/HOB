set.seed(123)

n_true <- 500; break_at <- 251
mu_before <- 2.5; mu_after <- 1.8; sigma_true <- 0.4

T <- c(rlnorm(break_at - 1,          meanlog = mu_before, sdlog = sigma_true),
       rlnorm(n_true - break_at + 1,  meanlog = mu_after,  sdlog = sigma_true))
y <- log(T)

true_ref <- c(rep(exp(mu_before), break_at - 1),
              rep(exp(mu_after),  n_true - break_at + 1))

# Deliberately wrong PERT (ML=100 vs true ~6-12) to stress-test robustness.
# Motivation: kappa0=0.5 chosen because with kappa0>=2 the model stays anchored
# to the wrong prior for 20-30 projects. See VAULT_ARCHITECTURE.md sec. 30.
O <- 8; ML <- 100; P <- 150
mu_pert   <- (O + 4*ML + P) / 6
var_pert  <- ((P - O)/6)^2
sigma0_sq <- log(1 + var_pert / mu_pert^2)
mu0    <- log(mu_pert) - 0.5 * sigma0_sq
kappa0 <- 0.5; a0 <- 3; b0 <- sigma0_sq * (a0 - 1)

# -----------------------------
# BATCH update (Full Bayes / Window)
# -----------------------------

update_nig_batch <- function(y_obs, m0, k0, a0, b0) {
  n     <- length(y_obs)
  y_bar <- mean(y_obs)
  S     <- sum((y_obs - y_bar)^2)
  kn    <- k0 + n
  list(m = (k0 * m0 + n * y_bar) / kn,
       k = kn,
       a = a0 + n / 2,
       b = b0 + 0.5 * S + (k0 * n / (2 * kn)) * (y_bar - m0)^2)
}

# -----------------------------
# DISCOUNTED recursive update
# Effective sample size saturates at 1/(1-rho).
# -----------------------------

update_nig_discount <- function(y_new, m_prev, k_prev, a_prev, b_prev, rho) {
  k_disc <- rho * k_prev
  kn     <- k_disc + 1
  mn     <- (k_disc * m_prev + y_new) / kn
  an     <- rho * a_prev + 0.5
  bn     <- rho * b_prev + (k_disc / (2 * kn)) * (y_new - m_prev)^2
  list(m = mn, k = kn, a = an, b = bn)
}

pred_quantiles <- function(post) {
  scale <- sqrt(post$b * (post$k + 1) / (post$a * post$k))
  q     <- qt(c(0.1, 0.5, 0.9), df = 2 * post$a)
  list(p10 = exp(post$m + scale * q[1]),
       med = exp(post$m),
       p90 = exp(post$m + scale * q[3]))
}

K   <- 10
rho <- 0.9   # effective sample size 1/(1-rho) = 10, comparable with K

full_med <- full_p10 <- full_p90 <- rep(NA_real_, n_true)
win_med  <- win_p10  <- win_p90  <- rep(NA_real_, n_true)
dis_med  <- dis_p10  <- dis_p90  <- rep(NA_real_, n_true)

dm <- mu0; dk <- kappa0; da <- a0; db <- b0

for (i in 2:n_true) {
  obs <- y[1:(i - 1)]

  pf <- pred_quantiles(update_nig_batch(obs, mu0, kappa0, a0, b0))
  full_med[i] <- pf$med; full_p10[i] <- pf$p10; full_p90[i] <- pf$p90

  pw <- pred_quantiles(update_nig_batch(tail(obs, K), mu0, kappa0, a0, b0))
  win_med[i] <- pw$med; win_p10[i] <- pw$p10; win_p90[i] <- pw$p90

  disc <- update_nig_discount(y[i - 1], dm, dk, da, db, rho)
  dm <- disc$m; dk <- disc$k; da <- disc$a; db <- disc$b
  pd <- pred_quantiles(disc)
  dis_med[i] <- pd$med; dis_p10[i] <- pd$p10; dis_p90[i] <- pd$p90
}

# -----------------------------
# PLOT
# -----------------------------

ylim_range <- c(0, quantile(T, 0.97))

methods <- list(
  list(med = full_med, p10 = full_p10, p90 = full_p90,
       col_med = "blue",       col_band = "lightblue",
       title = "Full Bayesian"),
  list(med = win_med, p10 = win_p10, p90 = win_p90,
       col_med = "darkorange",  col_band = "moccasin",
       title = paste0("Sliding window (K=", K, ")")),
  list(med = dis_med, p10 = dis_p10, p90 = dis_p90,
       col_med = "darkgreen",   col_band = "palegreen",
       title = paste0("Discounted (rho=", rho, ", n_eff~", round(1/(1-rho)), ")"))
)

par(mfrow = c(1, 3), mar = c(4, 4, 3, 1))
for (m in methods) {
  plot(T, pch = 16, cex = 0.35, col = "gray75",
       ylim = ylim_range, xlab = "Projects observed",
       ylab = "Duration (days)", main = m$title)
  abline(v = break_at, col = "gray40", lty = 3)
  polygon(c(seq_along(m$p90), rev(seq_along(m$p10))),
          c(m$p90, rev(m$p10)), col = m$col_band, border = NA)
  lines(m$med,    col = m$col_med, lwd = 2)
  lines(true_ref, col = "black",   lwd = 1.5, lty = 2)
  legend("topright",
         legend = c("True median", "Posterior median", "p10-p90"),
         col = c("black", m$col_med, m$col_band),
         lty = c(2,1,NA), pch = c(NA,NA,15),
         lwd = c(1.5,2,NA), pt.cex = 1.5, cex = 0.7)
}
par(mfrow = c(1, 1))

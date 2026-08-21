"""Bayesian posterior math for per-phase duration prediction.

Model
-----
For each (role, phase) cell, durations D in calendar days are modelled as
log-Normal:

    Y_i = log D_i  ~  N(mu, sigma^2)
    sigma^2        ~  InvGamma(a_0, b_0)
    mu | sigma^2   ~  N(mu_0, sigma^2 / kappa_0)

The prior is elicited via Beta-PERT three-point estimates (O, ML, P) per cell,
mapped to log-Normal hyperparameters by moment matching. Posterior is updated
in closed form (Normal-Inverse-Gamma is conjugate to a Normal likelihood with
unknown mean and variance). Posterior predictive is a location-scale Student-t.

References
----------
Kim, B.-c., & Reinschmidt, K. F. (2009). Probabilistic Forecasting of Project
Duration Using Bayesian Inference and the Beta Distribution. Journal of
Construction Engineering and Management, 135(3), 178-186. (Beta-PERT elicitation
and the prior/data balance idea are taken from this paper.)

Murphy, K. P. (2007). Conjugate Bayesian analysis of the Gaussian distribution.
Technical report, UBC. (Standard NIG conjugate update formulas.)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from scipy.stats import t as student_t


# ---------------------------------------------------------------------------
# Prior elicitation: Beta-PERT (O, ML, P) -> log-Normal hyperparameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BetaPert:
    O: float   # optimistic   (~p10 of duration in days)
    ML: float  # most likely  (mode)
    P: float   # pessimistic  (~p90)

    def __post_init__(self) -> None:
        if not (self.O <= self.ML <= self.P):
            raise ValueError(f"Require O <= ML <= P, got ({self.O}, {self.ML}, {self.P})")
        if self.O <= 0:
            raise ValueError(f"O must be positive, got {self.O}")

    @property
    def mean(self) -> float:
        return (self.O + 4 * self.ML + self.P) / 6

    @property
    def variance(self) -> float:
        return ((self.P - self.O) / 6) ** 2


@dataclass(frozen=True)
class NIGPrior:
    """Normal-Inverse-Gamma hyperparameters on (mu, sigma^2)."""
    mu_0: float
    kappa_0: float
    a_0: float
    b_0: float

    @classmethod
    def from_beta_pert(
        cls,
        bp: BetaPert,
        kappa_0: float = 0.5,
        a_0: float = 3.0,
    ) -> "NIGPrior":
        """Moment-match Beta-PERT to log-Normal, then build NIG prior.

        b_0 is set so that the prior mean of sigma^2 equals the elicited
        log-Normal variance: E[sigma^2] = b_0 / (a_0 - 1) = sigma_0^2.
        """
        mean = bp.mean
        var = bp.variance
        sigma_0_sq = math.log(1 + var / (mean ** 2))
        mu_0 = math.log(mean) - 0.5 * sigma_0_sq
        b_0 = sigma_0_sq * (a_0 - 1)
        return cls(mu_0=mu_0, kappa_0=kappa_0, a_0=a_0, b_0=b_0)


# ---------------------------------------------------------------------------
# Posterior update: NIG conjugate to Normal likelihood
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NIGPosterior:
    """Posterior NIG hyperparameters after observing n log-durations."""
    mu_n: float
    kappa_n: float
    a_n: float
    b_n: float
    n: int

    @classmethod
    def from_observations(
        cls,
        prior: NIGPrior,
        durations_days: Sequence[float],
    ) -> "NIGPosterior":
        """Conjugate update (Murphy 2007, eqs. 85-89).

        Parameters
        ----------
        prior
            Prior NIG hyperparameters.
        durations_days
            Observed phase durations in calendar days. Empty sequence returns
            the prior unchanged (n=0).
        """
        n = len(durations_days)
        if n == 0:
            return cls(prior.mu_0, prior.kappa_0, prior.a_0, prior.b_0, 0)

        y = [math.log(d) for d in durations_days]
        ybar = sum(y) / n
        ss = sum((yi - ybar) ** 2 for yi in y)

        kappa_n = prior.kappa_0 + n
        mu_n = (prior.kappa_0 * prior.mu_0 + n * ybar) / kappa_n
        a_n = prior.a_0 + n / 2
        b_n = (
            prior.b_0
            + 0.5 * ss
            + (prior.kappa_0 * n * (ybar - prior.mu_0) ** 2) / (2 * kappa_n)
        )
        return cls(mu_n=mu_n, kappa_n=kappa_n, a_n=a_n, b_n=b_n, n=n)


# ---------------------------------------------------------------------------
# Posterior predictive: location-scale Student-t on log scale
# ---------------------------------------------------------------------------


def predictive_quantile(post: NIGPosterior, q: float) -> float:
    """Posterior predictive quantile of duration in calendar days.

    Y* ~ t_{2 a_n}(mu_n, b_n (kappa_n + 1) / (a_n kappa_n))
    D* = exp(Y*)
    """
    df = 2 * post.a_n
    scale_sq = post.b_n * (post.kappa_n + 1) / (post.a_n * post.kappa_n)
    log_q = student_t.ppf(q, df=df, loc=post.mu_n, scale=math.sqrt(scale_sq))
    return math.exp(log_q)


def predictive_summary(post: NIGPosterior) -> dict:
    """Standard summary: p10, p50 (median), p90 of duration in days, plus n."""
    return {
        "n": post.n,
        "mu_n": round(post.mu_n, 4),
        "kappa_n": round(post.kappa_n, 4),
        "a_n": round(post.a_n, 4),
        "b_n": round(post.b_n, 6),
        "p10_days": round(predictive_quantile(post, 0.10)),
        "p50_days": round(predictive_quantile(post, 0.50)),
        "p90_days": round(predictive_quantile(post, 0.90)),
    }


# ---------------------------------------------------------------------------
# Convenience: full pipeline from priors.json layout
# ---------------------------------------------------------------------------


def cell_summary(
    prior_pert: dict,
    durations_days: Sequence[float],
    kappa_0: float = 0.5,
    a_0: float = 3.0,
) -> dict:
    """Take a single cell's {O, ML, P} and observed durations, return summary."""
    bp = BetaPert(O=prior_pert["O"], ML=prior_pert["ML"], P=prior_pert["P"])
    prior = NIGPrior.from_beta_pert(bp, kappa_0=kappa_0, a_0=a_0)
    post = NIGPosterior.from_observations(prior, durations_days)
    return predictive_summary(post)

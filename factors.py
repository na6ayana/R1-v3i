"""Factor calculation, ranking and monthly signal construction."""
import numpy as np
import pandas as pd

import config


def momentum(close: pd.DataFrame, window=config.MOMENTUM_WINDOW, skip=config.MOMENTUM_SKIP) -> pd.DataFrame:
    """"12-1" momentum: rate of change over `window` days, ending `skip` days
    ago rather than today.

    A plain single-window ROC over a short (~1-month) lookback measures
    short-term reversal, not continuation -- that's the old 22-day formula,
    which tested at t=-0.02 (indistinguishable from noise). Skipping the most
    recent `skip` days (default 21, ~1 month) excludes exactly the part of
    the price history where reversal dominates, isolating the longer-horizon
    continuation effect the "momentum" factor is actually meant to capture.
    """
    return (close.shift(skip) - close.shift(skip + window)) / close.shift(skip + window)


def yang_zhang_volatility(open_, high, low, close, window=config.VOLATILITY_WINDOW, annualize=True) -> pd.DataFrame:
    """Yang-Zhang volatility estimator, rolling over `window` days, per asset.

    Combines overnight (close->open) variance, open->close variance and the
    Rogers-Satchell drift-independent estimator:
        YZ_var = Vo + k*Vc + (1-k)*Vrs
        k = 0.34 / (1.34 + (n+1)/(n-1))
    """
    n = window
    k = 0.34 / (1.34 + (n + 1) / (n - 1))

    log_oc = np.log(open_ / close.shift(1))       # overnight return
    log_co = np.log(close / open_)                 # open-to-close return
    log_ho = np.log(high / open_)
    log_lo = np.log(low / open_)
    log_hc = np.log(high / close)
    log_lc = np.log(low / close)
    rs = log_ho * log_hc + log_lo * log_lc          # Rogers-Satchell daily term

    vo = log_oc.rolling(n).var(ddof=1)
    vc = log_co.rolling(n).var(ddof=1)
    vrs = rs.rolling(n).mean()

    yz_var = vo + k * vc + (1 - k) * vrs
    yz_var = yz_var.clip(lower=0)  # numerical safety, variance can't be negative
    yz_vol = np.sqrt(yz_var)
    if annualize:
        yz_vol = yz_vol * np.sqrt(252)
    return yz_vol


def downside_deviation(close: pd.DataFrame, window=config.VOLATILITY_WINDOW, annualize=True) -> pd.DataFrame:
    """Downside deviation: like volatility, but only penalizes down-moves.

    Semi-deviation of daily returns below 0, rolling over `window` days:
    sqrt(mean(min(return, 0)^2)). Yang-Zhang volatility (the other option
    here) treats a stock's big UP days as just as "risky" as big down days,
    since it's a two-sided range/variance estimator -- but investors mainly
    care about downside risk, not upside variance. A stock with big rallies
    but calm drawdowns would look volatile to Yang-Zhang while looking safe
    here, which is a materially different ranking in names with skewed
    return distributions (common among the higher-beta/distressed names in
    this universe).

    Uses close-to-close returns only (not the full OHLC range Yang-Zhang
    uses) since "downside" needs a signed daily return to classify a day as
    up or down in the first place -- a range-based estimator has no sign.
    """
    daily_return = close.pct_change(fill_method=None)
    downside = daily_return.clip(upper=0)
    dd = np.sqrt((downside ** 2).rolling(window).mean())
    if annualize:
        dd = dd * np.sqrt(252)
    return dd


def volume_confirmation(close: pd.DataFrame, volume: pd.DataFrame,
                         fast=config.VOLUME_FAST, slow=config.VOLUME_SLOW) -> pd.DataFrame:
    """Price-aware volume confirmation: is buying pressure accelerating?

    The original formula (Volume.rolling(fast).mean() / Volume.rolling(slow).mean())
    had two problems:
      1. Price-blind: it only measures whether TURNOVER is rising, not whether
         that volume is happening on up-days or down-days -- a volume spike on
         a crash counts identically to one on a rally. "Confirmation" should
         mean volume is backing the price move, not just that turnover is up.
      2. Overlapping windows: the fast (10-day) window is a strict subset of
         the slow (22-day) window, so the ratio partly compares a number to
         itself, damping and autocorrelating the signal.

    Fixed here with a price-aware, non-overlapping two-window design:
      - Each day is signed by that day's return direction (+1 up, -1 down,
        0 flat), giving signed volume = Volume * sign(return).
      - `recent_ratio` = net signed volume / total volume over the most
        recent `fast` days -- in [-1, 1], the fraction of recent turnover
        that was "buying" vs "selling" volume (a money-flow-style measure).
      - `prior_ratio` is the same measure over the `slow - fast` days
        immediately BEFORE the recent window -- adjacent, not overlapping.
      - VC = recent_ratio - prior_ratio: is buying pressure intensifying
        relative to just before, rather than merely "is volume elevated."
    """
    daily_return = close.pct_change(fill_method=None)
    signed_volume = volume * np.sign(daily_return)

    recent_signed = signed_volume.rolling(fast).sum()
    recent_total = volume.rolling(fast).sum()
    recent_ratio = recent_signed / recent_total

    prior_window = slow - fast
    prior_signed = signed_volume.shift(fast).rolling(prior_window).sum()
    prior_total = volume.shift(fast).rolling(prior_window).sum()
    prior_ratio = prior_signed / prior_total

    return recent_ratio - prior_ratio


def cross_sectional_ranks(m: pd.DataFrame, v: pd.DataFrame, vc: pd.DataFrame):
    """Rank each factor cross-sectionally (across assets) on each date.

    - Rank_of_M: highest momentum -> highest numeric rank (ascending value order)
    - Rank_of_V: lowest volatility -> highest numeric rank (descending value order)
    - Rank_of_VC: highest volume confirmation -> highest numeric rank (ascending value order)
    """
    rank_m = m.rank(axis=1, ascending=True, method="average")
    rank_v = v.rank(axis=1, ascending=False, method="average")
    rank_vc = vc.rank(axis=1, ascending=False, method="average")
    return rank_m, rank_v, rank_vc


def total_rank_daily(m: pd.DataFrame, v: pd.DataFrame, vc: pd.DataFrame) -> pd.DataFrame:
    rank_m, rank_v, rank_vc = cross_sectional_ranks(m, v, vc)
    total = config.W1 * rank_m + config.W2 * rank_v + config.W3 * rank_vc + m / config.X
    return total


def resample_total_rank(total_rank_d: pd.DataFrame, freq=config.REBALANCE_FREQ) -> pd.DataFrame:
    """Total_Rank is computed daily but the *signal* is the last value at
    each rebalance-period end (`freq`: "ME" monthly, "QE" quarterly, etc)."""
    return total_rank_d.resample(freq).last()


def hysteresis_membership(rebalance_rank: pd.DataFrame, top_n=config.TOP_N,
                           buffer=config.HYSTERESIS_BUFFER) -> pd.DataFrame:
    """Stateful buffer-zone membership selection, evaluated sequentially
    over the rebalance dates (this one is NOT independent row-by-row, unlike
    a plain top-N pick, since it needs to know what was already held).

    A NEW asset must rank in the top `top_n` to be added; an asset ALREADY
    held is only dropped once its rank falls outside the top
    `top_n + buffer`. This is the standard hysteresis rule real index
    committees (S&P, Russell, etc) use to damp reconstitution churn from
    noisy rank jitter right around the cutoff -- without it, a marginal rank
    swap at the boundary forces a full sell/buy round-trip even when the
    incoming pick isn't meaningfully better than what's already held.

    Portfolio size is kept fixed at `top_n`: if more than `top_n` retained
    (already-held, still-within-buffer) assets exist in a given period, the
    worst-ranked of them are trimmed back out before filling any new slots.
    Returns a boolean DataFrame, True where an asset is held that period.
    """
    exit_rank = top_n + buffer
    held = set()
    rows = {}
    for d, row in rebalance_rank.iterrows():
        valid = row.dropna().sort_values(ascending=False)  # best (highest Total_Rank) first
        rank_position = {asset: i + 1 for i, asset in enumerate(valid.index)}  # 1 = best

        retained = [a for a in held if rank_position.get(a, float("inf")) <= exit_rank]
        retained.sort(key=lambda a: rank_position[a])
        retained = retained[:top_n]

        picks = list(retained)
        if len(picks) < top_n:
            for asset in valid.index:
                if asset not in picks:
                    picks.append(asset)
                if len(picks) == top_n:
                    break

        held = set(picks)
        out = pd.Series(False, index=row.index)
        out.loc[picks] = True
        rows[d] = out
    return pd.DataFrame(rows).T

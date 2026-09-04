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


def _market_returns_aligned(market_close: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Reindex the market benchmark onto `index` and forward-fill BEFORE
    taking returns, not after.

    Sparse single-day mismatches are common (a handful of days where a
    stock traded but the index didn't publish a value, or vice versa --
    found ~26 such days over 2007-2026 in Nifty 50 vs. this universe's
    trading calendar). A plain reindex leaves those as NaN, and a single
    NaN anywhere inside a `window`-day rolling calculation (beta needs
    ~252 days) blanks out the ENTIRE window, not just that one day --
    turning a handful of sparse gaps into years of missing beta values.
    Forward-filling first (carrying the last known index level forward,
    the same treatment already used for every other benchmark alignment
    in this codebase) fixes it at the source.
    """
    return market_close.reindex(index).ffill().pct_change(fill_method=None)


def beta_to_market(close: pd.DataFrame, market_close: pd.Series, window=config.BETA_WINDOW) -> pd.DataFrame:
    """Rolling CAPM beta of each stock's daily returns against the market
    (Nifty 50) benchmark's daily returns, over `window` trading days.

    Frazzini & Pedersen (2014, "Betting Against Beta", JFE) find low-beta
    stocks earn higher risk-adjusted returns than CAPM predicts -- the
    security market line is empirically "too flat." Their implementation
    isolates this as a pure risk premium via a leveraged, beta-neutral
    long-short portfolio, which needs short selling -- not usable in this
    long-only, delivery-based Indian equity strategy. The underlying
    cross-sectional finding doesn't need the short leg though: ranking
    stocks by beta and favoring the low end is a long-only tilt, exactly how
    every other factor here already works (this is what real long-only
    "low volatility" funds do in practice, e.g. ICICI Pru Nifty Low Vol 30).

    Computed via the covariance/variance identity (fully vectorized, no
    per-column rolling regression loop): beta = Cov(r_i, r_m) / Var(r_m),
    with Cov/Var expanded as E[XY] - E[X]E[Y] so everything is a plain
    rolling mean.
    """
    stock_ret = close.pct_change(fill_method=None)
    mkt_ret = _market_returns_aligned(market_close, close.index)

    mean_i = stock_ret.rolling(window).mean()
    mean_m = mkt_ret.rolling(window).mean()
    mean_im = stock_ret.multiply(mkt_ret, axis=0).rolling(window).mean()
    cov_im = mean_im - mean_i.multiply(mean_m, axis=0)

    var_m = (mkt_ret ** 2).rolling(window).mean() - mean_m ** 2

    return cov_im.div(var_m, axis=0)


def idiosyncratic_volatility(close: pd.DataFrame, market_close: pd.Series,
                              window=config.BETA_WINDOW, annualize=True) -> pd.DataFrame:
    """Volatility of each stock's return NOT explained by its market-beta
    exposure, rolling over `window` days.

    Ang, Hodrick, Xing & Zhang (2006, "The Cross-Section of Volatility and
    Expected Returns", Journal of Finance) find stocks with high
    idiosyncratic (stock-specific, non-market) volatility earn LOWER future
    returns -- a distinct anomaly from beta itself, and from the total
    volatility / downside deviation already used elsewhere in this file.
    A stock can have high total volatility purely because it has high beta
    (moves a lot because the market moves a lot) without necessarily having
    high idiosyncratic risk; this isolates the stock-specific part.

    Uses the CAPM variance decomposition Var(r_i) = beta^2 * Var(r_m) +
    Var(idiosyncratic), rather than a rolling regression-residual series
    (equivalent under CAPM assumptions, far cheaper to compute across many
    assets and a long history).
    """
    stock_ret = close.pct_change(fill_method=None)
    mkt_ret = _market_returns_aligned(market_close, close.index)

    b = beta_to_market(close, market_close, window)
    var_i = stock_ret.rolling(window).var(ddof=1)
    var_m = mkt_ret.rolling(window).var(ddof=1)

    idio_var = (var_i - (b ** 2).multiply(var_m, axis=0)).clip(lower=0)
    idio_vol = np.sqrt(idio_var)
    if annualize:
        idio_vol = idio_vol * np.sqrt(252)
    return idio_vol


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

    - Rank_of_M: highest `m` value -> highest numeric rank
    - Rank_of_V: LOWEST `v` value -> highest numeric rank
    - Rank_of_VC: LOWEST `vc` value -> highest numeric rank

    These describe the ranking MECHANISM, not a fixed economic meaning --
    the caller decides what "favored" means for the "v" and "vc" slots by
    choosing what to pass in (negating a factor before it gets here flips
    which end of it is favored). As of this writing main.py passes
    `v = -idiosyncratic_volatility(...)` (so this ends up favoring HIGH
    idiosyncratic volatility, not low -- direction flipped vs. the Ang-
    Hodrick-Xing-Zhang academic finding, based on IC evidence on this
    universe) and `vc = volume_confirmation(...)` unchanged (favoring LOW
    volume-confirmation, also flipped vs. that factor's original intent).
    Check main.py's compute_signal for what's actually plugged in before
    assuming either slot's direction.
    """
    rank_m = m.rank(axis=1, ascending=True, method="average")
    rank_v = v.rank(axis=1, ascending=False, method="average")
    rank_vc = vc.rank(axis=1, ascending=False, method="average")
    return rank_m, rank_v, rank_vc


def total_rank_daily(m: pd.DataFrame, v: pd.DataFrame, vc: pd.DataFrame,
                      w1=None, w2=None, w3=None, x=None) -> pd.DataFrame:
    w1 = config.W1 if w1 is None else w1
    w2 = config.W2 if w2 is None else w2
    w3 = config.W3 if w3 is None else w3
    x = config.X if x is None else x
    rank_m, rank_v, rank_vc = cross_sectional_ranks(m, v, vc)
    total = w1 * rank_m + w2 * rank_v + w3 * rank_vc + m / x
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

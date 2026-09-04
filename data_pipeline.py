"""Data acquisition and clean-up for the ranked asset allocation backtest."""
import os
from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf

import config


def _cache_path(ticker: str, cache_dir: str) -> str:
    # ".NS" / "&" etc are filesystem-safe as-is on Windows/Linux; ticker
    # names here are simple enough (letters, digits, "-", "&", ".") that no
    # extra escaping is needed.
    return os.path.join(cache_dir, f"{ticker}.csv")


def _load_from_cache(ticker: str, cache_dir: str):
    """Return a cached OHLCV DataFrame if it exists and was written today,
    else None (meaning: go fetch it from yfinance)."""
    path = _cache_path(ticker, cache_dir)
    if not os.path.exists(path):
        return None
    mtime = date.fromtimestamp(os.path.getmtime(path))
    if mtime != date.today():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df


def _save_to_cache(ticker: str, df: pd.DataFrame, cache_dir: str):
    os.makedirs(cache_dir, exist_ok=True)
    df.to_csv(_cache_path(ticker, cache_dir))


def download_universe(tickers, cache_dir=None):
    """Download each ticker's FULL available OHLCV history. Returns dict[ticker] -> DataFrame.

    Assets are NOT forced onto a common start date: each stock's frame
    simply starts at its own inception/listing. This keeps the universe
    survivorship-bias free -- we do not require an asset to have existed
    for the whole window to be included, and we never drop an asset just
    because it has a shorter history.

    A ticker that yfinance has no data for at all (e.g. a delisted company
    whose price history was purged from the vendor entirely) is skipped
    with a printed warning rather than aborting the whole run -- with a
    ~100+ ticker universe, one bad symbol shouldn't take down the backtest.

    A handful of long-lived, heavily-split/bonused stocks (found here:
    ADANIENT.NS, MOTHERSON.NS) trigger a yfinance/Yahoo bug where the
    dividend/split back-adjustment ("auto_adjust=True") compounds into
    outright NEGATIVE prices for their older history -- not a rare tail
    value, their entire adjusted Close series is negative from listing
    until the bug's effect decays out decades later. For any ticker where
    that happens, this falls back to RAW (unadjusted) prices instead. Raw
    prices are correct in sign but show a real jump on each stock split/
    bonus-issue date (since shares outstanding changed but history wasn't
    rescaled); the winsorization step downstream (which already exists to
    absorb exactly this kind of single/multi-day discontinuity from vendor
    data problems) smooths those out, which is a far smaller distortion
    than carrying negative prices into log-based factor math.

    Each ticker's resolved OHLCV frame (whichever of the above paths it
    took) is cached to a per-ticker CSV under `cache_dir` (defaults to
    config.CACHE_DIR; pass a different dir for a different market's
    universe, e.g. nasdaq_config.CACHE_DIR, to keep caches separate) so
    re-running the backtest the same day doesn't re-hit yfinance for
    ~100+ tickers every time.
    """
    cache_dir = config.CACHE_DIR if cache_dir is None else cache_dir
    data = {}
    skipped = []
    fell_back_to_raw = []
    from_cache = 0
    for t in tickers:
        cached = _load_from_cache(t, cache_dir)
        if cached is not None:
            data[t] = cached
            from_cache += 1
            continue

        try:
            df = yf.download(t, period="max", auto_adjust=True, progress=False)
        except Exception as e:
            skipped.append((t, str(e)[:100]))
            continue
        if df.empty:
            skipped.append((t, "no data returned"))
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if (df["Close"] <= 0).any():
            try:
                raw = yf.download(t, period="max", auto_adjust=False, progress=False)
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = raw.columns.get_level_values(0)
                if not raw.empty and (raw["Close"] > 0).all():
                    df = raw
                    fell_back_to_raw.append(t)
            except Exception:
                pass  # keep the auto_adjust frame; still-bad rows are caught by the caller

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        data[t] = df
        _save_to_cache(t, df, cache_dir)
    if from_cache:
        print(f"  Loaded {from_cache} ticker(s) from today's local cache ({cache_dir}/)")
    if fell_back_to_raw:
        print(f"  Fell back to raw (unadjusted) prices for {len(fell_back_to_raw)} "
              f"ticker(s) with a broken auto-adjust series: {', '.join(fell_back_to_raw)}")
    if skipped:
        print(f"  Skipped {len(skipped)} ticker(s) with no usable data: "
              f"{', '.join(t for t, _ in skipped)}")
    if not data:
        raise RuntimeError("No tickers returned any data.")
    return data


def fix_invalid_open(data: dict) -> dict:
    """Repair non-positive Open prices.

    Yahoo Finance's early history (2009 through ~Jan-2010) for several of
    these NSE ETFs reports Open=0 on ~250 sessions even though High/Low/Close
    are populated -- a vendor data gap, not a real price. Left as-is this
    feeds a log(0) into the Yang-Zhang volatility estimator (which needs
    Open) and NaNs out that factor for an extended stretch, silently
    excluding otherwise-tradable assets from ranking during that window.
    Replaced with the prior day's Close (i.e. assume no overnight gap on the
    missing day, using only already-known past data -- no look-ahead), or
    that same day's Close as a last-resort fallback for a leading row.
    """
    cleaned = {}
    for t, df in data.items():
        df = df.copy()
        bad = (df["Open"] <= 0) | df["Open"].isna()
        df.loc[bad, "Open"] = df["Close"].shift(1)[bad]
        still_bad = df["Open"].isna() | (df["Open"] <= 0)
        df.loc[still_bad, "Open"] = df.loc[still_bad, "Close"]
        cleaned[t] = df
    return cleaned


def drop_non_trading_weekdays(data: dict) -> dict:
    """Drop any Saturday/Sunday rows from the raw vendor data.

    NSE does not hold regular weekend sessions -- the one exception,
    Diwali Muhurat trading, is a specific known calendar date handled by
    drop_muhurat_days, not a general weekend pattern. A weekend-dated row
    in the raw feed is a data error (a mis-timestamped Friday close or
    Monday open, or similar vendor glitch), not a real trading session.

    Left in, a single such row for even ONE ticker corrupts the union-based
    multi-asset panel: on that phantom "day," every other held asset has no
    price at all and falls back to its entry price for mark-to-market,
    while the one bad ticker marks-to-market off a real (or semi-real)
    price -- producing a spurious spike-then-revert in portfolio NAV.
    Found via a genuine case: a Saturday 2010-02-06 row present for exactly
    1 of 50 Nifty 50 tickers, which alone produced a false +37.8%/-26.4%
    two-day portfolio NAV swing that survived winsorization (winsorization
    checks each ticker's OWN return magnitude, not whether the calendar
    date it's dated on is a real trading day shared by other assets).
    """
    cleaned = {}
    for t, df in data.items():
        cleaned[t] = df[df.index.dayofweek < 5].copy()
    return cleaned


def drop_muhurat_days(data: dict, muhurat_dates=None) -> dict:
    """Remove NSE Muhurat-trading calendar dates from every asset's history.
    `muhurat_dates` defaults to config.MUHURAT_TRADING_DATES (India); pass
    an empty list for markets with no such exception (e.g. the US)."""
    dates = config.MUHURAT_TRADING_DATES if muhurat_dates is None else muhurat_dates
    muhurat = pd.to_datetime(dates)
    cleaned = {}
    for t, df in data.items():
        cleaned[t] = df[~df.index.normalize().isin(muhurat)].copy()
    return cleaned


def winsorize_returns(data: dict, lower=config.WINSOR_LOWER_PCTL, upper=config.WINSOR_UPPER_PCTL,
                       abs_return_cap=None) -> dict:
    """Winsorize each asset's OHLC bars based on its own daily-return tails.

    A day whose Close-to-Close return falls below the `lower` percentile or
    above the `upper` percentile of that asset's own return distribution
    *as observed so far* is treated as a fake tail event (e.g. a stale/bad
    tick from the data vendor): the day's OHLC are rescaled so that the
    realized return is clipped to the percentile boundary, while preserving
    the intraday High/Low/Open shape relative to Close.

    The percentile bounds are computed with an EXPANDING window (point-in-
    time only, `min_periods` warm-up before any clipping starts) rather than
    over the full sample. Using the full-sample quantile would mean a 2017
    data point gets cleaned using knowledge of returns observed as late as
    2026 -- a look-ahead / data-snooping leak into a step that is supposed to
    be pure data hygiene.

    A fixed absolute cap (`config.WINSOR_ABS_RETURN_CAP`) is layered on top
    of the expanding quantile. It is NOT derived from the data (no
    look-ahead), and it exists because the 0.1th/99.9th percentile of only
    ~2500 daily observations is a fundamentally noisy estimate -- it is
    effectively interpolating between the 2nd/3rd most extreme values ever
    observed -- so the expanding quantile alone can remain too wide to catch
    a catastrophic (~90%+) data-vendor glitch even long past its warm-up.

    Separately, each day's return is recomputed against the *already-
    adjusted* previous close (not the raw one) and the decision to clip is
    re-evaluated on that recomputed return. This matters for multi-day data
    glitches (observed e.g. around 2019-12-19/20 in the raw Yahoo Finance
    feed for several NSE ETFs, where price craters ~99% for two sessions and
    then snaps back): a single-pass check against raw returns only catches
    the first bad day and lets the "recovery" day through as if it were a
    huge legitimate rally. Recomputing against the adjusted chain catches
    both the drop and the snap-back and reverts the whole glitch, days at a
    time, without silently deleting any trading day.
    """
    min_periods = 252  # ~1 trading year of history before bounds are trusted
    cleaned = {}
    for t, df in data.items():
        df = df.copy()
        raw_close = df["Close"].to_numpy(dtype=float)
        raw_ret = df["Close"].pct_change()
        lo_series = raw_ret.expanding(min_periods=min_periods).quantile(lower).to_numpy()
        hi_series = raw_ret.expanding(min_periods=min_periods).quantile(upper).to_numpy()

        cap = config.WINSOR_ABS_RETURN_CAP if abs_return_cap is None else abs_return_cap
        adj_close = raw_close.copy()
        for i in range(1, len(adj_close)):
            prev_adj = adj_close[i - 1]
            if prev_adj <= 0 or np.isnan(prev_adj) or np.isnan(raw_close[i]):
                adj_close[i] = raw_close[i]
                continue
            lo_i, hi_i = lo_series[i], hi_series[i]
            lo = max(lo_i, -cap) if not np.isnan(lo_i) else -cap
            hi = min(hi_i, cap) if not np.isnan(hi_i) else cap
            r = raw_close[i] / prev_adj - 1
            r_clipped = min(max(r, lo), hi)
            adj_close[i] = prev_adj * (1 + r_clipped)

        close_new = pd.Series(adj_close, index=df.index)
        scale = (close_new / df["Close"]).replace([np.inf, -np.inf], 1.0).fillna(1.0)
        df["Open"] = df["Open"] * scale
        df["High"] = df["High"] * scale
        df["Low"] = df["Low"] * scale
        df["Close"] = close_new
        cleaned[t] = df
    return cleaned


def clean_data(raw: dict, muhurat_dates=None, winsor_abs_cap=None) -> dict:
    step_weekday = drop_non_trading_weekdays(raw)
    step0 = fix_invalid_open(step_weekday)
    step1 = drop_muhurat_days(step0, muhurat_dates)
    step2 = winsorize_returns(step1, abs_return_cap=winsor_abs_cap)
    return step2


def first_date_with_min_coverage(close: pd.DataFrame, min_tickers: int) -> pd.Timestamp:
    """First date on which at least `min_tickers` assets in `close` have
    valid (non-NaN) data.

    Matters when a universe is defined by TODAY's constituents but the data
    goes back much further than most of those constituents' listing dates
    (found on Nasdaq-100: only 28-56 of the current 102 names existed at
    all between 1986-1997). Before enough of the universe exists, every
    pick is drawn from an ever-smaller pool that's, by construction,
    pre-filtered for "eventually became a 40-year mega-cap winner" -- a
    much more severe form of the survivorship bias already present in
    "current constituents only" than a normal-sized universe has. Capping
    the backtest start here (in addition to any benchmark-availability
    floor) keeps that amplified-bias stretch out of the reported numbers."""
    counts = close.notna().sum(axis=1)
    valid = counts[counts >= min_tickers]
    return valid.index[0] if len(valid) else close.index[0]


def split_dates(all_dates: pd.DatetimeIndex):
    """Chronological 60/20/20 split by trading-date index position."""
    n = len(all_dates)
    train_end = int(n * config.TRAIN_FRAC)
    val_end = train_end + int(n * config.VAL_FRAC)
    train = all_dates[:train_end]
    val = all_dates[train_end:val_end]
    test = all_dates[val_end:]
    return train, val, test


def build_price_panels(data: dict):
    """Combine per-asset frames into aligned wide panels (union of dates)."""
    all_index = sorted(set().union(*[df.index for df in data.values()]))
    all_index = pd.DatetimeIndex(all_index)
    panels = {}
    for field in ["Open", "High", "Low", "Close", "Volume"]:
        panel = pd.DataFrame(index=all_index, columns=list(data.keys()), dtype=float)
        for t, df in data.items():
            panel.loc[df.index, t] = df[field]
        panels[field] = panel
    return panels

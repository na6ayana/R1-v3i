"""Information Coefficient (IC) analysis for the ranking factors.

IC here is the monthly cross-sectional Spearman rank correlation between a
factor's month-end value and the asset's forward (next-month) return -- the
standard way to check whether a ranking factor actually has predictive
power, independent of the backtest's cost/tax/execution mechanics.
"""
import numpy as np
import pandas as pd
from scipy import stats


def forward_returns(close: pd.DataFrame, month_end_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Forward return from each month-end date to the NEXT month-end date,
    per asset -- the holding-period return an asset ranked at date t would
    go on to realize over month t+1 (ignores the 1-day execution lag used
    in the actual backtest; that lag is immaterial to whether the factor
    has signal)."""
    px = close.reindex(month_end_dates, method="ffill")
    fwd = px.shift(-1) / px - 1
    return fwd


def compute_ic_series(factor_monthly: pd.DataFrame, fwd_ret: pd.DataFrame, min_assets=5) -> pd.Series:
    """Monthly Spearman rank-IC between a factor and forward returns.
    One IC value per month-end date with enough valid (factor, fwd_ret) pairs."""
    dates = factor_monthly.index.intersection(fwd_ret.index)
    out = {}
    for d in dates:
        f = factor_monthly.loc[d]
        r = fwd_ret.loc[d]
        valid = f.notna() & r.notna()
        if valid.sum() < min_assets:
            continue
        ic, _ = stats.spearmanr(f[valid], r[valid])
        if not np.isnan(ic):
            out[d] = ic
    return pd.Series(out).sort_index()


def summarize_ic(ic_series: pd.Series, factor_name: str) -> dict:
    n = len(ic_series)
    mean_ic = ic_series.mean() if n else np.nan
    std_ic = ic_series.std(ddof=1) if n > 1 else np.nan
    t_stat = mean_ic / (std_ic / np.sqrt(n)) if n > 1 and std_ic > 0 else np.nan
    ir_monthly = mean_ic / std_ic if std_ic and std_ic > 0 else np.nan
    pct_positive = (ic_series > 0).mean() * 100 if n else np.nan
    return {
        "factor": factor_name,
        "n_months": n,
        "mean_ic": mean_ic,
        "std_ic": std_ic,
        "t_stat": t_stat,
        "ir_monthly": ir_monthly,
        "pct_months_positive": pct_positive,
    }


def run_ic_analysis(close: pd.DataFrame, factor_monthly_snapshots: dict) -> tuple[dict, pd.DataFrame]:
    """factor_monthly_snapshots: {name: monthly-indexed factor DataFrame}
    (all sharing the same asset columns as `close`). Returns
    (per-factor IC time series dict, summary DataFrame)."""
    all_month_ends = sorted(set().union(*[df.index for df in factor_monthly_snapshots.values()]))
    fwd_ret = forward_returns(close, pd.DatetimeIndex(all_month_ends))

    ic_series_by_factor = {}
    summaries = []
    for name, factor_monthly in factor_monthly_snapshots.items():
        ic_series = compute_ic_series(factor_monthly, fwd_ret)
        ic_series_by_factor[name] = ic_series
        summaries.append(summarize_ic(ic_series, name))

    summary_df = pd.DataFrame(summaries).set_index("factor")
    return ic_series_by_factor, summary_df


def print_ic_table(summary_df: pd.DataFrame):
    print(f"{'Factor':<12} {'N':>5} {'Mean IC':>9} {'Std IC':>8} {'t-stat':>8} {'IR(mo)':>8} {'%Pos':>7}")
    for name, row in summary_df.iterrows():
        print(f"{name:<12} {row['n_months']:>5.0f} {row['mean_ic']:>9.4f} {row['std_ic']:>8.4f} "
              f"{row['t_stat']:>8.2f} {row['ir_monthly']:>8.3f} {row['pct_months_positive']:>6.1f}%")

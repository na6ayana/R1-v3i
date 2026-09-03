"""Performance metrics for a daily NAV / return series."""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def daily_returns(nav: pd.Series) -> pd.Series:
    return nav.pct_change().dropna()


def cagr(nav: pd.Series) -> float:
    n_days = (nav.index[-1] - nav.index[0]).days
    if n_days <= 0:
        return np.nan
    total_return = nav.iloc[-1] / nav.iloc[0]
    years = n_days / 365.25
    return total_return ** (1 / years) - 1


def annualized_vol(rets: pd.Series) -> float:
    return rets.std(ddof=1) * np.sqrt(TRADING_DAYS)


def sharpe_ratio(rets: pd.Series, rf_annual=0.06) -> float:
    rf_daily = (1 + rf_annual) ** (1 / TRADING_DAYS) - 1
    excess = rets - rf_daily
    if excess.std(ddof=1) == 0:
        return np.nan
    return (excess.mean() / excess.std(ddof=1)) * np.sqrt(TRADING_DAYS)


def sortino_ratio(rets: pd.Series, rf_annual=0.06) -> float:
    rf_daily = (1 + rf_annual) ** (1 / TRADING_DAYS) - 1
    excess = rets - rf_daily
    downside = excess[excess < 0]
    dd = downside.std(ddof=1)
    if dd == 0 or np.isnan(dd):
        return np.nan
    return (excess.mean() / dd) * np.sqrt(TRADING_DAYS)


def max_drawdown(nav: pd.Series) -> float:
    running_max = nav.cummax()
    dd = nav / running_max - 1
    return dd.min()


def calmar_ratio(nav: pd.Series) -> float:
    mdd = max_drawdown(nav)
    if mdd == 0:
        return np.nan
    return cagr(nav) / abs(mdd)


def total_return(nav: pd.Series) -> float:
    return nav.iloc[-1] / nav.iloc[0] - 1


def win_rate(rets: pd.Series) -> float:
    return (rets > 0).mean()


def summary(nav: pd.Series, label: str = "") -> dict:
    rets = daily_returns(nav)
    return {
        "period": label,
        "start": nav.index[0].date(),
        "end": nav.index[-1].date(),
        "total_return_pct": total_return(nav) * 100,
        "cagr_pct": cagr(nav) * 100,
        "ann_vol_pct": annualized_vol(rets) * 100,
        "sharpe": sharpe_ratio(rets),
        "sortino": sortino_ratio(rets),
        "max_drawdown_pct": max_drawdown(nav) * 100,
        "calmar": calmar_ratio(nav),
        "win_rate_pct": win_rate(rets) * 100,
    }


def print_summary(s: dict):
    print(f"--- {s['period']}  ({s['start']} to {s['end']}) ---")
    print(f"  Total Return   : {s['total_return_pct']:.2f}%")
    print(f"  CAGR           : {s['cagr_pct']:.2f}%")
    print(f"  Ann. Volatility: {s['ann_vol_pct']:.2f}%")
    print(f"  Sharpe Ratio   : {s['sharpe']:.2f}")
    print(f"  Sortino Ratio  : {s['sortino']:.2f}")
    print(f"  Max Drawdown   : {s['max_drawdown_pct']:.2f}%")
    print(f"  Calmar Ratio   : {s['calmar']:.2f}")
    print(f"  Win Rate       : {s['win_rate_pct']:.2f}%")

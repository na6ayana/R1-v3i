"""Trading liquidity / market-impact (slippage) modeling.

The audit found the backtest had NO slippage model at all -- every trade
executed at the exact quoted Open price regardless of size, and a check
against real average daily traded value (ADTV) showed a single position at
the backtest's ending NAV could be ~10% of a day's volume for the
least-liquid current constituents. That's large enough to move the market
in practice; modeling it here rather than leaving it silently at zero.
"""
import numpy as np
import pandas as pd

import config


def average_daily_traded_value(close: pd.DataFrame, volume: pd.DataFrame, window=60) -> pd.DataFrame:
    """Trailing rolling average of Close*Volume (INR traded per day), per
    asset, SHIFTED by one day so today's trade is sized against liquidity
    known as of yesterday's close -- today's own volume isn't observable
    before today's trade executes, so using it would be a (mild) look-ahead.
    """
    traded_value = close * volume
    return traded_value.rolling(window).mean().shift(1)


def slippage_pct(trade_value: float, adtv: float, coef=config.SLIPPAGE_COEF,
                  max_pct=config.SLIPPAGE_MAX_PCT) -> float:
    """Square-root market-impact model: slippage (as a fraction of price)
    grows with the square root of participation rate (trade size / ADTV).

    This is the standard functional form used in the market-impact
    literature (e.g. Almgren, Thum, Hauptmann & Li 2005, "Direct Estimation
    of Equity Market Impact") -- impact scales sub-linearly with trade size
    because a large order can be absorbed by more of the order book /
    liquidity providers than the mechanical size ratio alone would suggest.
    `coef` is a rough calibration (not fit to Indian market microstructure
    data, which isn't available here): coef=0.01 means trading exactly
    100% of a stock's ADTV in one day costs ~1% slippage; 10% of ADTV costs
    ~0.32%; 1% of ADTV costs ~0.1%.

    If ADTV is unknown (missing history, e.g. very early in a stock's
    listing) or non-positive, slippage is NOT modeled for that trade
    (returns 0) rather than guessing -- a residual, disclosed gap, not a
    hidden inflation.
    """
    if adtv is None or pd.isna(adtv) or adtv <= 0 or trade_value <= 0:
        return 0.0
    participation = trade_value / adtv
    pct = coef * np.sqrt(participation)
    return min(pct, max_pct)

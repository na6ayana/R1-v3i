"""Share-count-level portfolio simulation: rebalancing, costs, capital-gains tax."""
import numpy as np
import pandas as pd

import config
import costs


def build_signal_weights(rebalance_membership: pd.DataFrame) -> pd.DataFrame:
    """Equal-weight target for the period FOLLOWING each rebalance date."""
    n_selected = rebalance_membership.sum(axis=1).replace(0, np.nan)
    return rebalance_membership.div(n_selected, axis=0).fillna(0.0)


def daily_target_weights(rebalance_weights: pd.DataFrame, daily_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Forward-fill the rebalance-period signal onto the daily calendar, then
    shift by one trading day so a signal known at a rebalance-date close is
    only acted on the following trading day (no look-ahead)."""
    daily = rebalance_weights.reindex(daily_index, method="ffill")
    daily = daily.shift(1)
    return daily.fillna(0.0)


def run_backtest(open_px: pd.DataFrame, close_px: pd.DataFrame, target_weights: pd.DataFrame,
                  initial_capital=config.INITIAL_CAPITAL):
    """Event-driven simulation with share-count accounting.

    Rebalance trades execute at the day's Open price (the day after the
    signal date), valued against the portfolio's value at the prior close.
    Returns a dict of daily series: nav, cash, turnover, costs, taxes.
    """
    dates = close_px.index
    assets = list(close_px.columns)

    cash = initial_capital
    shares = {a: 0.0 for a in assets}
    entry_price = {a: None for a in assets}
    entry_date = {a: None for a in assets}
    fy_ltcg_used = {}

    nav_hist = []
    cost_hist = []
    tax_hist = []
    turnover_hist = []
    n_holdings_hist = []

    prev_close_val = initial_capital
    prev_tw_row = None

    for i, d in enumerate(dates):
        day_cost = 0.0
        day_tax = 0.0
        day_turnover = 0.0

        tw_row = target_weights.loc[d] if d in target_weights.index else None
        # Only actually trade when the target weights CHANGE (a real monthly
        # rebalance event), not every day. target_weights is constant within
        # a month (ffilled from the monthly signal), but NAV and prices drift
        # daily -- recomputing target_shares off every day's price would force
        # a tiny "rebalance" trade daily just to cancel out normal price
        # drift, producing far more turnover/cost/tax than the strategy
        # (buy the top-N, hold equal-weight until the next ranking) calls for.
        is_rebalance_day = tw_row is not None and (prev_tw_row is None or not tw_row.equals(prev_tw_row))
        if tw_row is not None:
            prev_tw_row = tw_row

        if is_rebalance_day:
            o_row = open_px.loc[d]
            portfolio_value_for_sizing = prev_close_val

            # Only assets with a usable open price today can be traded today.
            for a in assets:
                target_w = tw_row.get(a, 0.0)
                if pd.isna(target_w):
                    target_w = 0.0
                px = o_row.get(a, np.nan)
                if pd.isna(px) or px <= 0:
                    continue  # asset not tradeable today (e.g. not yet listed) -> hold prior state (should be 0 anyway)

                target_value = portfolio_value_for_sizing * target_w
                target_shares = target_value / px if px > 0 else 0.0
                delta = target_shares - shares[a]

                if abs(delta) < 1e-9:
                    continue

                trade_value = abs(delta) * px
                day_turnover += trade_value

                if delta > 0:
                    c = costs.buy_cost(trade_value)
                    cash -= trade_value + c
                    day_cost += c
                    if shares[a] > 0 and entry_price[a] is not None:
                        # blended cost basis for the added tranche; keep original entry date
                        new_shares = shares[a] + delta
                        entry_price[a] = (shares[a] * entry_price[a] + delta * px) / new_shares
                    else:
                        entry_price[a] = px
                        entry_date[a] = d
                    shares[a] = shares[a] + delta
                else:
                    sell_shares = -delta
                    full_exit = target_shares <= 1e-9
                    c = costs.sell_cost(trade_value, full_exit)
                    proceeds = trade_value
                    cash += proceeds - c
                    day_cost += c

                    if entry_price[a] is not None:
                        gain = sell_shares * (px - entry_price[a])
                        holding_days = (d - entry_date[a]).days if entry_date[a] is not None else 0
                        fy = costs.fiscal_year(d)
                        tax = costs.capital_gains_tax(gain, holding_days, fy, fy_ltcg_used)
                        cash -= tax
                        day_tax += tax

                    shares[a] = target_shares
                    if full_exit:
                        entry_price[a] = None
                        entry_date[a] = None

        # Mark to market at today's close
        c_row = close_px.loc[d]
        holdings_value = 0.0
        n_held = 0
        for a in assets:
            px = c_row.get(a, np.nan)
            if shares[a] > 0:
                if pd.isna(px):
                    px = entry_price[a] if entry_price[a] is not None else 0.0
                holdings_value += shares[a] * px
                n_held += 1

        nav = cash + holdings_value
        nav_hist.append(nav)
        cost_hist.append(day_cost)
        tax_hist.append(day_tax)
        turnover_hist.append(day_turnover)
        n_holdings_hist.append(n_held)
        prev_close_val = nav

    result = pd.DataFrame({
        "nav": nav_hist,
        "cost": cost_hist,
        "tax": tax_hist,
        "turnover": turnover_hist,
        "n_holdings": n_holdings_hist,
    }, index=dates)
    return result

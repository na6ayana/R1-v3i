"""Equity-delivery transaction cost & capital-gains tax model.

Market-agnostic: every function takes an optional `cost_config` dict
(defaulting to config.COSTS, the Indian assumptions) so a different market's
cost/tax structure -- e.g. a US model with no STT/stamp duty and a calendar
tax year instead of Apr-Mar -- can reuse this same engine without touching
it. See nasdaq_config.py's COSTS dict for the US variant.
"""
import config


def buy_cost(trade_value: float, cost_config: dict = None) -> float:
    c = cost_config if cost_config is not None else config.COSTS
    brokerage = trade_value * c["brokerage_pct"]
    stt = trade_value * c["stt_pct"]
    exch = trade_value * c["exchange_txn_pct"]
    sebi = trade_value * c["sebi_fee_pct"]
    stamp = trade_value * c["stamp_duty_pct"]
    gst = (brokerage + exch) * c["gst_pct"]
    return brokerage + stt + exch + sebi + stamp + gst


def sell_cost(trade_value: float, full_exit: bool, cost_config: dict = None) -> float:
    c = cost_config if cost_config is not None else config.COSTS
    brokerage = trade_value * c["brokerage_pct"]
    stt = trade_value * c["stt_pct"]
    exch = trade_value * c["exchange_txn_pct"]
    sebi = trade_value * c["sebi_fee_pct"]
    gst = (brokerage + exch) * c["gst_pct"]
    dp = c["dp_charge_flat"] if full_exit else 0.0
    return brokerage + stt + exch + sebi + gst + dp


def fiscal_year(date, fy_start_month: int = 4) -> int:
    """Tax-year label: a year starting `fy_start_month` -> label = that
    year. Default 4 = Indian FY (Apr-Mar). Pass fy_start_month=1 for a
    plain calendar tax year (e.g. the US)."""
    return date.year if date.month >= fy_start_month else date.year - 1


def capital_gains_tax(gain: float, holding_days: int, fy: int, fy_ltcg_used: dict,
                       cost_config: dict = None) -> float:
    """Tax on a single realized-gain event. Losses are not taxed (and are
    not offset against other gains -- a simplification vs. real loss
    carry-forward rules)."""
    if gain <= 0:
        return 0.0
    c = cost_config if cost_config is not None else config.COSTS
    if holding_days > 365:
        used = fy_ltcg_used.get(fy, 0.0)
        exemption_left = max(c["ltcg_exemption"] - used, 0.0)
        taxable = max(gain - exemption_left, 0.0)
        fy_ltcg_used[fy] = used + gain
        return taxable * c["ltcg_rate"]
    else:
        return gain * c["stcg_rate"]

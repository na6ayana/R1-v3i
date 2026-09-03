"""Indian equity-delivery transaction cost & capital-gains tax model."""
import config


def buy_cost(trade_value: float) -> float:
    c = config.COSTS
    brokerage = trade_value * c["brokerage_pct"]
    stt = trade_value * c["stt_pct"]
    exch = trade_value * c["exchange_txn_pct"]
    sebi = trade_value * c["sebi_fee_pct"]
    stamp = trade_value * c["stamp_duty_pct"]
    gst = (brokerage + exch) * c["gst_pct"]
    return brokerage + stt + exch + sebi + stamp + gst


def sell_cost(trade_value: float, full_exit: bool) -> float:
    c = config.COSTS
    brokerage = trade_value * c["brokerage_pct"]
    stt = trade_value * c["stt_pct"]
    exch = trade_value * c["exchange_txn_pct"]
    sebi = trade_value * c["sebi_fee_pct"]
    gst = (brokerage + exch) * c["gst_pct"]
    dp = c["dp_charge_flat"] if full_exit else 0.0
    return brokerage + stt + exch + sebi + gst + dp


def fiscal_year(date) -> int:
    """Indian FY label: Apr(year) - Mar(year+1) => label = year."""
    return date.year if date.month >= 4 else date.year - 1


def capital_gains_tax(gain: float, holding_days: int, fy: int, fy_ltcg_used: dict) -> float:
    """Tax on a single realized-gain event. Losses are not taxed (and are
    not offset against other gains -- a simplification vs. real loss
    carry-forward rules)."""
    if gain <= 0:
        return 0.0
    c = config.COSTS
    if holding_days > 365:
        used = fy_ltcg_used.get(fy, 0.0)
        exemption_left = max(c["ltcg_exemption"] - used, 0.0)
        taxable = max(gain - exemption_left, 0.0)
        fy_ltcg_used[fy] = used + gain
        return taxable * c["ltcg_rate"]
    else:
        return gain * c["stcg_rate"]

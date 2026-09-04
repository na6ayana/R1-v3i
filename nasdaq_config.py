"""Configuration for testing the ranked allocation strategy on Nasdaq-100
stocks -- a separate market profile, reusing the same engine
(factors.py/backtest.py/metrics.py/ic_analysis.py/liquidity.py) as the
Indian config.py, but with US-specific universe, costs, tax, and benchmark.

This is a direct PORT of the strategy validated on Nifty 100 (same factor
windows, rebalance cadence, hysteresis, weights) -- NOT a re-tuned model.
The point of this module is to test "does the same design travel to a
different market," not to re-run the whole IC-driven design process again
for the US. If you want a genuinely re-tuned US strategy, that's a
separate, larger effort (repeat the IC/walk-forward iteration this session
did for India, on US data).
"""
import config  # reuse market-agnostic strategy-design parameters from here

# --- Universe ----------------------------------------------------------
# Current Nasdaq-100 constituents (102 tickers -- includes both share
# classes of Alphabet, GOOG/GOOGL, which is why it's not exactly 100),
# fetched live from Nasdaq's own quote-list API
# (api.nasdaq.com/api/quote/list-type/nasdaq100) on 2026-09-04. Every
# ticker individually verified against yfinance: resolves, quoteType
# EQUITY, no negative-price auto-adjust bug (the class of issue found for
# ADANIENT.NS/MOTHERSON.NS on the Indian side).
#
# Same survivorship-bias caveat as the Indian universe: this is TODAY's
# membership, not a reconstructed historical membership list -- yfinance
# has no historical index-composition API for Nasdaq-100 either. No
# delisted/failed-company backfill list was built for this market (out of
# scope for a first port); if wanted later, the same DELISTED_HISTORICAL
# pattern from config.py could be replicated here.
UNIVERSE = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "ALAB", "ALNY", "AMAT",
    "AMD", "AMGN", "AMZN", "APP", "ARM", "ASML", "AVGO", "AXON", "BKNG", "BKR",
    "CCEP", "CDNS", "CEG", "CMCSA", "COST", "CPRT", "CRWD", "CRWV", "CSCO", "CSX",
    "CTAS", "DASH", "DDOG", "DXCM", "EXC", "FANG", "FAST", "FER", "FTNT", "GEHC",
    "GILD", "GOOG", "GOOGL", "HON", "HONA", "IDXX", "INTC", "INTU", "ISRG", "KDP",
    "KHC", "KLAC", "LIN", "LITE", "LRCX", "MAR", "MCHP", "MDLZ", "MELI", "META",
    "MNST", "MPWR", "MRVL", "MSFT", "MSTR", "MU", "NBIS", "NFLX", "NVDA", "NXPI",
    "ODFL", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR", "PYPL", "QCOM",
    "REGN", "RKLB", "ROP", "ROST", "SBUX", "SHOP", "SNDK", "SNPS", "SPCX", "STX",
    "TER", "TMUS", "TRI", "TSLA", "TTWO", "TXN", "VRTX", "WBD", "WDAY", "WDC",
    "WMT", "XEL",
]

BENCHMARK = "^NDX"  # Nasdaq-100 index

# --- Currency / notional -------------------------------------------------
CURRENCY = "USD"
INITIAL_CAPITAL = 1_000_000.0  # USD 1 million notional (illustrative, like the INR 1cr figure)

# --- Local price-data cache ------------------------------------------------
# Separate cache dir from the Indian one -- no ticker collisions expected
# (US tickers carry no ".NS" suffix) but keeping them apart avoids ever
# mixing markets' cached data by accident.
CACHE_DIR = "data_cache_nasdaq"

# --- Calendar exceptions --------------------------------------------------
# No Nasdaq/NYSE equivalent of NSE's Muhurat trading session -- US market
# holidays are already absent from the raw data entirely (the exchange is
# simply closed, no special low-volume session gets recorded), so nothing
# needs to be explicitly excluded here.
MUHURAT_TRADING_DATES = []

# --- Data cleaning ---------------------------------------------------------
# Reuse the Indian winsorization percentiles (0.1/99.9, expanding window --
# see data_pipeline.winsorize_returns) as-is; they're not India-specific.
# The absolute backstop cap is kept at the same 0.65 as the Indian stock
# universe: Nasdaq-100 names are all large-caps (no penny/distressed names
# the way the Indian delisted-stock list had), but real ~20-35% single-day
# moves on earnings shocks do happen even for mega-caps (e.g. META -26%
# Feb-2022, NFLX -35% at times), so 0.65 stays a safe, non-binding ceiling
# rather than something likely to clip a genuine move.
WINSOR_ABS_RETURN_CAP = config.WINSOR_ABS_RETURN_CAP

# --- Strategy parameters ---------------------------------------------------
# Straight port from config.py -- see that file's comments for the research
# rationale behind each of these (12-1 momentum, idiosyncratic-vol window,
# quarterly rebalance, hysteresis buffer). Not re-tuned for this market.
MOMENTUM_WINDOW = config.MOMENTUM_WINDOW
MOMENTUM_SKIP = config.MOMENTUM_SKIP
BETA_WINDOW = config.BETA_WINDOW
VOLUME_FAST = config.VOLUME_FAST
VOLUME_SLOW = config.VOLUME_SLOW
W1, W2, W3 = config.W1, config.W2, config.W3
X = config.X
TOP_N = config.TOP_N
REBALANCE_FREQ = config.REBALANCE_FREQ
HYSTERESIS_BUFFER = config.HYSTERESIS_BUFFER

TRAIN_FRAC = config.TRAIN_FRAC
VAL_FRAC = config.VAL_FRAC
TEST_FRAC = config.TEST_FRAC

# --- Market impact / slippage -----------------------------------------------
# Same functional form and coefficient as the Indian model (see
# config.SLIPPAGE_COEF's comment) -- Nasdaq-100 names are extremely liquid
# mega-caps with daily traded values typically in the hundreds of millions
# to billions of USD, so slippage should end up near-negligible here
# regardless; kept for consistency and to actually verify that expectation
# rather than assume it.
SLIPPAGE_COEF = config.SLIPPAGE_COEF
SLIPPAGE_MAX_PCT = config.SLIPPAGE_MAX_PCT

# --- US equity trading cost & capital-gains tax assumptions -----------------
# Materially different cost structure from India: major US brokers
# (Schwab, Fidelity, Robinhood, etc.) charge $0 commission on stock trades,
# there's no STT/stamp-duty/GST equivalent, and the small regulatory fees
# that do exist (SEC Section 31 fee, FINRA Trading Activity Fee) are both
# sell-side-only and tiny. Capital gains tax is federal ordinary-income
# rates for short-term (<=1yr) and preferential rates for long-term (>1yr),
# and is HIGHLY investor-specific (federal bracket + state tax + NIIT) --
# unlike India's STCG/LTCG, there's no single "the" rate. Flat, disclosed,
# illustrative assumptions used here (a moderately-high federal bracket,
# no state tax, no NIIT -- adjust for your own situation): 32% short-term,
# 15% long-term (the most common LTCG bracket), no flat-dollar exemption
# (the US 0% LTCG bracket is income-driven, not a flat exempt amount the
# way India's Rs1.25L LTCG exemption is, so there's no direct analog here).
COSTS = {
    "brokerage_pct": 0.0,           # $0 commission at major US brokers
    "stt_pct": 0.0,                 # no US equivalent of India's STT
    "exchange_txn_pct": 0.00003,    # rough combined SEC Section 31 fee + FINRA TAF, sell-side-only in reality but modeled on both legs for simplicity (tiny either way)
    "sebi_fee_pct": 0.0,            # no US equivalent
    "stamp_duty_pct": 0.0,          # no US equivalent
    "gst_pct": 0.0,                 # no GST on US brokerage
    "dp_charge_flat": 0.0,          # no US equivalent of India's per-scrip DP charge
    "stcg_rate": 0.32,              # short-term (<=1yr): taxed as ordinary income; 32% federal bracket assumed, no state tax
    "ltcg_rate": 0.15,              # long-term (>1yr): most common US LTCG bracket
    "ltcg_exemption": 0.0,          # no flat-dollar LTCG exemption in the US system
}

# US tax year is the calendar year (Jan-Dec), unlike India's Apr-Mar FY.
FY_START_MONTH = 1

# Risk-free rate for Sharpe/Sortino (metrics.py defaults to 6%, a rough
# Indian rate proxy). ~4% is a more reasonable US Treasury-based estimate;
# treat as illustrative, not fit to any specific historical period.
RF_ANNUAL = 0.04

# ^NDX (the benchmark) has data back to 1985, but most of TODAY's 102
# constituents didn't exist yet -- only 28 of them had data in 1986, 35 in
# 1990, 50 in 1995 (checked directly against the cache). Before enough of
# the universe exists, the ranking is drawn from an ever-smaller,
# ever-more-survivorship-biased pool. Require at least half the universe
# before the backtest starts (see data_pipeline.first_date_with_min_coverage);
# empirically this lands the effective start around 1995.
MIN_UNIVERSE_SIZE = len(UNIVERSE) // 2

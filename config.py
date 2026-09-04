"""Configuration for the Ranked Asset Allocation strategy backtest."""
from datetime import datetime

# --- Universe -----------------------------------------------------------
# Individual Nifty 100 stocks (not ETFs). Two parts:
#
# 1. CURRENT_NIFTY100: today's 100 constituents, pulled directly from NSE's
#    official list (nsearchives.nseindia.com/content/indices/ind_nifty100list.csv,
#    fetched 2026-09-03) with ".NS" appended.
#
# 2. DELISTED_HISTORICAL: yfinance has no API for historical index membership
#    (which stocks were in Nifty 100 on any given past date), so there is no
#    way to reconstruct exact constituent history. This is a best-effort,
#    NOT exhaustive, NOT precisely-dated list of companies that were
#    large/blue-chip enough to plausibly have been Nifty 100 (or Nifty 50)
#    constituents at their peak, based on public reporting of their market
#    cap and index history, and that later went bankrupt, were delisted, or
#    are now functionally worthless penny stocks:
#      - RCOM.NS, RELCAPITAL.NS  -- Reliance ADAG group (telecom, financial
#        services), both Nifty 50-caliber at peak, later insolvent
#      - JETAIRWAYS.NS  -- Jet Airways, was Nifty 50-listed, grounded 2019
#      - UNITECH.NS, HDIL.NS, GVKPIL.NS  -- 2007-2008 real-estate/infra boom
#        era large-caps
#      - EDUCOMP.NS  -- education-sector large-cap, fraud allegations
#      - ABAN.NS  -- Aban Offshore, was India's largest offshore driller
#      - GTLINFRA.NS, ALOKINDS.NS  -- telecom-tower / textiles large-caps
#    Several other well-known failures (Satyam, Ranbaxy, DHFL, Cairn India,
#    Kingfisher Airlines, Bhushan Steel, Essar Steel, Jaiprakash Associates)
#    were checked but Yahoo Finance has NO price data for them at all
#    (ticker fully purged after delisting/merger) -- they cannot be included
#    from this data source. This means the universe still has some
#    residual survivorship bias; it is reduced, not eliminated.
#
# Other ticker corrections vs. earlier ETF-based version of this file:
#  - PSUBANKBEES.NS -> PSUBNKBEES.NS was an ETF-only fix, no longer relevant
#    now that the universe is individual stocks (kept in git history).
CURRENT_NIFTY100 = [
    "ABB.NS", "ADANIENSOL.NS", "ADANIENT.NS", "ADANIGREEN.NS", "ADANIPORTS.NS",
    "ADANIPOWER.NS", "AMBUJACEM.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", "DMART.NS",
    "AXISBANK.NS", "BAJAJ-AUTO.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "BAJAJHLDNG.NS",
    "BANKBARODA.NS", "BEL.NS", "BPCL.NS", "BHARTIARTL.NS", "BOSCHLTD.NS",
    "BRITANNIA.NS", "CGPOWER.NS", "CANBK.NS", "CHOLAFIN.NS", "CIPLA.NS",
    "COALINDIA.NS", "CUMMINSIND.NS", "DLF.NS", "DIVISLAB.NS", "DRREDDY.NS",
    "EICHERMOT.NS", "ETERNAL.NS", "GAIL.NS", "GODREJCP.NS", "GRASIM.NS",
    "HCLTECH.NS", "HDFCAMC.NS", "HDFCBANK.NS", "HDFCLIFE.NS", "HINDALCO.NS",
    "HAL.NS", "HINDUNILVR.NS", "HINDZINC.NS", "HYUNDAI.NS", "ICICIBANK.NS",
    "ITC.NS", "INDHOTEL.NS", "IOC.NS", "IRFC.NS", "INFY.NS",
    "INDIGO.NS", "JSWSTEEL.NS", "JINDALSTEL.NS", "JIOFIN.NS", "KOTAKBANK.NS",
    "LTM.NS", "LT.NS", "LODHA.NS", "M&M.NS", "MARUTI.NS",
    "MAXHEALTH.NS", "MAZDOCK.NS", "MUTHOOTFIN.NS", "NTPC.NS", "NESTLEIND.NS",
    "ONGC.NS", "PIDILITIND.NS", "PFC.NS", "POWERGRID.NS", "PNB.NS",
    "RECLTD.NS", "RELIANCE.NS", "SBILIFE.NS", "MOTHERSON.NS", "SHREECEM.NS",
    "SHRIRAMFIN.NS", "ENRIN.NS", "SIEMENS.NS", "SOLARINDS.NS", "SBIN.NS",
    "SUNPHARMA.NS", "TVSMOTOR.NS", "TATACAP.NS", "TCS.NS", "TATACONSUM.NS",
    "TMCV.NS", "TMPV.NS", "TATAPOWER.NS", "TATASTEEL.NS", "TECHM.NS",
    "TITAN.NS", "TORNTPHARM.NS", "TRENT.NS", "ULTRACEMCO.NS", "UNIONBANK.NS",
    "UNITDSPR.NS", "VBL.NS", "VEDL.NS", "WIPRO.NS", "ZYDUSLIFE.NS"
]

DELISTED_HISTORICAL = [
    "RCOM.NS", "RELCAPITAL.NS", "JETAIRWAYS.NS", "UNITECH.NS", "HDIL.NS",
    "GVKPIL.NS", "EDUCOMP.NS", "ABAN.NS", "GTLINFRA.NS", "ALOKINDS.NS",
]

# Current Nifty 50 constituents (subset of CURRENT_NIFTY100), same NSE
# official-list source, fetched 2026-09-03. Not the default UNIVERSE --
# used for a narrower-universe comparison check (larger, more liquid
# large-caps only, no delisted names).
NIFTY50 = [
    "ADANIENT.NS", "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "BAJAJ-AUTO.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "BEL.NS", "BHARTIARTL.NS",
    "CIPLA.NS", "COALINDIA.NS", "DRREDDY.NS", "EICHERMOT.NS", "ETERNAL.NS",
    "GRASIM.NS", "HCLTECH.NS", "HDFCBANK.NS", "HDFCLIFE.NS", "HINDALCO.NS",
    "HINDUNILVR.NS", "ICICIBANK.NS", "ITC.NS", "INFY.NS", "INDIGO.NS",
    "JSWSTEEL.NS", "JIOFIN.NS", "KOTAKBANK.NS", "LT.NS", "M&M.NS",
    "MARUTI.NS", "MAXHEALTH.NS", "NTPC.NS", "NESTLEIND.NS", "ONGC.NS",
    "POWERGRID.NS", "RELIANCE.NS", "SBILIFE.NS", "SHRIRAMFIN.NS", "SBIN.NS",
    "SUNPHARMA.NS", "TCS.NS", "TATACONSUM.NS", "TMPV.NS", "TATASTEEL.NS",
    "TECHM.NS", "TITAN.NS", "TRENT.NS", "ULTRACEMCO.NS", "WIPRO.NS",
]

# Kept OUT of UNIVERSE by default. A direct comparison showed these 10 names
# were doing a disproportionate share of the work: Total_Rank IC t-stat was
# 2.92 with them included vs. 1.75 (below the conventional significance bar)
# on CURRENT_NIFTY100 alone. Their extreme, one-off collapse events (RCOM,
# HDIL, JETAIRWAYS, etc. crashing 90%+) are easy for a downside-deviation/
# momentum ranking to "catch" retrospectively, but that's a different, less
# repeatable effect than genuine cross-sectional skill among ordinary
# large-caps -- and it's exactly the kind of result a full-period aggregate
# number can hide. DELISTED_HISTORICAL is kept defined (not deleted) since
# it's still valid, researched survivorship-bias-reduction data; add it back
# via UNIVERSE = CURRENT_NIFTY100 + DELISTED_HISTORICAL if wanted again.
UNIVERSE = CURRENT_NIFTY100

BENCHMARK = "^NSEI"  # Nifty 50 index

# --- Data window ----------------------------------------------------------
# No fixed lookback: pull each ticker's FULL available history from yfinance
# (period="max" in data_pipeline.download_universe). Different ETFs list on
# different dates -- this is what keeps the universe survivorship-bias free,
# each asset simply has no rows before its own inception.
END_DATE = datetime.today()

# --- Local price-data cache -------------------------------------------------
# Raw per-ticker OHLCV is cached to disk (one CSV per ticker) so re-running
# the backtest doesn't re-download ~110 tickers' full history from yfinance
# every time. A cache file is reused if it was written TODAY; otherwise it's
# treated as stale and re-downloaded. Delete CACHE_DIR (or a single ticker's
# file in it) to force a fresh pull.
CACHE_DIR = "data_cache"

# --- Strategy parameters ---------------------------------------------------
# Momentum uses the standard "12-1" construction: a ~12-month formation
# period that SKIPS the most recent ~1 month, since short (~1-month) lookback
# momentum empirically exhibits reversal rather than continuation (this is
# what the plain 22-day ROC used to measure, and it tested at t=-0.02 --
# indistinguishable from noise). MOMENTUM_SKIP=21 (~1 month) is excluded from
# the end of the window; MOMENTUM_WINDOW=231 is the formation length, so the
# total lookback (skip + window) is 252 trading days (~12 months).
MOMENTUM_WINDOW = 231
MOMENTUM_SKIP = 21

# Only used by yang_zhang_volatility/downside_deviation, which are no
# longer in the active pipeline (replaced by idiosyncratic_volatility below,
# see BETA_WINDOW) -- kept for reference. A lengthened-window experiment
# (63 days, to better match REBALANCE_FREQ="QE") was tried and reverted: it
# made Rank_V's IC WORSE, not better (t=0.80 -> 0.50), so 10 is intentional,
# not a leftover default.
VOLATILITY_WINDOW = 10
VOLUME_FAST = 10
VOLUME_SLOW = 22

# Beta / idiosyncratic-volatility factors (Frazzini-Pedersen "Betting
# Against Beta"; Ang-Hodrick-Xing-Zhang idiosyncratic vol). 252 trading days
# (~1 year) rolling window against Nifty 50 -- these are risk-regime
# characteristics, not short-term signals, so they need a substantially
# longer window than the price/volume factors above to be estimated
# reliably; a beta estimated over 10-63 days is mostly noise.
BETA_WINDOW = 252

W1, W2, W3 = 0.3, 0.3, 0.3  # weight on Rank_M, Rank_V, Rank_VC
X = 10                        # divisor for the M/x tiebreak term

TOP_N = 10                 # number of assets held at a time

# Rebalance cadence (pandas resample rule: "ME"=month-end, "QE"=quarter-end).
# Was monthly ("ME"). A weak-but-real factor combo (Total_Rank IC t~3.9) still
# lost to Nifty 50 net of costs/tax because near-total monthly reranking of a
# tiny N-stock book generates enormous turnover -- almost every gain realized
# within a year, taxed at the 20% STCG rate instead of 12.5% LTCG, on top of
# brokerage/STT/stamp/GST on both legs of every swap. Quarterly cuts the
# number of rebalance events (and the taxable events + txn costs that come
# with them) to a third of monthly, while still reacting to the ranking
# signal every 3 months.
REBALANCE_FREQ = "QE"

# Hysteresis / buffer zone (the rule real index committees like S&P/Russell
# use to limit reconstitution churn): a NEW asset must rank in the top TOP_N
# to be added, but an asset ALREADY held is only dropped once its rank falls
# outside the top (TOP_N + HYSTERESIS_BUFFER). Without this, marginal/noisy
# rank jitter right around the TOP_N cutoff forces a full swap every
# rebalance even when the "new" pick isn't meaningfully better than what's
# already held -- exactly the kind of unnecessary turnover that was eating
# the strategy's edge. See factors.hysteresis_membership.
HYSTERESIS_BUFFER = 5

# --- Data cleaning ----------------------------------------------------------
# Winsorize daily simple returns at the 0.1th / 99.9th percentile per asset
# to suppress fabricated tail events (data errors / stale-price jumps),
# while leaving genuine (but not absurd) tail risk intact.
WINSOR_LOWER_PCTL = 0.001
WINSOR_UPPER_PCTL = 0.999

# A fixed, data-independent backstop on the winsorization bound (NOT derived
# from any observed return, so it introduces no look-ahead information).
# The 0.1th/99.9th percentile of a few thousand daily observations is
# inherently a noisy estimate (it is effectively interpolating between the
# 2nd/3rd most extreme values ever seen), so an expanding-window quantile
# alone can still be too wide to catch an extreme multi-day data-vendor
# glitch (e.g. the 2019-12-19/20 Yahoo Finance glitch found in the ETF
# universe) even well past its warm-up period.
#
# Individual stocks are far more volatile than the diversified ETFs this cap
# was originally tuned for (0.35): most Nifty 100 names are F&O-eligible and
# so have NO daily circuit/price-band limit, and genuine single-day moves of
# 20-40%+ do happen around real events (e.g. the Adani group stocks during
# the Jan-2023 Hindenburg report, distressed penny-stock names like RCOM/
# HDIL/EDUCOMP swinging on tiny absolute prices). Set high enough to never
# clip a real single-stock event, while still catching a >90%-magnitude data
# glitch.
WINSOR_ABS_RETURN_CAP = 0.65

# NSE Diwali "Muhurat Trading" sessions: a ~1hr symbolic session on an
# otherwise-closed day. Volume is a tiny fraction of normal days and prices
# can gap in a way that distorts the Volume-Confirmation and Volatility
# factors, so these calendar dates are dropped entirely from the raw data.
MUHURAT_TRADING_DATES = [
    "2002-11-04", "2003-10-25", "2004-11-12",
    "2005-11-01", "2006-10-21", "2007-11-09", "2008-10-28", "2009-10-17",
    "2010-11-05", "2011-10-26", "2012-11-13", "2013-11-03", "2014-10-23",
    "2015-11-11", "2016-10-30", "2017-10-19", "2018-11-07", "2019-10-27",
    "2020-11-14", "2021-11-04", "2022-10-24", "2023-11-12",
    "2024-11-01", "2025-10-21",
]

# --- Train / validation / test split (chronological, by calendar date) -----
TRAIN_FRAC = 0.6
VAL_FRAC = 0.2
TEST_FRAC = 0.2

# --- Indian equity-delivery trading cost & tax assumptions ------------------
# All positions are traded delivery-style (T+1 settlement, no intraday
# leverage), so the standard "delivery" cost stack applies. Rates below reflect the
# post-2024-budget schedule for a discount broker; documented individually
# so any single assumption can be tuned without touching the engine.
COSTS = {
    "brokerage_pct": 0.0003,        # 0.03% per side (discount broker; many charge flat Rs20/order-whichever-lower, ignored here)
    "stt_pct": 0.001,               # Securities Transaction Tax: 0.1% on delivery buy AND sell
    "exchange_txn_pct": 0.0000297,  # NSE transaction charges
    "sebi_fee_pct": 0.0000001,      # SEBI turnover fee (Rs10/crore)
    "stamp_duty_pct": 0.00015,      # stamp duty, buy side only, 0.015%
    "gst_pct": 0.18,                # GST on (brokerage + exchange txn charges)
    "dp_charge_flat": 15.0,         # flat DP (depository) charge per scrip on sell, INR
    "stcg_rate": 0.20,              # short-term capital gains tax (holding <= 365 days), post-Jul-2024
    "ltcg_rate": 0.125,             # long-term capital gains tax (holding > 365 days), post-Jul-2024
    "ltcg_exemption": 125000.0,     # annual LTCG exemption, INR (applied approximately, see backtest.py)
}

INITIAL_CAPITAL = 10_000_000.0  # INR 1 crore notional

# --- Market impact / slippage -----------------------------------------------
# Audit finding: no slippage model existed at all -- every trade executed at
# the exact quoted price regardless of size. Checked against real ADTV: a
# single TOP_N position at the backtest's ending NAV was ~10% of a day's
# volume for the least-liquid current constituents, large enough that real
# execution would move the price. Modeled with the standard square-root
# market-impact form (see liquidity.py): slippage_pct = SLIPPAGE_COEF *
# sqrt(trade_value / trailing_60d_ADTV), capped at SLIPPAGE_MAX_PCT.
# SLIPPAGE_COEF=0.01 is a rough, disclosed calibration (not fit to Indian
# market microstructure data, which isn't available here) -- treat the
# resulting numbers as "plausible order of magnitude," not precise.
SLIPPAGE_COEF = 0.01
SLIPPAGE_MAX_PCT = 0.05

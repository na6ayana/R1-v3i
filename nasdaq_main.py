"""Run the ranked-allocation strategy end to end on Nasdaq-100 stocks.

A direct port of main.py's pipeline onto nasdaq_config's universe/costs/
benchmark -- same factors.py/backtest.py/metrics.py/ic_analysis.py/
liquidity.py engine, same strategy parameters (see nasdaq_config.py's
docstring: this tests whether the design travels, it does not re-tune it
for the US market).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import nasdaq_config as config
import data_pipeline as dp
import factors
import backtest
import metrics
import ic_analysis
import liquidity

OUT_DIR = "output_nasdaq"


def load_and_clean():
    print("Downloading Nasdaq-100 universe data from yfinance...")
    raw = dp.download_universe(config.UNIVERSE, cache_dir=config.CACHE_DIR)
    print("Cleaning: winsorizing return tails (no Muhurat-day equivalent for US markets)...")
    cleaned = dp.clean_data(raw, muhurat_dates=config.MUHURAT_TRADING_DATES,
                             winsor_abs_cap=config.WINSOR_ABS_RETURN_CAP)
    panels = dp.build_price_panels(cleaned)
    return panels


def compute_signal(panels, benchmark_series):
    print("Computing factors: Momentum, Idiosyncratic Volatility, Volume Confirmation...")
    m = factors.momentum(panels["Close"], window=config.MOMENTUM_WINDOW, skip=config.MOMENTUM_SKIP)
    # Same sign-flip as the Indian pipeline (favor HIGH idiosyncratic vol,
    # not low) -- ported as-is; NOT re-validated by a fresh IC test on this
    # market before being applied. That re-validation is exactly what
    # running this module and reading its own IC table is for.
    v = -factors.idiosyncratic_volatility(panels["Close"], benchmark_series, window=config.BETA_WINDOW)
    vc = factors.volume_confirmation(panels["Close"], panels["Volume"],
                                      fast=config.VOLUME_FAST, slow=config.VOLUME_SLOW)

    total_rank_d = factors.total_rank_daily(m, v, vc, w1=config.W1, w2=config.W2, w3=config.W3, x=config.X)
    rebalance_rank = factors.resample_total_rank(total_rank_d, freq=config.REBALANCE_FREQ)
    rebalance_membership = factors.hysteresis_membership(rebalance_rank, top_n=config.TOP_N,
                                                           buffer=config.HYSTERESIS_BUFFER)
    rebalance_weights = backtest.build_signal_weights(rebalance_membership)

    rank_m, rank_v, rank_vc = factors.cross_sectional_ranks(m, v, vc)
    factor_snapshots = {
        "Rank_M": rank_m.resample(config.REBALANCE_FREQ).last(),
        "Rank_V": rank_v.resample(config.REBALANCE_FREQ).last(),
        "Rank_VC": rank_vc.resample(config.REBALANCE_FREQ).last(),
        "Total_Rank": rebalance_rank,
    }
    return rebalance_weights, factor_snapshots


def run_period(panels, full_daily_weights, adtv_px, dates, label):
    close_px = panels["Close"].loc[dates]
    open_px = panels["Open"].loc[dates]
    adtv_slice = adtv_px.loc[dates]
    daily_w = full_daily_weights.loc[dates]
    result = backtest.run_backtest(open_px, close_px, daily_w, adtv_px=adtv_slice,
                                    initial_capital=config.INITIAL_CAPITAL,
                                    cost_config=config.COSTS, fy_start_month=config.FY_START_MONTH)
    s = metrics.summary(result["nav"], label, rf_annual=config.RF_ANNUAL)
    metrics.print_summary(s)
    return result, s


def get_benchmark_series(ticker=None):
    ticker = ticker or config.BENCHMARK
    raw = dp.download_universe([ticker], cache_dir=config.CACHE_DIR)
    cleaned = dp.clean_data(raw, muhurat_dates=config.MUHURAT_TRADING_DATES,
                             winsor_abs_cap=config.WINSOR_ABS_RETURN_CAP)
    return cleaned[ticker]["Close"]


def plot_cumulative(strategy_nav: pd.Series, benchmark_close: pd.Series, benchmark_label: str,
                     path: str, title: str):
    strat_cum = strategy_nav / strategy_nav.iloc[0]
    bench_cum = benchmark_close / benchmark_close.dropna().iloc[0]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(strat_cum.index, strat_cum.values, label="Ranked Allocation Strategy (net of costs & tax)", linewidth=1.5)
    ax.plot(bench_cum.index, bench_cum.values, label=benchmark_label, linewidth=1.5, alpha=0.8)
    ax.set_title(title)
    ax.set_ylabel("Growth of 1")
    ax.set_xlabel("Date")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved plot: {path}")


def plot_ic_summary(ic_summary: pd.DataFrame, path: str):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    factors_ = ic_summary.index.tolist()
    means = ic_summary["mean_ic"].values
    colors = ["#2a9d8f" if m >= 0 else "#e76f51" for m in means]
    bars = ax.bar(factors_, means, color=colors)
    for bar, (_, row) in zip(bars, ic_summary.iterrows()):
        y = bar.get_height()
        offset = 0.001 if y >= 0 else -0.001
        va = "bottom" if y >= 0 else "top"
        ax.text(bar.get_x() + bar.get_width() / 2, y + offset,
                f"t={row['t_stat']:.2f}", ha="center", va=va, fontsize=9)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Mean quarterly IC (Spearman)")
    ax.set_title("Nasdaq-100 Factor IC Summary (mean IC, annotated with t-stat)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved plot: {path}")


def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    panels = load_and_clean()

    print("\nDetermining benchmark (Nasdaq-100 index) start date to cap the backtest window...")
    benchmark_series = get_benchmark_series()
    benchmark_start = benchmark_series.dropna().index.min()
    print(f"  {config.BENCHMARK} data starts {benchmark_start.date()} -- backtest will not start earlier than this.")

    rebalance_weights, factor_snapshots = compute_signal(panels, benchmark_series)

    min_coverage_start = dp.first_date_with_min_coverage(panels["Close"], config.MIN_UNIVERSE_SIZE)
    print(f"  At least {config.MIN_UNIVERSE_SIZE}/{len(config.UNIVERSE)} current constituents have data "
          f"from {min_coverage_start.date()} onward -- backtest will not start earlier than this either "
          f"(most of today's Nasdaq-100 didn't exist before the mid-1990s).")

    all_dates = panels["Close"].index
    warmup = max(config.MOMENTUM_SKIP + config.MOMENTUM_WINDOW, config.BETA_WINDOW, config.VOLUME_SLOW) + 5
    usable_dates = all_dates[warmup:]
    usable_dates = usable_dates[usable_dates >= benchmark_start]
    usable_dates = usable_dates[usable_dates >= min_coverage_start]

    # Same bug found and fixed on the Indian side: idiosyncratic vol/beta
    # need BETA_WINDOW days of the BENCHMARK's own history, which can bind
    # later than the universe-coverage gate above. Belt-and-suspenders --
    # ^NDX has data back to 1985 so this doesn't end up binding here (the
    # coverage gate above is already later), but check explicitly rather
    # than assume.
    min_rank_coverage_start = dp.first_date_with_min_coverage(factor_snapshots["Total_Rank"], config.TOP_N)
    print(f"  Total_Rank has >= {config.TOP_N} valid candidates from {min_rank_coverage_start.date()} onward.")
    usable_dates = usable_dates[usable_dates >= min_rank_coverage_start]

    train, val, test = dp.split_dates(usable_dates)

    print("\n================ FACTOR IC ANALYSIS (NASDAQ-100) ================\n")
    print(f"Cross-sectional Spearman rank-IC ({config.REBALANCE_FREQ} rebalance cadence) between")
    print("each factor's rank at a rebalance date and the asset's forward return to the")
    print(f"NEXT rebalance date, restricted to the same window as the backtest")
    print(f"({usable_dates[0].date()} to {usable_dates[-1].date()}):\n")
    windowed_snapshots = {
        name: snap[(snap.index >= usable_dates[0]) & (snap.index <= usable_dates[-1])]
        for name, snap in factor_snapshots.items()
    }
    ic_series_by_factor, ic_summary = ic_analysis.run_ic_analysis(panels["Close"], windowed_snapshots)
    ic_analysis.print_ic_table(ic_summary)
    ic_summary.to_csv(f"{OUT_DIR}/ic_analysis.csv")
    print(f"\nSaved IC table: {OUT_DIR}/ic_analysis.csv")
    plot_ic_summary(ic_summary, f"{OUT_DIR}/ic_summary.png")

    full_daily_weights = backtest.daily_target_weights(rebalance_weights, usable_dates)
    adtv_px = liquidity.average_daily_traded_value(panels["Close"], panels["Volume"])

    print("\n================ BACKTEST RESULTS (NASDAQ-100) ================\n")
    results = {}
    summaries = []
    for label, dates in [("Train (60%)", train), ("Validation (20%)", val), ("Test (20%)", test), ("Full Period", usable_dates)]:
        res, s = run_period(panels, full_daily_weights, adtv_px, dates, label)
        results[label] = res
        summaries.append(s)
        print()

    summary_df = pd.DataFrame(summaries).set_index("period")
    summary_df.to_csv(f"{OUT_DIR}/performance_summary.csv")
    print(f"Saved metrics table: {OUT_DIR}/performance_summary.csv")

    full_result = results["Full Period"]
    full_result.to_csv(f"{OUT_DIR}/daily_nav_full_period.csv")

    bm_close = benchmark_series.reindex(full_result.index).ffill()
    plot_cumulative(full_result["nav"], bm_close, "Nasdaq-100",
                     f"{OUT_DIR}/cumulative_returns.png",
                     "Cumulative Returns: Strategy vs. Nasdaq-100")

    bm_summary = metrics.summary(bm_close.dropna(), "Nasdaq-100 Benchmark (Full Period)", rf_annual=config.RF_ANNUAL)
    metrics.print_summary(bm_summary)
    pd.DataFrame([bm_summary]).set_index("period").to_csv(f"{OUT_DIR}/benchmark_summary.csv")

    total_costs = full_result["cost"].sum()
    total_slippage = full_result["slippage"].sum()
    total_taxes = full_result["tax"].sum()
    print(f"\nTotal transaction costs over full period: USD {total_costs:,.0f}")
    print(f"Total slippage (market impact) over full period: USD {total_slippage:,.0f}")
    print(f"Total capital-gains tax over full period : USD {total_taxes:,.0f}")


if __name__ == "__main__":
    main()

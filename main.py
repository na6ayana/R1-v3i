"""Run the ranked-asset-allocation backtest end to end."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config
import data_pipeline as dp
import factors
import backtest
import metrics
import ic_analysis

OUT_DIR = "output"


def load_and_clean():
    print("Downloading universe data from yfinance...")
    raw = dp.download_universe(config.UNIVERSE)
    print("Cleaning: dropping Muhurat-trading days, winsorizing return tails...")
    cleaned = dp.clean_data(raw)
    panels = dp.build_price_panels(cleaned)
    return panels


def compute_signal(panels):
    print("Computing factors: Momentum, Downside Deviation, Volume Confirmation...")
    m = factors.momentum(panels["Close"])
    v = factors.downside_deviation(panels["Close"])
    vc = factors.volume_confirmation(panels["Close"], panels["Volume"])

    total_rank_d = factors.total_rank_daily(m, v, vc)
    rebalance_rank = factors.resample_total_rank(total_rank_d)
    rebalance_membership = factors.hysteresis_membership(rebalance_rank)
    rebalance_weights = backtest.build_signal_weights(rebalance_membership)

    # Rebalance-period snapshots of each sub-rank, for IC analysis -- same
    # construction/cadence as Total_Rank, so "does this sub-factor's rank
    # predict the NEXT rebalance period's return" can be checked individually
    # and against the combined score.
    rank_m, rank_v, rank_vc = factors.cross_sectional_ranks(m, v, vc)
    factor_snapshots = {
        "Rank_M": rank_m.resample(config.REBALANCE_FREQ).last(),
        "Rank_V": rank_v.resample(config.REBALANCE_FREQ).last(),
        "Rank_VC": rank_vc.resample(config.REBALANCE_FREQ).last(),
        "Total_Rank": rebalance_rank,
    }
    return rebalance_weights, factor_snapshots


def run_period(panels, full_daily_weights, dates, label):
    close_px = panels["Close"].loc[dates]
    open_px = panels["Open"].loc[dates]
    # Slice the ALREADY ffill+shifted full-history weight frame, rather than
    # recomputing ffill+shift on just this period's dates -- recomputing on a
    # sub-slice would wipe out row 0's true (carried-over) signal via shift(1)
    # and force a spurious cash reset at the start of Validation/Test.
    daily_w = full_daily_weights.loc[dates]
    result = backtest.run_backtest(open_px, close_px, daily_w)
    s = metrics.summary(result["nav"], label)
    metrics.print_summary(s)
    return result, s


def get_benchmark_series(ticker=None):
    """Fetch a benchmark's full history and run it through the SAME cleaning
    pipeline (Muhurat-day drop, winsorization) as the strategy universe --
    a raw yf.download is vulnerable to the same vendor data glitches found
    in the strategy data (e.g. GOLDBEES.NS's 2019-12-19/20 ~99% single-day
    move was a known Yahoo Finance data bug, not a real price move)."""
    ticker = ticker or config.BENCHMARK
    raw = dp.download_universe([ticker])
    cleaned = dp.clean_data(raw)
    return cleaned[ticker]["Close"]


def get_benchmark(dates, ticker=None):
    return get_benchmark_series(ticker).reindex(dates).ffill()


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
    """Bar chart of mean monthly IC per factor, annotated with its t-stat.
    A dashed line at |t|=2 marks the conventional "significant" threshold."""
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
    ax.set_ylabel("Mean monthly IC (Spearman)")
    ax.set_title("Factor IC Summary (mean IC, annotated with t-stat)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved plot: {path}")


def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    panels = load_and_clean()
    rebalance_weights, factor_snapshots = compute_signal(panels)

    print("\nDetermining benchmark (Nifty 50) start date to cap the backtest window...")
    benchmark_series = get_benchmark_series()
    benchmark_start = benchmark_series.dropna().index.min()
    print(f"  Nifty 50 data starts {benchmark_start.date()} -- backtest will not start earlier than this.")

    all_dates = panels["Close"].index
    # warm up: need MOMENTUM_SKIP+MOMENTUM_WINDOW / VOLATILITY_WINDOW / VOLUME_SLOW
    # history before factors are valid (momentum needs the longest lookback:
    # skip + window days, not just window days).
    warmup = max(config.MOMENTUM_SKIP + config.MOMENTUM_WINDOW, config.VOLATILITY_WINDOW, config.VOLUME_SLOW) + 5
    usable_dates = all_dates[warmup:]
    # Cap the start so every period actually has a benchmark to compare against
    # (yfinance's ^NSEI history starts well after some of the older stocks').
    usable_dates = usable_dates[usable_dates >= benchmark_start]

    train, val, test = dp.split_dates(usable_dates)

    print("\n================ FACTOR IC ANALYSIS ================\n")
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

    # Build the full-history daily weight signal ONCE (ffill + one-day shift
    # over the entire usable calendar) so period slices below inherit
    # whatever signal was genuinely live at their start, instead of each
    # slice re-deriving its own (incorrect) cold start.
    full_daily_weights = backtest.daily_target_weights(rebalance_weights, usable_dates)

    print("\n================ BACKTEST RESULTS ================\n")
    results = {}
    summaries = []
    for label, dates in [("Train (60%)", train), ("Validation (20%)", val), ("Test (20%)", test), ("Full Period", usable_dates)]:
        res, s = run_period(panels, full_daily_weights, dates, label)
        results[label] = res
        summaries.append(s)
        print()

    summary_df = pd.DataFrame(summaries).set_index("period")
    summary_df.to_csv(f"{OUT_DIR}/performance_summary.csv")
    print(f"Saved metrics table: {OUT_DIR}/performance_summary.csv")

    full_result = results["Full Period"]
    full_result.to_csv(f"{OUT_DIR}/daily_nav_full_period.csv")

    bm_close = benchmark_series.reindex(full_result.index).ffill()
    plot_cumulative(full_result["nav"], bm_close, "Nifty 50",
                     f"{OUT_DIR}/cumulative_returns.png",
                     "Cumulative Returns: Strategy vs. Nifty 50")

    bm_summary = metrics.summary(bm_close.dropna(), "Nifty 50 Benchmark (Full Period)")
    metrics.print_summary(bm_summary)
    pd.DataFrame([bm_summary]).set_index("period").to_csv(f"{OUT_DIR}/benchmark_summary.csv")

    print("\nDownloading GOLDBEES.NS for comparison (not part of the stock universe)...")
    gold_close = get_benchmark(full_result.index, ticker="GOLDBEES.NS")
    plot_cumulative(full_result["nav"], gold_close, "GOLDBEES.NS",
                     f"{OUT_DIR}/cumulative_returns_vs_goldbees.png",
                     "Cumulative Returns: Strategy vs. GOLDBEES.NS")
    gold_summary = metrics.summary(gold_close.dropna(), "GOLDBEES.NS (Full Period)")
    metrics.print_summary(gold_summary)
    pd.DataFrame([gold_summary]).set_index("period").to_csv(f"{OUT_DIR}/goldbees_summary.csv")

    total_costs = full_result["cost"].sum()
    total_taxes = full_result["tax"].sum()
    print(f"\nTotal transaction costs over full period: INR {total_costs:,.0f}")
    print(f"Total capital-gains tax over full period : INR {total_taxes:,.0f}")


if __name__ == "__main__":
    main()

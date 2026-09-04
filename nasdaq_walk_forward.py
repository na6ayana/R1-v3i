"""Walk-forward / out-of-sample robustness check for the Nasdaq-100 module.

Direct port of walk_forward.py's methodology onto nasdaq_main/nasdaq_config
-- see that file's docstring for what this does and does not test (same
caveats apply: daily execution is causal, but the strategy DESIGN was
arrived at by iterating on Indian data, then ported here unchanged. This
walk-forward tests whether the ported design holds up out-of-sample on
THIS market, not whether the original design process was sound).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import nasdaq_config as config
import data_pipeline as dp
import backtest
import metrics
import ic_analysis
import liquidity
import nasdaq_main as m

OUT_DIR = m.OUT_DIR


def chronological_folds(dates: pd.DatetimeIndex, n_folds: int):
    edges = np.linspace(0, len(dates), n_folds + 1, dtype=int)
    return [dates[edges[i]:edges[i + 1]] for i in range(n_folds)]


def run_fold(panels, full_daily_weights, adtv_px, benchmark_series, fold_dates, label):
    close_px = panels["Close"].loc[fold_dates]
    open_px = panels["Open"].loc[fold_dates]
    daily_w = full_daily_weights.loc[fold_dates]
    adtv_slice = adtv_px.loc[fold_dates]
    result = backtest.run_backtest(open_px, close_px, daily_w, adtv_px=adtv_slice,
                                    initial_capital=config.INITIAL_CAPITAL,
                                    cost_config=config.COSTS, fy_start_month=config.FY_START_MONTH)
    s = metrics.summary(result["nav"], label, rf_annual=config.RF_ANNUAL)

    bm_seg = benchmark_series.reindex(fold_dates).ffill().dropna()
    bm_cagr = metrics.cagr(bm_seg) * 100 if len(bm_seg) > 1 else float("nan")
    bm_sharpe = metrics.sharpe_ratio(metrics.daily_returns(bm_seg), config.RF_ANNUAL) if len(bm_seg) > 1 else float("nan")

    return {
        "fold": label,
        "start": fold_dates[0].date(),
        "end": fold_dates[-1].date(),
        "strategy_cagr_pct": s["cagr_pct"],
        "strategy_sharpe": s["sharpe"],
        "strategy_maxdd_pct": s["max_drawdown_pct"],
        "bench_cagr_pct": bm_cagr,
        "bench_sharpe": bm_sharpe,
        "beat_bench": s["cagr_pct"] > bm_cagr,
    }


def rolling_ic(ic_series: pd.Series, window: int):
    out = {}
    for i in range(window, len(ic_series) + 1):
        chunk = ic_series.iloc[i - window:i]
        d = ic_series.index[i - 1]
        mean_ic = chunk.mean()
        std_ic = chunk.std(ddof=1)
        t_stat = mean_ic / (std_ic / np.sqrt(window)) if std_ic > 0 else np.nan
        out[d] = (mean_ic, t_stat)
    return pd.DataFrame(out, index=["mean_ic", "t_stat"]).T


def plot_folds(fold_df: pd.DataFrame, path: str):
    fig, ax = plt.subplots(figsize=(11, 6))
    x = np.arange(len(fold_df))
    width = 0.35
    colors_strat = ["#2a9d8f" if b else "#e76f51" for b in fold_df["beat_bench"]]
    ax.bar(x - width / 2, fold_df["strategy_cagr_pct"], width, color=colors_strat, label="Strategy")
    ax.bar(x + width / 2, fold_df["bench_cagr_pct"], width, color="#888888", label="Nasdaq-100")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{row['fold']}\n{row['start']} to {row['end']}" for _, row in fold_df.iterrows()],
                        fontsize=8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("CAGR (%) within fold")
    ax.set_title("Walk-Forward: Strategy vs. Nasdaq-100 CAGR per Chronological Fold\n(green = strategy beat Nasdaq-100 in that fold, red = did not)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved plot: {path}")


def plot_rolling_ic(roll: pd.DataFrame, window: int, path: str):
    fig, ax1 = plt.subplots(figsize=(11, 6))
    ax1.plot(roll.index, roll["mean_ic"], color="#457b9d", linewidth=1.5, label="Rolling mean IC")
    ax1.axhline(0, color="black", linewidth=0.8)
    ax1.set_ylabel("Rolling mean IC (Spearman)", color="#457b9d")
    ax1.set_xlabel("Date")

    ax2 = ax1.twinx()
    ax2.plot(roll.index, roll["t_stat"], color="#e76f51", linewidth=1.2, linestyle="--", label="Rolling t-stat")
    ax2.axhline(2, color="#e76f51", linewidth=0.8, linestyle=":", alpha=0.7)
    ax2.axhline(-2, color="#e76f51", linewidth=0.8, linestyle=":", alpha=0.7)
    ax2.set_ylabel("Rolling t-stat", color="#e76f51")

    ax1.set_title(f"Nasdaq-100 Total_Rank: {window}-quarter Rolling IC and t-stat Over Time\n(dotted lines mark |t|=2)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved plot: {path}")


def main(n_folds=5, rolling_window=12):
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    panels = m.load_and_clean()

    benchmark_series = m.get_benchmark_series()
    benchmark_start = benchmark_series.dropna().index.min()

    rebalance_weights, factor_snapshots = m.compute_signal(panels, benchmark_series)

    min_coverage_start = dp.first_date_with_min_coverage(panels["Close"], config.MIN_UNIVERSE_SIZE)

    all_dates = panels["Close"].index
    warmup = max(config.MOMENTUM_SKIP + config.MOMENTUM_WINDOW, config.BETA_WINDOW, config.VOLUME_SLOW) + 5
    usable_dates = all_dates[warmup:]
    usable_dates = usable_dates[usable_dates >= benchmark_start]
    usable_dates = usable_dates[usable_dates >= min_coverage_start]
    min_rank_coverage_start = dp.first_date_with_min_coverage(factor_snapshots["Total_Rank"], config.TOP_N)
    usable_dates = usable_dates[usable_dates >= min_rank_coverage_start]

    full_daily_weights = backtest.daily_target_weights(rebalance_weights, usable_dates)
    adtv_px = liquidity.average_daily_traded_value(panels["Close"], panels["Volume"])

    print(f"\n================ WALK-FORWARD (NASDAQ-100): {n_folds} CHRONOLOGICAL FOLDS ================\n")
    folds = chronological_folds(usable_dates, n_folds)
    fold_rows = []
    for i, fold_dates in enumerate(folds, 1):
        row = run_fold(panels, full_daily_weights, adtv_px, benchmark_series, fold_dates, f"Fold {i}")
        fold_rows.append(row)
        verdict = "BEAT" if row["beat_bench"] else "trailed"
        print(f"  Fold {i} ({row['start']} to {row['end']}): "
              f"strategy CAGR {row['strategy_cagr_pct']:6.2f}% / Sharpe {row['strategy_sharpe']:5.2f}  "
              f"vs Nasdaq-100 CAGR {row['bench_cagr_pct']:6.2f}% / Sharpe {row['bench_sharpe']:5.2f}  -> {verdict}")

    fold_df = pd.DataFrame(fold_rows)
    fold_df.to_csv(f"{OUT_DIR}/walk_forward_folds.csv", index=False)
    print(f"\nSaved: {OUT_DIR}/walk_forward_folds.csv")
    plot_folds(fold_df, f"{OUT_DIR}/walk_forward_folds.png")

    n_beat = fold_df["beat_bench"].sum()
    print(f"\nStrategy beat Nasdaq-100 in {n_beat}/{n_folds} independent chronological folds.")

    print(f"\n================ ROLLING IC ({rolling_window}-QUARTER WINDOW) ================\n")
    total_rank_snapshot = factor_snapshots["Total_Rank"]
    total_rank_windowed = total_rank_snapshot[(total_rank_snapshot.index >= usable_dates[0]) &
                                               (total_rank_snapshot.index <= usable_dates[-1])]
    fwd_ret = ic_analysis.forward_returns(panels["Close"], total_rank_windowed.index)
    ic_series = ic_analysis.compute_ic_series(total_rank_windowed, fwd_ret)

    if len(ic_series) <= rolling_window:
        print(f"  Not enough rebalance periods ({len(ic_series)}) for a {rolling_window}-period rolling window; skipping.")
    else:
        roll = rolling_ic(ic_series, rolling_window)
        roll.to_csv(f"{OUT_DIR}/walk_forward_rolling_ic.csv")
        print(f"Saved: {OUT_DIR}/walk_forward_rolling_ic.csv")
        plot_rolling_ic(roll, rolling_window, f"{OUT_DIR}/walk_forward_rolling_ic.png")

        frac_positive = (roll["mean_ic"] > 0).mean() * 100
        frac_significant = (roll["t_stat"].abs() > 2).mean() * 100
        print(f"\nRolling mean IC was positive in {frac_positive:.0f}% of the rolling windows.")
        print(f"Rolling t-stat exceeded |t|=2 in {frac_significant:.0f}% of the rolling windows.")

    return fold_df


if __name__ == "__main__":
    main()

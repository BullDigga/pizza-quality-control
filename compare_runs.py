"""Сводная таблица всех экспериментов (этап 4: исследование гиперпараметров).

Собирает runs/*/results.csv + runs/*/args.yaml в единую таблицу
metrics/experiments_summary.csv и график metrics/experiments_comparison.png.

Запуск: python compare_runs.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # без экрана
import matplotlib.pyplot as plt
import pandas as pd
import yaml

RUNS_DIR = Path("runs")
METRICS_DIR = Path("metrics")
# Какие гиперпараметры тащим в сводную таблицу из args.yaml
HYPER_KEYS = ("model", "epochs", "imgsz", "batch", "lr0", "optimizer",
              "mosaic", "mixup", "hsv_h", "hsv_s", "hsv_v",
              "degrees", "flipud", "fliplr")
RESULT_KEYS = {"metrics/precision(B)": "precision",
               "metrics/recall(B)": "recall",
               "metrics/mAP50(B)": "mAP50",
               "metrics/mAP50-95(B)": "mAP50-95"}


def collect() -> pd.DataFrame:
    rows = []
    for results_csv in sorted(RUNS_DIR.glob("**/results.csv")):
        run_dir = results_csv.parent
        df = pd.read_csv(results_csv)
        df.columns = [c.strip() for c in df.columns]
        if "metrics/mAP50-95(B)" not in df.columns:
            continue
        # Лучшая эпоха по mAP50-95
        best_row = df.loc[df["metrics/mAP50-95(B)"].idxmax()]
        row: dict = {"experiment": run_dir.name, "best_epoch": int(best_row["epoch"]) + 1}
        for src, dst in RESULT_KEYS.items():
            row[dst] = round(float(best_row[src]), 4)
        args_file = run_dir / "args.yaml"
        if args_file.exists():
            saved = yaml.safe_load(args_file.read_text(encoding="utf-8")) or {}
            for key in HYPER_KEYS:
                value = saved.get(key)
                if isinstance(value, Path):
                    value = value.name
                row[key] = value
        rows.append(row)
    return pd.DataFrame(rows)


def plot(summary: pd.DataFrame, out_png: Path) -> None:
    fig, ax = plt.subplots(figsize=(max(8, 1.2 * len(summary)), 5))
    x = range(len(summary))
    width = 0.35
    ax.bar([i - width / 2 for i in x], summary["mAP50"], width, label="mAP@0.5")
    ax.bar([i + width / 2 for i in x], summary["mAP50-95"], width, label="mAP@0.5:0.95")
    ax.set_xticks(list(x))
    ax.set_xticklabels(summary["experiment"], rotation=20, ha="right")
    ax.set_ylabel("mAP")
    ax.set_title("Сравнение экспериментов")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    for i, (v1, v2) in enumerate(zip(summary["mAP50"], summary["mAP50-95"])):
        ax.text(i - width / 2, v1 + 0.005, f"{v1:.3f}", ha="center", fontsize=8)
        ax.text(i + width / 2, v2 + 0.005, f"{v2:.3f}", ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def main() -> None:
    if not RUNS_DIR.exists():
        raise SystemExit("Нет каталога runs/ — сначала обучите модель (train.py)")
    summary = collect()
    if summary.empty:
        raise SystemExit("В runs/ не найдено результатов обучения")

    METRICS_DIR.mkdir(exist_ok=True)
    csv_path = METRICS_DIR / "experiments_summary.csv"
    summary.to_csv(csv_path, index=False, encoding="utf-8")

    png_path = METRICS_DIR / "experiments_comparison.png"
    plot(summary, png_path)

    print(summary.to_string(index=False))
    print(f"\nСохранено: {csv_path} и {png_path}")


if __name__ == "__main__":
    main()

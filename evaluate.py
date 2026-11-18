"""Оценка метрик обученной модели на тестовой выборке.

Сохраняет в metrics/<имя>/:
- summary.csv  — общие Precision, Recall, mAP@0.5, mAP@0.5:0.95;
- per_class.csv — те же метрики по каждому классу (таблица для отчётов);
- confusion_matrix.png, PR_curve.png, results.png — копии графиков из runs/.

Запуск:
    python evaluate.py                          # weights/best.pt
    python evaluate.py --weights runs/exp02/weights/best.pt
    python evaluate.py --runs all               # все runs/* по очереди
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

METRIC_KEYS = ("metrics/precision(B)", "metrics/recall(B)",
               "metrics/mAP50(B)", "metrics/mAP50-95(B)")


def evaluate(weights: Path, data: Path, out_root: Path, name: str | None = None) -> None:
    if name is None:
        if weights.parent.name == "weights" and weights.parent.parent.name:
            # runs/<эксперимент>/weights/best.pt -> имя эксперимента
            name = weights.parent.parent.name
        else:
            name = weights.stem
    out_dir = out_root / name
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== {weights} -> {out_dir} ===")
    model = YOLO(str(weights))
    results = model.val(data=str(data), split="test")

    # Общие метрики
    metrics = results.results_dict
    with open(out_dir / "summary.csv", "w", encoding="utf-8") as f:
        f.write("metric,value\n")
        for key in METRIC_KEYS:
            f.write(f"{key},{metrics.get(key, float('nan')):.6f}\n")
    for key in METRIC_KEYS:
        print(f"  {key}: {metrics.get(key, float('nan')):.4f}")

    # Метрики по классам
    box = results.box
    with open(out_dir / "per_class.csv", "w", encoding="utf-8") as f:
        f.write("class,precision,recall,mAP50,mAP50-95\n")
        for i, class_id in enumerate(box.ap_class_index):
            class_name = results.names[class_id]
            f.write(f"{class_name},{box.p[i]:.6f},{box.r[i]:.6f},"
                    f"{box.ap50[i]:.6f},{box.ap[i]:.6f}\n")
            print(f"  {class_name:<12} P={box.p[i]:.3f} R={box.r[i]:.3f} "
                  f"mAP50={box.ap50[i]:.3f} mAP50-95={box.ap[i]:.3f}")

    # Копируем графики из каталога эксперимента (если есть)
    run_dir = weights.parent.parent
    for png in ("confusion_matrix.png", "PR_curve.png", "results.png"):
        src = run_dir / png
        if src.exists():
            shutil.copy2(src, out_dir / png)


def main() -> None:
    parser = argparse.ArgumentParser(description="Оценка метрик на тестовой выборке")
    parser.add_argument("--weights", default="weights/best.pt", help="путь к весам")
    parser.add_argument("--data", default="dataset/data.yaml", help="путь к data.yaml")
    parser.add_argument("--name", default=None, help="имя каталога в metrics/ (по умолчанию — имя эксперимента)")
    parser.add_argument("--runs", default=None, const="all", nargs="?",
                        help="оценить все runs/*/weights/best.pt по очереди")
    args = parser.parse_args()

    data = Path(args.data)
    if not data.exists():
        raise SystemExit("Нет dataset/data.yaml — сначала запустите python download_dataset.py")
    out_root = Path("metrics")

    if args.runs == "all":
        candidates = sorted(Path("runs").glob("**/weights/best.pt"))
        if not candidates:
            raise SystemExit("Не найдено runs/*/weights/best.pt")
        for weights in candidates:
            evaluate(weights, data, out_root, name=args.name)
    else:
        weights = Path(args.weights)
        if not weights.exists():
            raise SystemExit(f"Нет весов {weights} — сначала обучите модель (train.py)")
        evaluate(weights, data, out_root, name=args.name)

    print(f"\nРезультаты сохранены в {out_root}/")


if __name__ == "__main__":
    main()

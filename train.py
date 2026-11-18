"""Дообучение YOLOv8 для детекции ингредиентов пиццы.

Каждый запуск — именованный эксперимент в runs/<имя>/ (для этапа 4: меняем
параметр — переобучаем – сравниваем через compare_runs.py).

Запуск: python train.py --name exp01_baseline
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Обучение YOLOv8 на датасете пиццы")
    parser.add_argument("--data", default="dataset/data.yaml", help="путь к data.yaml")
    parser.add_argument("--model", default="yolov8n.pt", help="модель (yolov8n/s/m/l/x)")
    parser.add_argument("--name", default="exp01_baseline", help="имя эксперимента (runs/<имя>)")
    parser.add_argument("--epochs", type=int, default=50, help="число эпох")
    parser.add_argument("--imgsz", type=int, default=640, help="размер входа")
    parser.add_argument("--batch", type=int, default=16, help="размер батча (-1 — авто)")
    parser.add_argument("--device", default="auto", help="auto / cpu / cuda / 0")
    parser.add_argument("--lr0", type=float, default=0.01, help="начальный learning rate")
    parser.add_argument("--optimizer", default="auto", help="auto / SGD / AdamW / Adam")
    parser.add_argument("--seed", type=int, default=42, help="сид для воспроизводимости")
    parser.add_argument("--patience", type=int, default=15, help="ранняя остановка")
    parser.add_argument("--workers", type=int, default=8, help="потоки загрузки данных")
    # Аугментации — основные ручки для экспериментов этапа 4
    parser.add_argument("--mosaic", type=float, default=1.0, help="вероятность мозаики")
    parser.add_argument("--mixup", type=float, default=0.0, help="вероятность mixup")
    parser.add_argument("--hsv_h", type=float, default=0.015, help="аугментация оттенка")
    parser.add_argument("--hsv_s", type=float, default=0.7, help="аугментация насыщенности")
    parser.add_argument("--hsv_v", type=float, default=0.4, help="аугментация яркости")
    parser.add_argument("--degrees", type=float, default=0.0, help="случайный поворот, градусы")
    parser.add_argument("--flipud", type=float, default=0.0, help="вертикальное отражение")
    parser.add_argument("--fliplr", type=float, default=0.5, help="горизонтальное отражение")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit("Нет dataset/data.yaml — сначала запустите python download_dataset.py")

    print(f"Эксперимент '{args.name}': модель={args.model}, epochs={args.epochs}, "
          f"imgsz={args.imgsz}, batch={args.batch}, lr0={args.lr0}")

    model = YOLO(args.model)
    # Абсолютный путь: относительный project ultralytics склеивает со своим
    # служебным каталогом (получилось бы runs/detect/runs/<имя>)
    runs_project = Path("runs").resolve()
    results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        lr0=args.lr0,
        optimizer=args.optimizer,
        seed=args.seed,
        patience=args.patience,
        workers=args.workers,
        project=str(runs_project),
        name=args.name,
        # Аугментации
        mosaic=args.mosaic,
        mixup=args.mixup,
        hsv_h=args.hsv_h,
        hsv_s=args.hsv_s,
        hsv_v=args.hsv_v,
        degrees=args.degrees,
        flipud=args.flipud,
        fliplr=args.fliplr,
    )

    # Копируем лучшие веса в weights/best.pt (их ждут detector.py и GUI)
    best = Path(model.trainer.best)
    weights_dir = Path("weights")
    weights_dir.mkdir(exist_ok=True)
    shutil.copy2(best, weights_dir / "best.pt")

    print("\n=== Итоговые метрики на валидации ===")
    metrics = getattr(results, "results_dict", {}) or {}
    for key in ("metrics/precision(B)", "metrics/recall(B)",
                "metrics/mAP50(B)", "metrics/mAP50-95(B)"):
        value = metrics.get(key)
        if value is not None:
            print(f"{key}: {value:.4f}")
    print(f"\nЛучшие веса: {best} -> {weights_dir / 'best.pt'}")
    print(f"Каталог эксперимента: {Path(model.trainer.save_dir)}")


if __name__ == "__main__":
    main()

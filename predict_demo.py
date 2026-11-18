"""Визуализация детекции на тестовых изображениях (для отчёта и проверки весов).

Берёт изображения (переданные аргументом или случайные из тестового сплита),
запускает модель и сохраняет аннотированные картинки в out/validation/.

Запуск:
    python predict_demo.py                          # 8 случайных из test
    python predict_demo.py --count 15 --conf 0.15
    python predict_demo.py путь/к/фото.jpg ещё.jpg  # конкретные файлы
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from ultralytics import YOLO

TEST_DIR = Path("dataset/raw/test/images")
OUT_DIR = Path("out/validation")
WEIGHTS = Path("weights/best.pt")


def main() -> None:
    parser = argparse.ArgumentParser(description="Детекция на изображениях с сохранением разметки")
    parser.add_argument("images", nargs="*", help="пути к изображениям (иначе случайные из test)")
    parser.add_argument("--weights", default=str(WEIGHTS))
    parser.add_argument("--conf", type=float, default=0.15, help="порог уверенности")
    parser.add_argument("--count", type=int, default=8, help="сколько случайных изображений брать")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not Path(args.weights).exists():
        raise SystemExit(f"Нет весов {args.weights} — сначала обучите модель (train.py)")

    if args.images:
        images = [Path(p) for p in args.images]
    else:
        if not TEST_DIR.exists():
            raise SystemExit("Нет dataset/raw/test/images — сначала запустите download_dataset.py")
        random.seed(args.seed)
        images = random.sample(sorted(TEST_DIR.glob("*.jpg")), min(args.count, 100))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.weights)

    for image_path in images:
        result = model.predict(str(image_path), conf=args.conf, verbose=False)[0]
        out_path = OUT_DIR / f"{image_path.stem}_det.jpg"
        result.save(str(out_path))  # рамки + подписи классов от ultralytics
        counts = {}
        for cls_id in result.boxes.cls.tolist():
            name = result.names[int(cls_id)]
            counts[name] = counts.get(name, 0) + 1
        summary = ", ".join(f"{k}×{v}" for k, v in sorted(counts.items())) or "ничего не найдено"
        print(f"{image_path.name}: {len(result.boxes)} объектов — {summary}")


if __name__ == "__main__":
    main()

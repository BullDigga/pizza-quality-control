"""Скачивание датасета Pizza-Toppings-Object-Detection с HuggingFace.

Что делает:
- скачивает репозиторий датасета в dataset/raw/ (без обучающего ноутбука);
- находит каталоги train/valid/test и записывает корректный dataset/data.yaml
  (пути в исходном data.yaml датасета не совпадают с реальной структурой);
- считает распределение классов по сплитам -> dataset/class_distribution.csv
  (пригодится для отчётов по этапам 3-4).

Запуск: python download_dataset.py [--force]
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from huggingface_hub import snapshot_download

REPO_ID = "mbar0075/Pizza-Toppings-Object-Detection"

# Порядок классов строго как в data.yaml датасета (индекс = id класса)
CLASS_NAMES = [
    "Arugula", "Bacon", "Basil", "Broccoli", "Cheese", "Chicken", "Corn",
    "Ham", "Mushroom", "Olives", "Onion", "Pepperoni", "Peppers",
    "Pineapple", "Pizza", "Tomatoes",
]
SPLITS = ("train", "valid", "test")
IMAGE_EXTS = ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG")


def find_images_dir(raw: Path, split: str) -> Path | None:
    """Ищет каталог с картинками сплита: raw/<split>/images или глубже."""
    for pattern in (f"{split}/images", f"{split}/Images", f"**/{split}/images"):
        for d in sorted(raw.glob(pattern)):
            if d.is_dir() and any(d.iterdir()):
                return d
    # запасной вариант: картинки лежат прямо в каталоге сплита
    direct = raw / split
    if direct.is_dir() and any(direct.glob("*.jpg")):
        return direct
    return None


def count_images(images_dir: Path) -> int:
    """Число файлов изображений (регистр расширения не важен — на Windows
    glob '*.jpg' и '*.JPG' совпадают с одними и теми же файлами)."""
    return sum(1 for f in images_dir.iterdir()
               if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Скачивание и подготовка датасета пиццы")
    parser.add_argument("--force", action="store_true",
                        help="скачать заново, даже если dataset/raw уже существует")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent / "dataset"
    raw = root / "raw"

    if args.force or not raw.exists():
        raw.mkdir(parents=True, exist_ok=True)
        print(f"Скачиваю {REPO_ID} (~90 МБ)...")
        snapshot_download(
            repo_id=REPO_ID,
            repo_type="dataset",
            local_dir=raw,
            ignore_patterns=["*.ipynb"],
        )
    else:
        print(f"Датасет уже скачан: {raw} (используйте --force для повторного скачивания)")

    # Проверяем структуру сплитов
    split_dirs: dict[str, Path] = {}
    for split in SPLITS:
        images_dir = find_images_dir(raw, split)
        if images_dir is None:
            raise SystemExit(f"Не нашёл картинки сплита '{split}' в {raw}")
        labels_dir = images_dir.parent / "labels"
        if not labels_dir.is_dir():
            raise SystemExit(f"Нет каталога labels рядом с {images_dir}")
        split_dirs[split] = images_dir

    # Записываем корректный data.yaml (пути относительно каталога dataset/raw)
    lines = [f"path: {raw.as_posix()}"]
    for split, yaml_key in (("train", "train"), ("valid", "val"), ("test", "test")):
        rel = split_dirs[split].relative_to(raw).as_posix()
        lines.append(f"{yaml_key}: {rel}")
    lines.append("names:")
    lines.extend(f"  {i}: {name}" for i, name in enumerate(CLASS_NAMES))
    yaml_path = root / "data.yaml"
    yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Записан {yaml_path}")

    # Статистика: число изображений и экземпляров каждого класса по сплитам
    rows = []
    for split in SPLITS:
        images_dir = split_dirs[split]
        labels_dir = images_dir.parent / "labels"
        counter: Counter[int] = Counter()
        for lbl in labels_dir.glob("*.txt"):
            for line in lbl.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.split()
                if parts and parts[0].isdigit():
                    counter[int(parts[0])] += 1
        print(f"{split}: {count_images(images_dir)} изображений, "
              f"{sum(counter.values())} экземпляров")
        for class_id, count in sorted(counter.items()):
            rows.append({"split": split, "class_id": class_id,
                         "class": CLASS_NAMES[class_id], "instances": count})

    csv_path = root / "class_distribution.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "class_id", "class", "instances"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Распределение классов: {csv_path}")
    print("Готово.")


if __name__ == "__main__":
    main()

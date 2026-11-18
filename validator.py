"""Валидация соответствия пиццы рецепту и подсказки «куда докинуть».

Правила:
- Полнота класса = найдено / требуется. Класс в норме, если полнота >= 90%.
- Вердикт PASS — если все классы рецепта в норме.
- Лишние ингредиенты (найдены, но не в рецепте) — предупреждение, не FAIL.
- Если полнота < 90%, предлагаем точки, куда докинуть недостающее: точки
  внутри зоны пиццы, максимально удалённые от уже найденных ингредиентов
  того же класса (жадный выбор). Нет таковых — от всех ингредиентов.
  Нет ни одного ингредиента — равномерно по кругу зоны пиццы.

Зависит только от структур с полями cls_name/center (детекции из detector.py),
поэтому логика тестируется без модели и без torch.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from recipes import PIZZA_CLASS, ru_name

COMPLETENESS_THRESHOLD = 0.9  # класс в норме, если найдено >= 90% от требуемого
EPS = 1e-9


@dataclass
class ClassReport:
    """Результат сверки одного ингредиента."""
    cls_name: str
    required: int
    found: int

    @property
    def completeness(self) -> float:
        return self.found / self.required if self.required > 0 else 1.0

    @property
    def ok(self) -> bool:
        return self.found + EPS >= COMPLETENESS_THRESHOLD * self.required

    @property
    def missing(self) -> int:
        """Сколько кусочков не хватает до полной нормы рецепта."""
        return max(0, self.required - self.found)

    @property
    def name_ru(self) -> str:
        return ru_name(self.cls_name)


@dataclass
class Suggestion:
    """Точка «докинуть сюда» на изображении (пиксели)."""
    cls_name: str
    x: float
    y: float

    @property
    def name_ru(self) -> str:
        return ru_name(self.cls_name)


@dataclass
class ValidationResult:
    class_reports: list[ClassReport] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)  # лишние классы (англ.)
    suggestions: list[Suggestion] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.ok for r in self.class_reports)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.class_reports if r.ok)


def _pizza_region(detections: list, image_size: tuple[int, int]) -> tuple[float, float, float] | None:
    """Круг зоны пиццы (cx, cy, r): по самому крупному боксу класса Pizza.

    Возвращает None, если пиццу не нашли — тогда зона всё изображение.
    """
    pizza_boxes = [d for d in detections if d.cls_name == PIZZA_CLASS]
    if pizza_boxes:
        best = max(pizza_boxes,
                   key=lambda d: (d.x2 - d.x1) * (d.y2 - d.y1))
        cx, cy = best.center
        r = min(best.x2 - best.x1, best.y2 - best.y1) / 2 * 0.95  # вписанный круг
        return (cx, cy, r)
    return None


def place_missing(detections: list, cls_name: str, k: int,
                  region: tuple[float, float, float] | None,
                  image_size: tuple[int, int], grid: int = 60) -> list[tuple[float, float]]:
    """k точек, максимально удалённых от ингредиентов того же класса.

    Жадный алгоритм дальних точек: сетка кандидатов внутри зоны пиццы,
    на каждом шаге берём кандидата с максимальным расстоянием до ближайшего
    «якоря» (ингредиенты того же класса + уже выбранные точки).
    """
    if k <= 0:
        return []
    width, height = image_size
    if region is not None:
        cx, cy, r = region
    else:
        cx, cy, r = width / 2, height / 2, min(width, height) / 2 * 0.95

    def inside(px: float, py: float) -> bool:
        if region is not None:
            return math.hypot(px - cx, py - cy) <= r
        return 0.0 <= px <= width and 0.0 <= py <= height

    # Якоря: сначала ингредиенты того же класса, иначе все ингредиенты
    same_class = [d.center for d in detections
                  if d.cls_name == cls_name and d.cls_name != PIZZA_CLASS]
    anchors = same_class or [d.center for d in detections
                             if d.cls_name != PIZZA_CLASS]
    if not anchors:
        # Ингредиентов нет вовсе — раскидываем k точек равномерно по кругу
        return [(cx + 0.5 * r * math.cos(2 * math.pi * i / k),
                 cy + 0.5 * r * math.sin(2 * math.pi * i / k)) for i in range(k)]

    # Сетка кандидатов внутри зоны
    candidates = []
    for gx in range(grid + 1):
        for gy in range(grid + 1):
            px = cx - r + (2 * r) * gx / grid
            py = cy - r + (2 * r) * gy / grid
            if inside(px, py):
                candidates.append((px, py))

    chosen: list[tuple[float, float]] = []
    for _ in range(k):
        best_point = max(candidates, key=lambda p: min(
            math.hypot(p[0] - a[0], p[1] - a[1]) for a in anchors + chosen))
        chosen.append(best_point)
    return chosen


def validate(detections: list, recipe: dict,
             image_size: tuple[int, int] = (640, 640),
             grid: int = 60) -> ValidationResult:
    """Сверяет найденные детекции с рецептом пиццы.

    detections — список объектов с полями cls_name, center, x1/y1/x2/y2
                 (детекции из detector.py);
    recipe     — {"name": ..., "ingredients": {класс: количество}};
    image_size — (ширина, высота) изображения в пикселях.
    """
    counts: dict[str, int] = {}
    for det in detections:
        if det.cls_name != PIZZA_CLASS:
            counts[det.cls_name] = counts.get(det.cls_name, 0) + 1

    required = {cls: int(n) for cls, n in recipe.get("ingredients", {}).items()
                if int(n) > 0}

    reports = [ClassReport(cls_name=cls, required=n, found=counts.get(cls, 0))
               for cls, n in required.items()]
    extras = sorted(cls for cls in counts if cls not in required)

    region = _pizza_region(detections, image_size)
    suggestions: list[Suggestion] = []
    for report in reports:
        if not report.ok:
            points = place_missing(detections, report.cls_name, report.missing,
                                   region, image_size, grid)
            suggestions.extend(Suggestion(report.cls_name, x, y) for x, y in points)

    return ValidationResult(class_reports=reports, extras=extras,
                            suggestions=suggestions)

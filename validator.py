"""Валидация соответствия пиццы рецепту и подсказки «куда докинуть».

Правила:
- Полнота класса = найдено / требуется. Класс в норме, если полнота >= 90%.
- Избыток (найдено > требуется) — предупреждение, на вердикт не влияет.
- Вердикт PASS — если все классы рецепта в норме.
- Лишние ингредиенты (найдены, но не в рецепте) — предупреждение, не FAIL.
- Если полнота < 90%, предлагаем точки, куда докинуть недостающее:
  * экземпляры того же класса есть — точки, максимально удалённые от них
    (жадный выбор дальних точек);
  * класса на пицце нет вовсе (например, сыр) — равномерное покрытие
    зоны пиццы (спираль Вогеля): базовый ингредиент раскидывается
    по всей площади, а не «подальше от остальных».

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
    def excess(self) -> int:
        """Сколько кусочков больше нормы (предупреждение об избытке)."""
        return max(0, self.found - self.required)

    @property
    def is_extra(self) -> bool:
        """Ингредиент найден, но в рецепте его нет (надо = 0)."""
        return self.required == 0 and self.found > 0

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
class RemovalSuggestion:
    """Рамка «эту найти и убрать» — при избытке ингредиента."""
    cls_name: str
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def name_ru(self) -> str:
        return ru_name(self.cls_name)


@dataclass
class ValidationResult:
    class_reports: list[ClassReport] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)  # лишние классы (англ.)
    suggestions: list[Suggestion] = field(default_factory=list)
    removals: list[RemovalSuggestion] = field(default_factory=list)

    @property
    def recipe_reports(self) -> list[ClassReport]:
        """Отчёты по классам из рецепта (без «лишних» с надо = 0)."""
        return [r for r in self.class_reports if r.required > 0]

    @property
    def passed(self) -> bool:
        return all(r.ok for r in self.class_reports)

    @property
    def ok_count(self) -> int:
        """Сколько ингредиентов рецепта в норме (лишние не считаются)."""
        return sum(1 for r in self.recipe_reports if r.ok)


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


GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))  # золотой угол для спирали Вогеля


def even_spread(cx: float, cy: float, r: float, k: int) -> list[tuple[float, float]]:
    """k точек, равномерно покрывающих круг радиуса r (спираль Вогеля).

    Применяется, когда ингредиентов класса на пицце нет вовсе: такой
    ингредиент (сыр, соус) — базовый, его распределяют по всей площади.
    """
    if k == 1:
        return [(cx, cy)]
    points = []
    for i in range(k):
        rr = r * math.sqrt((i + 0.5) / k)
        theta = i * GOLDEN_ANGLE
        points.append((cx + rr * math.cos(theta), cy + rr * math.sin(theta)))
    return points


def place_missing(detections: list, cls_name: str, k: int,
                  region: tuple[float, float, float] | None,
                  image_size: tuple[int, int], grid: int = 60) -> list[tuple[float, float]]:
    """k точек, куда докинуть ингредиент класса cls_name.

    Экземпляры того же класса есть — жадный алгоритм дальних точек: сетка
    кандидатов внутри зоны пиццы, на каждом шаге берём кандидата с
    максимальным расстоянием до ближайшего «якоря» (того же класса +
    уже выбранные точки). Класса нет вовсе — равномерная раскладка
    even_spread по зоне пиццы.
    """
    if k <= 0:
        return []
    width, height = image_size
    if region is not None:
        cx, cy, r = region
    else:
        cx, cy, r = width / 2, height / 2, min(width, height) / 2 * 0.95

    same_class = [d.center for d in detections
                  if d.cls_name == cls_name and d.cls_name != PIZZA_CLASS]
    if not same_class:
        # Класса на пицце нет (например, сыр) — равномерно по всей пицце,
        # с запасом 0.7*r от края, чтобы точки не липли к бортику
        return even_spread(cx, cy, r * 0.7, k)

    def inside(px: float, py: float) -> bool:
        if region is not None:
            return math.hypot(px - cx, py - cy) <= r
        return 0.0 <= px <= width and 0.0 <= py <= height

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
            math.hypot(p[0] - a[0], p[1] - a[1]) for a in same_class + chosen))
        chosen.append(best_point)
    return chosen


def pick_removals(detections: list, cls_name: str, k: int) -> list[RemovalSuggestion]:
    """k рамок класса cls_name, которые лучше всего убрать при избытке.

    Жадно выбираем самые «сгущённые»: на каждом шаге изымаем бокс с
    минимальным расстоянием до ближайшего соседа того же класса —
    это и двойные детекции, и реальные кучки, где изъятие наименее заметно.
    """
    remaining = [d for d in detections
                 if d.cls_name == cls_name and d.cls_name != PIZZA_CLASS]
    picked = []
    while len(picked) < k and remaining:
        def nearest_distance(d) -> float:
            others = [o for o in remaining if o is not d]
            if not others:
                return float("inf")
            return min(math.dist(d.center, o.center) for o in others)
        victim = min(remaining, key=nearest_distance)
        picked.append(victim)
        remaining.remove(victim)
    return [RemovalSuggestion(cls_name, v.x1, v.y1, v.x2, v.y2) for v in picked]


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
    # Лишние ингредиенты — тоже строки отчёта, но с надо = 0
    reports.extend(ClassReport(cls_name=cls, required=0, found=counts[cls])
                   for cls in extras)

    region = _pizza_region(detections, image_size)
    suggestions: list[Suggestion] = []
    removals: list[RemovalSuggestion] = []
    for report in reports:
        if not report.ok:
            points = place_missing(detections, report.cls_name, report.missing,
                                   region, image_size, grid)
            suggestions.extend(Suggestion(report.cls_name, x, y) for x, y in points)
        elif report.required > 0 and report.excess > 0:
            removals.extend(pick_removals(detections, report.cls_name,
                                           report.excess))

    return ValidationResult(class_reports=reports, extras=extras,
                            suggestions=suggestions, removals=removals)

"""Тесты логики валидации (без модели — на синтетических детекциях).

Запуск: python test_validator.py
"""
from __future__ import annotations

import math
from itertools import combinations
from types import SimpleNamespace

from recipes import PIZZA_CLASS
from validator import (COMPLETENESS_THRESHOLD, ClassReport, Suggestion,
                       pick_removals, place_missing, validate)


def det(cls_name: str, x: float, y: float, size: float = 20.0) -> SimpleNamespace:
    """Синтетическая детекция с центром в (x, y)."""
    return SimpleNamespace(
        cls_name=cls_name,
        center=(x, y),
        x1=x - size / 2, y1=y - size / 2, x2=x + size / 2, y2=y + size / 2,
    )


def test_class_report_thresholds() -> None:
    # 10 найдено 9 -> 90% -> норма
    r = ClassReport("Pepperoni", 10, 9)
    assert r.ok, "9 из 10 должно проходить порог 90%"
    assert abs(r.completeness - 0.9) < 1e-9
    # 10 найдено 8 -> 80% -> не норма, докинуть 2
    r = ClassReport("Pepperoni", 10, 8)
    assert not r.ok
    assert r.missing == 2
    # 3 найдено 2 -> 66% -> не норма (порог 2.7)
    assert not ClassReport("Onion", 3, 2).ok
    # 3 найдено 3 -> норма
    assert ClassReport("Onion", 3, 3).ok
    # 0 требуется -> всегда норма
    assert ClassReport("Cheese", 0, 5).ok
    print("ok: пороги полноты 90%")


def test_validate_verdict() -> None:
    recipe = {"name": "Тест", "ingredients": {"Pepperoni": 10, "Olives": 10}}
    # Всё на месте -> PASS, без подсказок
    dets = [det("Pepperoni", 100 + 30 * i, 100) for i in range(10)] + \
           [det("Olives", 100, 100 + 30 * i) for i in range(10)] + \
           [det(PIZZA_CLASS, 320, 320, 600)]
    res = validate(dets, recipe, (640, 640))
    assert res.passed and not res.suggestions and not res.extras

    # Пепперони 8 из 10 -> FAIL, 2 подсказки для Pepperoni
    dets = [det("Pepperoni", 100 + 30 * i, 100) for i in range(8)] + \
           [det("Olives", 100, 100 + 30 * i) for i in range(10)] + \
           [det(PIZZA_CLASS, 320, 320, 600)]
    res = validate(dets, recipe, (640, 640))
    assert not res.passed
    assert res.ok_count == 1
    pepperoni_suggestions = [s for s in res.suggestions if s.cls_name == "Pepperoni"]
    assert len(pepperoni_suggestions) == 2

    # Лишний ингредиент -> предупреждение, но вердикт не меняет
    dets += [det("Basil", 400, 400)]
    res = validate(dets, recipe, (640, 640))
    assert "Basil" in res.extras
    assert res.ok_count == 1  # Olives в норме, Pepperoni нет
    print("ok: вердикт PASS/FAIL, подсказки, лишние ингредиенты")


def test_place_missing_far_from_same_class() -> None:
    # 5 пеппероний в левой половине — подсказка должна уйти вправо
    dets = [det("Pepperoni", 100 + 25 * i, 320) for i in range(5)]
    region = (320, 320, 300)
    (x, y), *_ = place_missing(dets, "Pepperoni", 1, region, (640, 640))
    same_x = [d.center[0] for d in dets]
    assert x > max(same_x), "точка должна быть правее всех ингредиентов того же класса"
    assert math.hypot(x - 320, y - 320) <= 300 + 1e-6, "точка вне зоны пиццы"
    print("ok: подсказка уходит от ингредиентов того же класса")


def test_place_missing_spread() -> None:
    # Нет ни одной детекции -> равномерная раскладка по зоне пиццы
    points = place_missing([], "Mushroom", 3, (320, 320, 300), (640, 640))
    assert len(points) == 3
    assert all(math.hypot(x - 320, y - 320) <= 0.7 * 300 + 1e-6
               for x, y in points)
    # Без зоны пиццы тоже работает (весь кадр)
    points = place_missing([], "Mushroom", 2, None, (640, 640))
    assert len(points) == 2
    print("ok: равномерное размещение при пустой пицце")


def test_place_missing_no_same_class_spreads_evenly() -> None:
    # Сыра нет вовсе (даже при других ингредиентах на пицце) ->
    # равномерное покрытие площади пиццы, а не «подальше от остальных»
    dets = [det("Pepperoni", 80, 80), det("Pepperoni", 500, 500)]
    points = place_missing(dets, "Cheese", 6, (320, 320, 300), (640, 640))
    assert len(points) == 6
    radii = [math.hypot(x - 320, y - 320) for x, y in points]
    assert max(radii) <= 0.7 * 300 + 1e-6, "точки не должны липнуть к краю"
    assert max(radii) >= 0.3 * 300, "точки должны покрывать площадь до краёв"
    pairwise = [math.dist(a, b) for a, b in combinations(points, 2)]
    assert min(pairwise) >= 0.25 * 300, "точки не должны кучковаться"
    # Одна точка -> центр пиццы
    assert place_missing(dets, "Cheese", 1, (320, 320, 300), (640, 640)) == [(320, 320)]
    print("ok: без своего класса — равномерно по всей пицце (спираль Вогеля)")


def test_excess_report() -> None:
    # Найдено больше нормы — класс в норме, но избыток отмечается
    r = ClassReport("Pepperoni", 14, 18)
    assert r.ok and r.excess == 4 and r.missing == 0
    assert abs(r.completeness - 18 / 14) < 1e-9
    print("ok: избыток считается и не заваливает вердикт")


def test_extra_ingredient_in_reports() -> None:
    # Лишний ингредиент — строка отчёта с надо=0, вердикт не валит, крестов нет
    recipe = {"name": "Тест", "ingredients": {"Olives": 5}}
    dets = [det("Olives", 100 + 30 * i, 100) for i in range(5)] + \
           [det("Basil", 300, 300)] + [det(PIZZA_CLASS, 320, 320, 600)]
    res = validate(dets, recipe, (640, 640))
    assert res.passed, "лишний ингредиент не должен заваливать вердикт"
    assert len(res.class_reports) == 2
    extra = res.class_reports[-1]
    assert extra.cls_name == "Basil" and extra.required == 0 and extra.found == 1
    assert extra.is_extra and extra.ok
    assert res.ok_count == 1 and len(res.recipe_reports) == 1
    assert not res.removals and not res.suggestions
    assert "Basil" in res.extras
    print("ok: лишний ингредиент — строка с надо=0 и статусом «лишний»")


def test_pick_removals_densest_first() -> None:
    # 6 пеппероний: три кучкой слева, три далеко; избыток 2 — убрать 2 из кучки
    cluster = [det("Pepperoni", 100, 100), det("Pepperoni", 118, 100),
               det("Pepperoni", 136, 100)]
    far = [det("Pepperoni", 400, 100), det("Pepperoni", 100, 400),
           det("Pepperoni", 400, 400)]
    dets = cluster + far
    removals = pick_removals(dets, "Pepperoni", 2)
    assert len(removals) == 2
    centers = [((r.x1 + r.x2) / 2, (r.y1 + r.y2) / 2) for r in removals]
    assert all(x < 200 for x, _ in centers), "должны выбрать из плотной кучки"
    # end-to-end: рецепт требует 4, найдено 6 -> PASS, но 2 рамки «убрать»
    recipe = {"name": "Тест", "ingredients": {"Pepperoni": 4}}
    res = validate(dets, recipe, (640, 640))
    assert res.passed and len(res.removals) == 2 and not res.suggestions
    print("ok: при избытке отмечаются к удалению самые сгущённые")


def test_class_report_suggestion_type() -> None:
    s = Suggestion("Pepperoni", 1.0, 2.0)
    assert (s.x, s.y) == (1.0, 2.0)
    assert ClassReport("Pepperoni", 10, 10).missing == 0
    assert COMPLETENESS_THRESHOLD == 0.9
    print("ok: структуры данных")


if __name__ == "__main__":
    test_class_report_thresholds()
    test_validate_verdict()
    test_place_missing_far_from_same_class()
    test_place_missing_spread()
    test_place_missing_no_same_class_spreads_evenly()
    test_excess_report()
    test_extra_ingredient_in_reports()
    test_pick_removals_densest_first()
    test_class_report_suggestion_type()
    print("\nВсе тесты пройдены.")

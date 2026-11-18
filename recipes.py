"""База пицц: рецепты с требуемым количеством каждого ингредиента.

Рецепт хранится в data/pizzas.json:
    [{"name": "Пепперони", "ingredients": {"Pepperoni": 14, "Cheese": 1}}, ...]
Классы ингредиентов — английские имена классов датасета (id совпадают с data.yaml).
"""
from __future__ import annotations

import json
from pathlib import Path

# Порядок классов строго как в data.yaml датасета (индекс = id класса)
CLASS_NAMES = [
    "Arugula", "Bacon", "Basil", "Broccoli", "Cheese", "Chicken", "Corn",
    "Ham", "Mushroom", "Olives", "Onion", "Pepperoni", "Peppers",
    "Pineapple", "Pizza", "Tomatoes",
]

CLASS_RU = {
    "Arugula": "Руккола",
    "Bacon": "Бекон",
    "Basil": "Базилик",
    "Broccoli": "Брокколи",
    "Cheese": "Сыр",
    "Chicken": "Курица",
    "Corn": "Кукуруза",
    "Ham": "Ветчина",
    "Mushroom": "Грибы",
    "Olives": "Оливки",
    "Onion": "Лук",
    "Pepperoni": "Пепперони",
    "Peppers": "Перец",
    "Pineapple": "Ананас",
    "Pizza": "Пицца (основание)",
    "Tomatoes": "Помидоры",
}

PIZZA_CLASS = "Pizza"
INGREDIENT_CLASSES = [c for c in CLASS_NAMES if c != PIZZA_CLASS]


def ru_name(en_name: str) -> str:
    """Русское название класса ингредиента."""
    return CLASS_RU.get(en_name, en_name)


# Стартовая база пицц. Количества — округлённые средние по train-выборке
# датасета (Pepperoni ~14, Ham ~13, Olives ~13, Peppers ~18, Mushroom ~10,
# Tomatoes ~7, Basil ~6, Cheese ~6 на изображение). Редактируются в GUI.
DEFAULT_PIZZAS = [
    {"name": "Пепперони", "ingredients": {"Pepperoni": 14, "Cheese": 6}},
    {"name": "Гавайская", "ingredients": {"Ham": 13, "Pineapple": 12, "Cheese": 6}},
    {"name": "Сырная", "ingredients": {"Cheese": 6}},
    {"name": "Овощная", "ingredients": {"Tomatoes": 7, "Peppers": 18, "Mushroom": 10,
                                        "Olives": 13, "Basil": 6}},
    {"name": "Мясная", "ingredients": {"Pepperoni": 14, "Ham": 13, "Chicken": 11,
                                       "Cheese": 6}},
]


class RecipeStore:
    """Загрузка/сохранение/изменение базы пицц в JSON."""

    def __init__(self, path: Path | str = Path("data") / "pizzas.json") -> None:
        self.path = Path(path)
        self.pizzas: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            self.pizzas = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.pizzas = json.loads(json.dumps(DEFAULT_PIZZAS))  # глубокая копия
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.pizzas, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def names(self) -> list[str]:
        return [p["name"] for p in self.pizzas]

    def get(self, name: str) -> dict | None:
        for pizza in self.pizzas:
            if pizza["name"] == name:
                return pizza
        return None

    def upsert(self, pizza: dict) -> None:
        """Добавляет пиццу или обновляет по имени."""
        for i, existing in enumerate(self.pizzas):
            if existing["name"] == pizza["name"]:
                self.pizzas[i] = pizza
                break
        else:
            self.pizzas.append(pizza)
        self.save()

    def delete(self, name: str) -> None:
        self.pizzas = [p for p in self.pizzas if p["name"] != name]
        self.save()

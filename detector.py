"""Обёртка YOLO-модели: детекция ингредиентов на изображении пиццы."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ultralytics import YOLO

from recipes import ru_name


@dataclass
class Detection:
    """Одна находка модели: класс + уверенность + рамка в пикселях."""
    cls_name: str  # английское имя класса (как в датасете)
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def name_ru(self) -> str:
        return ru_name(self.cls_name)


class Detector:
    """Загрузка обученных весов и инференс."""

    def __init__(self, weights: Path | str = Path("weights") / "best.pt") -> None:
        self.weights = Path(weights)
        if not self.weights.exists():
            raise FileNotFoundError(
                f"Не найдены веса {self.weights}. "
                "Обучите модель (python train.py) или скопируйте best.pt в weights/."
            )
        self.model = YOLO(str(self.weights))

    def detect(self, image_path: Path | str, conf: float = 0.25,
               iou: float = 0.45) -> list[Detection]:
        """Детекция на одном изображении."""
        result = self.model.predict(str(image_path), conf=conf, iou=iou,
                                    verbose=False)[0]
        detections = []
        for box in result.boxes:
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
            detections.append(Detection(
                cls_name=result.names[int(box.cls[0])],
                conf=float(box.conf[0]),
                x1=x1, y1=y1, x2=x2, y2=y2,
            ))
        return detections

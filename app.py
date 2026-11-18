"""Оконное приложение «Контроль качества пиццы» (PyQt6).

Сценарий работы:
1. «Загрузить изображение» — фото пиццы.
2. «Детекция» — ингредиенты в цветных рамках с уверенностью.
3. Выбрать пиццу из базы (кнопка «База пицц» — редактор рецептов).
4. «Проверить рецепт» — таблица полноты, вердикт ПРИГОДНА/БРАК,
   мишени «куда докинуть» на изображении.
5. «Сохранить результат» — PNG с разметкой.

Запуск: python app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from recipes import INGREDIENT_CLASSES, RecipeStore, ru_name
from validator import validate

WEIGHTS = Path("weights") / "best.pt"

# Палитра классов (индекс = id класса в data.yaml)
PALETTE = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4",
    "#46f0f0", "#f032e6", "#bcf60c", "#fabebe", "#008080", "#e6beff",
    "#9a6324", "#fffac8", "#800000", "#aaffc3",
]
MARKER_COLOR = QColor("#ff00ff")  # мишень «куда докинуть»


def class_color(cls_name: str) -> QColor:
    from recipes import CLASS_NAMES
    idx = CLASS_NAMES.index(cls_name) if cls_name in CLASS_NAMES else 0
    return QColor(PALETTE[idx % len(PALETTE)])


class DetectWorker(QThread):
    """Детекция в фоне, чтобы окно не зависало."""
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, detector, image_path: Path, conf: float) -> None:
        super().__init__()
        self.detector = detector
        self.image_path = image_path
        self.conf = conf

    def run(self) -> None:
        try:
            detections = self.detector.detect(self.image_path, conf=self.conf)
            self.done.emit(detections)
        except Exception as exc:  # noqa: BLE001 — показываем пользователю
            self.failed.emit(str(exc))


class RecipeDialog(QDialog):
    """Диалог добавления/изменения одной пиццы: имя + количества ингредиентов."""

    def __init__(self, parent=None, pizza: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Рецепт пиццы")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        self.name_edit = QLineEdit(pizza["name"] if pizza else "")
        self.name_edit.setPlaceholderText("Название пиццы")
        layout.addWidget(self.name_edit)

        grid = QGridLayout()
        self.spinboxes: dict[str, QSpinBox] = {}
        ingredients = pizza["ingredients"] if pizza else {}
        for i, cls in enumerate(INGREDIENT_CLASSES):
            spin = QSpinBox()
            spin.setRange(0, 99)
            spin.setValue(int(ingredients.get(cls, 0)))
            self.spinboxes[cls] = spin
            grid.addWidget(QLabel(ru_name(cls)), i // 3, (i % 3) * 2)
            grid.addWidget(spin, i // 3, (i % 3) * 2 + 1)
        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_pizza(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "ingredients": {cls: spin.value() for cls, spin in self.spinboxes.items()
                            if spin.value() > 0},
        }


class RecipeBookDialog(QDialog):
    """Редактор базы пицц: список + добавить/изменить/удалить."""

    def __init__(self, parent, store: RecipeStore) -> None:
        super().__init__(parent)
        self.setWindowTitle("База пицц")
        self.resize(420, 400)
        self.store = store
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        row = QHBoxLayout()
        btn_add = QPushButton("Добавить")
        btn_edit = QPushButton("Изменить")
        btn_del = QPushButton("Удалить")
        btn_add.clicked.connect(self.add_pizza)
        btn_edit.clicked.connect(self.edit_pizza)
        btn_del.clicked.connect(self.delete_pizza)
        for b in (btn_add, btn_edit, btn_del):
            row.addWidget(b)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(lambda _: self.reject())
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        for pizza in self.store.pizzas:
            ingredients = ", ".join(f"{ru_name(c)}×{n}"
                                    for c, n in pizza["ingredients"].items())
            self.list_widget.addItem(f"{pizza['name']}  —  {ingredients}")

    def add_pizza(self) -> None:
        dialog = RecipeDialog(self)
        if dialog.exec() and dialog.result_pizza()["name"]:
            self.store.upsert(dialog.result_pizza())
            self.refresh()

    def edit_pizza(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        pizza = self.store.pizzas[row]
        dialog = RecipeDialog(self, pizza)
        if dialog.exec() and dialog.result_pizza()["name"]:
            self.store.upsert(dialog.result_pizza())
            self.refresh()

    def delete_pizza(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        name = self.store.pizzas[row]["name"]
        if QMessageBox.question(self, "Удаление", f"Удалить пиццу «{name}»?") == \
                QMessageBox.StandardButton.Yes:
            self.store.delete(name)
            self.refresh()


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Контроль качества пиццы — детекция ингредиентов")
        self.resize(1400, 860)

        self.store = RecipeStore()
        self.detector = None
        self.worker = None
        self.image_path: Path | None = None
        self.original: QPixmap | None = None
        self.detections: list = []
        self.suggestions: list = []

        self._build_ui()

    # ---------- интерфейс ----------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        # Слева: изображение
        self.image_label = QLabel("Загрузите изображение пиццы")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(760, 600)
        self.image_label.setStyleSheet("background: #1e1e1e; color: #888;")
        scroll = QScrollArea()
        scroll.setWidget(self.image_label)
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, stretch=1)

        # Справа: панель управления
        panel = QVBoxLayout()
        panel.setSpacing(10)

        box_actions = QGroupBox("Изображение")
        actions = QVBoxLayout(box_actions)
        self.btn_open = QPushButton("Загрузить изображение…")
        self.btn_open.clicked.connect(self.open_image)
        self.btn_detect = QPushButton("Детекция")
        self.btn_detect.clicked.connect(self.run_detection)
        self.btn_detect.setEnabled(False)
        actions.addWidget(self.btn_open)
        actions.addWidget(self.btn_detect)

        conf_row = QHBoxLayout()
        conf_row.addWidget(QLabel("Порог уверенности:"))
        self.conf_label = QLabel("25%")
        conf_row.addWidget(self.conf_label)
        actions.addLayout(conf_row)
        self.conf_slider = QSlider(Qt.Orientation.Horizontal)
        self.conf_slider.setRange(5, 95)
        self.conf_slider.setValue(25)
        self.conf_slider.valueChanged.connect(
            lambda v: self.conf_label.setText(f"{v}%"))
        self.conf_slider.sliderReleased.connect(self.rerun_on_conf_change)
        actions.addWidget(self.conf_slider)
        panel.addWidget(box_actions)

        box_recipe = QGroupBox("Рецепт")
        recipe = QVBoxLayout(box_recipe)
        self.pizza_combo = QComboBox()
        self.pizza_combo.addItems(self.store.names())
        recipe.addWidget(self.pizza_combo)
        row = QHBoxLayout()
        self.btn_check = QPushButton("Проверить рецепт")
        self.btn_check.clicked.connect(self.check_recipe)
        self.btn_book = QPushButton("База пицц…")
        self.btn_book.clicked.connect(self.open_recipe_book)
        row.addWidget(self.btn_check)
        row.addWidget(self.btn_book)
        recipe.addLayout(row)
        panel.addWidget(box_recipe)

        box_result = QGroupBox("Результат проверки")
        result = QVBoxLayout(box_result)
        self.verdict_label = QLabel("—")
        font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        self.verdict_label.setFont(font)
        self.verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result.addWidget(self.verdict_label)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Ингредиент", "Надо", "Найдено", "Полнота", "Статус"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        result.addWidget(self.table)
        self.extras_label = QLabel("")
        self.extras_label.setWordWrap(True)
        result.addWidget(self.extras_label)
        self.btn_save = QPushButton("Сохранить результат…")
        self.btn_save.clicked.connect(self.save_result)
        self.btn_save.setEnabled(False)
        result.addWidget(self.btn_save)
        panel.addWidget(box_result)

        panel.addStretch(1)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #555;")
        panel.addWidget(self.status_label)
        right = QWidget()
        right.setLayout(panel)
        right.setFixedWidth(430)
        root.addWidget(right)

    # ---------- изображение и детекция ----------

    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать изображение пиццы", "",
            "Изображения (*.jpg *.jpeg *.png *.bmp);;Все файлы (*.*)")
        if not path:
            return
        self.image_path = Path(path)
        self.original = QPixmap(str(path))
        self.detections = []
        self.suggestions = []
        self.clear_results()
        self.render_image()
        self.btn_detect.setEnabled(True)
        self.status(f"Загружено: {self.image_path.name} "
                    f"({self.original.width()}×{self.original.height()})")

    def _get_detector(self):
        if self.detector is None:
            from detector import Detector
            self.detector = Detector(WEIGHTS)
        return self.detector

    def run_detection(self) -> None:
        if self.image_path is None or self.worker is not None:
            return
        try:
            detector = self._get_detector()
        except FileNotFoundError as exc:
            self.status(str(exc))
            QMessageBox.warning(self, "Нет весов", str(exc))
            return
        self.btn_detect.setEnabled(False)
        self.btn_detect.setText("Детекция…")
        self.status("Детекция…")
        conf = self.conf_slider.value() / 100
        self.worker = DetectWorker(detector, self.image_path, conf)
        self.worker.done.connect(self.on_detected)
        self.worker.failed.connect(self.on_detect_failed)
        # Освобождать объект потока можно только по QThread.finished —
        # сигнал done эмитится ещё внутри run(), и преждевременное
        # self.worker = None роняет приложение (QThread destroyed while running)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_finished(self) -> None:
        """Поток действительно завершён — освобождаем ссылку на него."""
        self.worker = None
        self.btn_detect.setEnabled(True)
        self.btn_detect.setText("Детекция")

    def rerun_on_conf_change(self) -> None:
        if self.image_path is not None:
            self.run_detection()

    def on_detected(self, detections: list) -> None:
        self.detections = detections
        self.suggestions = []
        counts: dict[str, int] = {}
        for d in detections:
            counts[d.cls_name] = counts.get(d.cls_name, 0) + 1
        summary = ", ".join(f"{ru_name(c)}×{n}" for c, n in sorted(counts.items()))
        self.status(f"Найдено {len(detections)} объектов: {summary or 'ничего'}")
        self.render_image()

    def on_detect_failed(self, message: str) -> None:
        self.status(f"Ошибка детекции: {message}")

    # ---------- проверка рецепта ----------

    def check_recipe(self) -> None:
        if not self.detections:
            self.status("Сначала загрузите изображение и запустите детекцию")
            return
        pizza = self.store.get(self.pizza_combo.currentText())
        if pizza is None:
            self.status("Выберите пиццу из базы")
            return
        result = validate(self.detections, pizza,
                          (self.original.width(), self.original.height()))
        self.suggestions = result.suggestions
        self.show_results(result, pizza)
        self.render_image()

    def show_results(self, result, pizza: dict) -> None:
        # Вердикт
        if result.passed:
            self.verdict_label.setText("✔ ПРИГОДНА")
            self.verdict_label.setStyleSheet("color: #2e7d32;")
        else:
            self.verdict_label.setText("✘ БРАК")
            self.verdict_label.setStyleSheet("color: #c62828;")
        # Таблица по классам
        self.table.setRowCount(len(result.class_reports))
        for i, report in enumerate(result.class_reports):
            values = [report.name_ru, str(report.required), str(report.found),
                      f"{report.completeness:.0%}",
                      "✔" if report.ok else f"✘ докинуть {report.missing}"]
            for j, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setForeground(QColor("#2e7d32") if report.ok
                                   else QColor("#c62828"))
                self.table.setItem(i, j, item)
        # Лишние ингредиенты
        if result.extras:
            extra_counts = {}
            for d in self.detections:
                if d.cls_name in result.extras:
                    extra_counts[d.cls_name] = extra_counts.get(d.cls_name, 0) + 1
            text = "⚠ Лишние ингредиенты (нет в рецепте): " + ", ".join(
                f"{ru_name(c)}×{n}" for c, n in sorted(extra_counts.items()))
            self.extras_label.setText(text)
        else:
            self.extras_label.setText("")
        n_suggestions = len(result.suggestions)
        if result.passed:
            self.status(f"«{pizza['name']}»: все ингредиенты в норме")
        else:
            self.status(f"«{pizza['name']}»: {result.ok_count}/{len(result.class_reports)} "
                        f"ингредиентов в норме; точек «докинуть»: {n_suggestions}")
        self.btn_save.setEnabled(True)

    def clear_results(self) -> None:
        self.verdict_label.setText("—")
        self.verdict_label.setStyleSheet("")
        self.table.setRowCount(0)
        self.extras_label.setText("")
        self.btn_save.setEnabled(False)

    def open_recipe_book(self) -> None:
        dialog = RecipeBookDialog(self, self.store)
        dialog.exec()
        current = self.pizza_combo.currentText()
        self.pizza_combo.clear()
        self.pizza_combo.addItems(self.store.names())
        if current in self.store.names():
            self.pizza_combo.setCurrentText(current)

    # ---------- отрисовка ----------

    def draw_overlay(self, canvas: QPixmap) -> QPixmap:
        """Рисует рамки детекций и мишени поверх копии изображения."""
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont("Segoe UI", 13, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        # Рамки детекций
        for d in self.detections:
            color = class_color(d.cls_name)
            painter.setPen(QPen(color, 3))
            painter.drawRect(int(d.x1), int(d.y1),
                             int(d.x2 - d.x1), int(d.y2 - d.y1))
            label = f"{d.name_ru} {d.conf:.2f}"
            text_w = metrics.horizontalAdvance(label) + 8
            text_h = metrics.height() + 4
            ty = int(d.y1) - text_h if d.y1 - text_h >= 0 else int(d.y1)
            tx = int(d.x1)
            if tx + text_w > canvas.width():  # не даем уйти за правый край
                tx = canvas.width() - text_w
            painter.fillRect(tx, ty, text_w, text_h, color)
            painter.setPen(QPen(QColor("white")))
            painter.drawText(tx + 4, ty + metrics.ascent() + 2, label)

        # Мишени «куда докинуть»
        marker_font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        painter.setFont(marker_font)
        marker_metrics = painter.fontMetrics()
        for s in self.suggestions:
            painter.setPen(QPen(MARKER_COLOR, 4))
            painter.drawEllipse(int(s.x) - 24, int(s.y) - 24, 48, 48)
            painter.drawLine(int(s.x) - 32, int(s.y), int(s.x) + 32, int(s.y))
            painter.drawLine(int(s.x), int(s.y) - 32, int(s.x), int(s.y) + 32)
            label = f"+ {s.name_ru}"
            text_w = marker_metrics.horizontalAdvance(label) + 8
            if int(s.x) + 28 + text_w <= canvas.width():  # подпись справа
                painter.fillRect(int(s.x) + 28, int(s.y) - 14, text_w, 24, MARKER_COLOR)
                painter.setPen(QPen(QColor("white")))
                painter.drawText(int(s.x) + 32, int(s.y) + 5, label)
            else:  # у правого края — подпись слева от мишени
                tx = int(s.x) - 28 - text_w
                painter.fillRect(tx, int(s.y) - 14, text_w, 24, MARKER_COLOR)
                painter.setPen(QPen(QColor("white")))
                painter.drawText(tx + 4, int(s.y) + 5, label)

        painter.end()
        return canvas

    def render_image(self) -> None:
        if self.original is None:
            return
        canvas = self.draw_overlay(QPixmap(self.original))
        scaled = canvas.scaled(self.image_label.size(),
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # noqa: N802 — имя Qt
        super().resizeEvent(event)
        if self.original is not None:
            self.render_image()

    def save_result(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить разметку", "result.png", "PNG (*.png)")
        if not path:
            return
        Path("out").mkdir(exist_ok=True)  # папка для результатов в gitignore
        canvas = self.draw_overlay(QPixmap(self.original))
        if canvas.save(path):
            self.status(f"Сохранено: {path}")

    def status(self, message: str) -> None:
        self.status_label.setText(message)


def main() -> None:
    # Необязательный аргумент: python app.py путь/к/фото.jpg —
    # открыть изображение сразу (удобно для демо и тестов).
    image_arg = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    if image_arg and Path(image_arg).exists():
        window.image_path = Path(image_arg)
        window.original = QPixmap(image_arg)
        window.clear_results()
        window.render_image()
        window.btn_detect.setEnabled(True)
        window.status(f"Загружено: {Path(image_arg).name}")
        window.run_detection()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

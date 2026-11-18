# Инструкция: обучение модели на ПК с NVIDIA GPU

Эта инструкция — для второго ПК с видеокартой. Всё делается один раз от начала
до конца (~30–40 минут вместе с ожиданием). Предполагается Windows; для Linux
отличия только в активации venv (`source .venv/bin/activate`) и путях.

## 1. Подготовка (один раз)

1. **Проверь GPU и драйвер.** Открой консоль (`Win+R` → `cmd`) и выполни:
   ```
   nvidia-smi
   ```
   В правом верхнем углу таблицы будет строка `CUDA Version: 12.x` — запомни число.
   Если команда не найдена — сначала обнови драйвер NVIDIA с nvidia.ru.

2. **Поставь, если ещё нет:**
   - Python 3.10 или новее — python.org (при установке отметь галочку **Add to PATH**);
   - Git — git-scm.com.

3. **Склонируй репозиторий и создай окружение:**
   ```
   git clone https://github.com/BullDigga/pizza-quality-control.git
   cd pizza-quality-control
   python -m venv .venv
   .venv\Scripts\activate
   ```
   *Git не ставится? На странице репозитория зелёная кнопка **Code → Download ZIP**,
   распакуй и продолжай с команды `python -m venv .venv` внутри папки.*

## 2. Установка пакетов (важен порядок — torch раньше остального)

4. **CUDA-сборка torch.** Команду выбери по версии CUDA из п.1:

   | nvidia-smi показывает | Команда |
   |---|---|
   | 12.4 и новее | `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126` |
   | 12.1 – 12.3 | `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121` |
   | 11.x | спроси у Николая/ассистента — подберём версию вручную |

5. **Остальные пакеты:**
   ```
   pip install -r requirements.txt
   ```

6. **Проверка, что GPU подхватится:**
   ```
   python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
   ```
   Должно напечатать `...+cu126 True` (или `+cu121 True`).
   Если `False` — **стоп**, дальше идти бессмысленно: пересмотри п.4 или напиши ассистенту.

## 3. Обучение и метрики

7. **Скачай датасет** (~90 МБ с HuggingFace):
   ```
   python download_dataset.py
   ```
   В конце напишет «train: 100 изображений…» на каждый сплит — это норма
   (в датасете 300 уникальных изображений).

8. **Обучение** (YOLOv8n, 50 эпох, 640px, ранняя остановка):
   ```
   python train.py --name exp01_baseline
   ```
   - В начале лога должно быть **`device=cuda`** — значит, учится на GPU.
   - Займёт ~10–25 минут (RTX-класс).
   - Если упало с `CUDA out of memory` — добавь `--batch 8` и запусти снова.
   - В конце скрипт сам напишет: «Лучшие веса: … -> weights/best.pt».

9. **Метрики и графики для отчёта:**
   ```
   python evaluate.py
   python compare_runs.py
   ```
   Появится папка `metrics/`: общие mAP/P/R, таблица по классам
   (`per_class.csv`), матрица ошибок, PR-кривая, сводка экспериментов.

## 4. Что привезти обратно на основной ноутбук

| Что | Куда положить на основном ноуте |
|---|---|
| `weights/best.pt` | `D:\pizza-quality-control\weights\best.pt` (перезаписать — так задумано) |
| папка `metrics\` целиком | `D:\pizza-quality-control\metrics\` |

После этого на основном ноуте запускается `python app.py` — уже с настоящими
весами. Файлы закоммитим в репозиторий (коммит 6).

## 5. Бонус: эксперименты для этапа 4

Схема исследования: меняешь **один** параметр, даёшь эксперименту **новое имя**,
переобучаешь:

```
python train.py --name exp02_lr005  --lr0 0.005
python train.py --name exp03_ep100 --epochs 100
python train.py --name exp04_imgsz512 --imgsz 512
python train.py --name exp05_no_mosaic --mosaic 0
```

После каждой серии:
```
python compare_runs.py
```
соберёт все эксперименты в `metrics/experiments_summary.csv` и график
`metrics/experiments_comparison.png` — готовая таблица «параметр → метрика»
для отчёта по этапу 4.

Полный список доступных параметров: `python train.py --help`.

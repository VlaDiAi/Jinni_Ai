import os, sys, logging, re, math, io
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from openpyxl import Workbook
from openpyxl.styles import Border, Side

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator_Safe")

app = FastAPI(title="MONOLIT-MOS Jarvis (Safe Mode)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class CommandRequest(BaseModel):
    command: str
    file_data_list: Optional[List[str]] = None  
    file_name_list: Optional[List[str]] = None

CURRENT_ESTIMATE_BYTES = None
BACKUP_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Джинни</title></head><body style="background:#050b14;color:#00f0ff;font-family:monospace;text-align:center;padding:50px;"><h2>[КРИТИЧЕСКАЯ ОШИБКА]: Файл index.html не найден!</h2></body></html>"""

# --- ПОПЫТКА ЗАГРУЗИТЬ ДАННЫЕ ИЗ index.py (Безопасный импорт) ---
WORK_INDEX = None
try:
    # Пытаемся импортировать WORK_INDEX из соседнего файла
    from index import WORK_INDEX
    logger.info("✅ Канонический реестр работ (index.py) успешно загружен.")
except ImportError:
    logger.warning("⚠️ Файл index.py не найден. Будет использован режим расчета монолитной плиты.")
except Exception as e:
    logger.error(f"❌ Ошибка загрузки index.py: {e}")

@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content=BACKUP_HTML, status_code=404)

@app.get("/api/download-estimate")
async def download_estimate():
    global CURRENT_ESTIMATE_BYTES
    if CURRENT_ESTIMATE_BYTES:
        return StreamingResponse(
            io.BytesIO(CURRENT_ESTIMATE_BYTES),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=estimate_batch_monolit.xlsx"}
        )
    raise HTTPException(status_code=404, detail="Смета пуста.")

@app.post("/api/command")
async def process_command(request: CommandRequest):
    global CURRENT_ESTIMATE_BYTES
    try:
        raw_query = request.command.strip()
        prefix, query = raw_query.split(": ", 1) if ": " in raw_query else ("AUTO", raw_query)
        prefix, q_low = prefix.upper(), query.lower()
        
        # Автоопределение роли
        if prefix == "AUTO":
            if any(k in q_low for k in ["радар", "скаут", "лид"]): prefix = "SCOUT"
            elif any(k in q_low for k in ["код", "обнови", "github"]): prefix = "CODER"
            elif any(k in q_low for k in ["инженер", "проект", "нагруз"]): prefix = "ENGINEER"
            elif any(k in q_low for k in ["план", "гпр", "график"]): prefix = "PLANNER"
            else: prefix = "SMETTER"

        if prefix == "SCOUT":
            return {"reply": "🕵️ [РАДАР]: Служба scout_catcher на VPS активна. Эфир Москвы чист.", "has_estimate": False}
        elif prefix == "ENGINEER":
            return {"reply": "📐 [ИНЖЕНЕР]: Конструкторский отдел готов к расчету бетона и монолита.", "has_estimate": False}
        elif prefix == "PLANNER":
            return {"reply": "📅 [ПЛАНИРОВЩИК]: Отдел планирования готов составить ГПР монолитных работ.", "has_estimate": False}
        elif prefix == "CODER":
            code_patch = (
                "import os, sys, math, openpyxl\n"
                "# Автоматический патч MONOLIT-MOS\n"
                "def calculate_monolit_estimate(floor_area, wall_area, perimeter):\n"
                "    concrete_volume = floor_area * 0.25\n"
                "    concrete_price = concrete_volume * 6500.0\n"
                "    total_sum = (wall_area * 1200.0) + (floor_area * 850.0) + concrete_price\n"
                "    total_sum = math.ceil(total_sum / 100.0) * 100\n"
                "    margin_profit = total_sum * 0.25\n"
                "    return total_sum, margin_profit, concrete_volume"
            )
            return {"reply": f"🤖 [ИИ-Кодер]: Патч сгенерирован!\n\n```python\n{code_patch}\n```", "has_estimate": False}

        # ==============================================================================
        # ГЛАВНАЯ ЛОГИКА: SMETTER
        # ==============================================================================
        if prefix == "SMETTER":
            rows = []
            total_sum = 0.0
            v_ctx = ""
            
            # 1. Попытка найти номер сборки в запросе (например, "сборка 3" или "этап 5")
            target_assembly = None
            match = re.search(r'\b(?:сборка|этап|блок)\s*(\d+)\b', q_low)
            if match:
                target_assembly = match.group(1)
            
            # 2. Если есть index.py и указана сборка -> берем из него
            if WORK_INDEX and target_assembly and target_assembly in WORK_INDEX:
                v_ctx = f"🏗️ [БРИДЖ]: Активирована сборка №{target_assembly}. Загрузка позиций из реестра...\n"
                for item in WORK_INDEX[target_assembly]:
                    cost = item["vol"] * item["price"]
                    total_sum += cost
                    rows.append({
                        "type": "Работа", 
                        "name": item["name"], 
                        "unit": item["unit"], 
                        "volume": float(item["vol"]), 
                        "price": float(item["price"])
                    })
            
            # 3. Если сборки нет или index.py не загружен -> режим "Монолит" (старый расчет)
            else:
                # Умный парсинг площадей (ищем слова "пол", "стены", "м2")
                # Ищем паттерн "число + пол" или просто первое число как пол
                floor_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:кв\.?\s*м|м2|пол)', q_low)
                wall_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:стены|стен|м2)', q_low)
                
                t_fl = float(floor_match.group(1)) if floor_match else 45.0
                t_wl = float(wall_match.group(1)) if wall_match else 110.0
                
                v_ctx = f"⚠️ [БРИДЖ]: Сборка не указана или индекс не найден. Запуск стандартного расчета монолитной плиты...\n"
                v_ctx += f"• Извлечено: Пол={t_fl} м², Стены={t_wl} м².\n"

                # Расчет бетона
                concrete_vol = t_fl * 0.25
                concrete_cost = concrete_vol * 6500.0
                rows.append({"type": "Материал", "name": "Бетон товарный B25", "unit": "м3", "volume": float(concrete_vol), "price": 6500.0})
                total_sum += concrete_cost
                
                # Расчет работ
                rows.append({"type": "Работа", "name": "Выравнивание стен под отделку", "unit": "м2", "volume": t_wl, "price": 1200.0})
                rows.append({"type": "Работа", "name": "Укладка замкового кварцвинила", "unit": "м2", "volume": t_fl, "price": 850.0})
                total_sum += (t_wl * 1200.0) + (t_fl * 850.0)

            # Финальные расчеты
            total_sum = math.ceil(total_sum / 100.0) * 100
            margin_val = total_sum * 0.25
            
            # Генерация Excel
            wb_out = Workbook()
            ws_out = wb_out.active
            ws_out.title

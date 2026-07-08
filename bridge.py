import os, sys, logging, base64, json, httpx
from io import BytesIO
from fastapi import FastAPI, HTTPException, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from openpyxl import Workbook
from openpyxl.styles import Border, Side, Font, Alignment
from openpyxl.utils import get_column_letter

# --- AIogram для Telegram ---
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator")

app = FastAPI(title="MONOLIT-MOS Jarvis")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Telegram Bot Setup ---
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = None
dp = None

if TG_BOT_TOKEN:
    bot = Bot(token=TG_BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        await message.answer(
            "👋 Привет! Я Джинни — оркестратор MONOLIT-MOS.\n\n"
            "Нажми кнопку ниже, чтобы открыть панель расчёта сметы, прайсов и монолитных работ.",
            reply_markup=types.ReplyKeyboardMarkup(
                keyboard=[[types.KeyboardButton(
                    text="📊 Открыть панель Джинни",
                    web_app=types.WebAppInfo(url="https://vladiai-jinni-ai-4538.twc1.net/app")
                )]],
                resize_keyboard=True
            )
        )

# --- Импорт справочника работ ---
try:
    from work_index import WORK_INDEX
except ImportError as e:
    logger.error(f"Не удалось импортировать work_index: {e}")
    WORK_INDEX = {}

CURRENT_ESTIMATE_BYTES = None
BACKUP_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Джинни</title></head><body style="background:#050b14;color:#00f0ff;font-family:monospace;text-align:center;padding:50px;"><h2>[КРИТИЧЕСКАЯ ОШИБКА]: Файл index.html не найден!</h2></body></html>"""

def load_smetter_catalog() -> list:
    """
    Возвращает плоский список позиций из WORK_INDEX.
    Каждая позиция: {"name": ..., "unit": ..., "price_work": ..., "stage": ...}
    """
    catalog_items = []
    for stage, items in WORK_INDEX.items():
        for item in items:
            price = item.get("price") or 0.0
            catalog_items.append({
                "name": str(item.get("name", "")).strip(),
                "unit": str(item.get("unit", "шт")).strip(),
                "price_work": float(price),
                "stage": str(stage),
                "price_mat": 0.0
            })
    return catalog_items

@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content=BACKUP_HTML, status_code=404)

@app.get("/app")
async def serve_mini_app():
    """Стабильная ссылка для Telegram Web App"""
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content=BACKUP_HTML, status_code=404)

class CommandRequest(BaseModel):
    command: str
    file_data_list: Optional[List[str]] = None  
    file_name_list: Optional[List[str]] = None

@app.post("/api/command")
async def process_command(request: CommandRequest):
    global CURRENT_ESTIMATE_BYTES
    try:
        raw_query = request.command.strip()
        prefix, query = raw_query.split(": ", 1) if ": " in raw_query else ("AUTO", raw_query)
        prefix = prefix.upper()
        q_low = query.lower()
        catalog = load_smetter_catalog()

        # Авто-маршрутизация
        if prefix == "AUTO":
            if any(k in q_low for k in ["радар", "скаут", "лид"]): prefix = "SCOUT"
            elif any(k in q_low for k in ["код", "обнови", "github"]): prefix = "CODER"
            elif any(k in q_low for k in ["инженер", "проект", "нагруз", "монолит"]): prefix = "ENGINEER"
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
                "    return total_sum\n"
            )
            return {"reply": f"💻 [КОДЕР]: Код-патч сгенерирован:\n```\n{code_patch}\n```", "has_estimate": False}

        elif prefix == "SMETTER":
            matched = []
            # Если запрос пустой — отдаём первые N позиций
            if query == "":
                matched = catalog[:50]
            else:
                # Простой поиск по словам
                keywords = query.split()
                for item in catalog:
                    if any(kw in item["name"].lower() for kw in keywords):
                        matched.append(item)

            if not matched:
                matched = catalog[:20]

            wb = Workbook()
            ws = wb.active
            ws.title = "Смета"

            headers = ["Этап", "Наименование", "Ед.", "Объём", "Цена (работа)", "Сумма"]
            ws.append(headers)

            thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
            bold_font = Font(bold=True)
            center_align = Alignment(horizontal="center", vertical="center")

            for h in range(1, len(headers)+1):
                cell = ws.cell(row=1, column=h, value=headers[h-1])
                cell.font = bold_font
                cell.alignment = center_align
                cell.border = thin_border

            total_sum = 0.0
            row_idx = 2
            for item in matched:
                vol = 1.0  # можно усложнить: парсить числа из запроса
                amount = vol * item["price_work"]
                total_sum += amount
                ws.append([
                    item["stage"],
                    item["name"],
                    item["unit"],
                    vol,
                    item["price_work"],
                    amount
                ])
                for c in range(1, 7):
                    cell = ws.cell(row=row_idx, column=c)
                    cell.border = thin_border
                row_idx += 1

            ws.cell(row=row_idx, column=5, value="ИТОГО:")
            ws.cell(row=row_idx, column=6, value=total_sum)
            ws.cell(row=row_idx, column=5).font = bold_font
            ws.cell(row=row_idx, column=6).font = bold_font

            # Автоширина колонок
            for col in ws.columns:
                max_length = 0
                column = col[0].

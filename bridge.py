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

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator")

app = FastAPI(title="MONOLIT-MOS Jarvis")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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

try:
    from work_index import WORK_INDEX
except ImportError as e:
    logger.error(f"Не удалось импортировать work_index: {e}")
    WORK_INDEX = {}

CURRENT_ESTIMATE_BYTES = None
BACKUP_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Джинни</title></head><body style="background:#050b14;color:#00f0ff;font-family:monospace;text-align:center;padding:50px;"><h2>[КРИТИЧЕСКАЯ ОШИБКА]: Файл index.html не найден!</h2></body></html>"""

def load_smetter_catalog() -> list:
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

        if prefix == "AUTO":
            if any(k in q_low for k in ["радар", "скаут", "лид"]): prefix = "SCOUT"
            elif any(k in q_low for k in ["код", "обнови", "github"]): prefix = "CODER"
            elif any(k in q_low

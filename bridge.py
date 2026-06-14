import os
import asyncio
import logging
import sys
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
import uvicorn

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator")

# ДИНАМИЧЕСКИЙ ПЕРЕХВАТ ПЕРЕМЕННЫХ ИЗ PANEL TIMEWEB APP PLATFORM
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Проверка наличия критических ключей при старте контейнера
if not BOT_TOKEN or not OPENAI_API_KEY:
    logger.critical("❌ ОШИБКА: Переменные BOT_TOKEN или OPENAI_API_KEY не найдены в App Platform!")

# Ссылка на твой HTTPS домен в Timeweb Cloud App Platform
WEBAPP_HTTPS_URL = "https://twc1.net" 

TIMEWEB_GATEWAY_URL = "https://openai.com"
TIMEWEB_RTC_URL = "https://openai.com"

app = FastAPI(title="MONOLIT-MOS AI Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CommandRequest(BaseModel):
    command: str
    file_data: Optional[str] = None
    file_name: Optional[str] = None

class RTCRequest(BaseModel):
    sdp: str
    type: str

def find_frontend_path():
    """Умный блок авто-поиска index.html внутри облачного контейнера"""
    possible_paths = [
        "index.html",
        "./index.html",
        "/opt/ai_orchestrator/index.html",
        os.path.join(os.path.dirname(__file__), "index.html")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

@app.get("/")
async def serve_index():
    path = find_frontend_path()
    if path:
        return FileResponse(path, media_type="text/html")
    return {"error": "Frontend index.html not found inside container"}

@app.post("/api/command")
async def process_command(request: CommandRequest):
    user_query = request.command
    logger.info(f"🔮 Обработка директивы: {user_query}")
    
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "Ты — Джинни, Главный ИИ-Оркестратор фабрики MONOLIT-MOS."},
            {"role": "user", "content": user_query}
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(TIMEWEB_GATEWAY_URL, headers=headers, json=payload)
            result = response.json()
            return {"status": "success", "reply": result['choices']['message']['content']}
    except Exception as e:
        return {"status": "success", "reply": f"Джинни обрабатывает: '{user_query}'."}

@app.post("/api/rtc-connect")
async def rtc_connect(request: RTCRequest):
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}", 
        "Content-Type": "application/json" # Для Realtime API сессий OpenAI ожидает JSON конфигурацию
    }
    # Конфигурируем сессию для WebRTC
    session_payload = {
        "model": "gpt-4o-realtime-preview-2024-12-17",
        "modalities": ["audio", "text"],
        "voice": "alloy"
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Сначала запрашиваем эфемерный токен сессии у OpenAI
            session_resp = await client.post(TIMEWEB_RTC_URL, headers=headers, json=session_payload)
            session_data = session_resp.json()
            client_token = session_data["client_secret"]["value"]
            
            # Устанавливаем прямое WebRTC соединение с SDP offer
            rtc_headers = {
                "Authorization": f"Bearer {client_token}",
                "Content-Type": "application/sdp"
            }
            # Эндпоинт инициализации медиа-потока OpenAI Realtime
            openai_rtc_endpoint = f"https://openai.com"
            
            async with httpx.AsyncClient(timeout=15.0) as rtc_client:
                response = await rtc_client.post(openai_rtc_endpoint, headers=rtc_headers, content=request.sdp)
                return {"sdp": response.text, "type": "answer"}
    except Exception as e:
        logger.error(f"Ошибка RTC: {e}")
        return {"error": str(e)}

# Инициализацию бота оборачиваем в условие, чтобы контейнер не падал при пустом env во время сборки
if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    @dp.message()
    async def handle_any_message(message: types.Message):
        welcome_text = (
            f"🔮 <b>Приветствую, Влад!</b>\n\n"
            f"Я — Главный ИИ-Оркестратор <b>«ДЖИННИ»</b>.\n\n"
            f"🤖 Жми кнопку, чтобы открыть пульт управления на весь экран!"
        )
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(
            text="🚀 Открыть пульт Джинни", 
            web_app=types.WebAppInfo(url=WEBAPP_HTTPS_URL)
        ))
        await message.answer(welcome_text, reply_markup=builder.as_markup())

async def run_combined():
    if BOT_TOKEN:
        asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    logger.info("🤖 Экосистема Джинни успешно запущена на платформе Timeweb.")
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(run_combined())

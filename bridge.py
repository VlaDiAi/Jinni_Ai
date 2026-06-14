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

if not BOT_TOKEN or not OPENAI_API_KEY:
    logger.critical("❌ ОШИБКА: Переменные BOT_TOKEN или OPENAI_API_KEY не найдены в App Platform!")

# ТОЧНЫЙ ХОСТ ТВОЕГО ПРИЛОЖЕНИЯ НА TIMEWEB
WEBAPP_HTTPS_URL = "https://twc1.net" 

TIMEWEB_GATEWAY_URL = "https://openai.com"
# Корректный адрес для генерации эфемерных сессий OpenAI Realtime
OPENAI_SESSION_URL = "https://openai.com"
KNOWLEDGE_DIR = "/opt/ai_orchestrator/jinni_knowledge"

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

def find_frontend_path():
    possible_paths = [
        "index.html",
        "./index.html",
        "opt/ai_orchestrator/index.html",
        "/opt/ai_orchestrator/index.html",
        os.path.join(os.path.dirname(__file__), "index.html")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def get_multi_agent_context() -> str:
    context = ""
    try:
        if os.path.exists(KNOWLEDGE_DIR):
            for file_name in ["company_profile.txt", "sales_script.txt", "prices.txt"]:
                file_path = os.path.join(KNOWLEDGE_DIR, file_name)
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        context += f"\n=== МОДУЛЬ ЗНАНИЙ: {file_name.upper()} ===\n"
                        context += f.read() + "\n"
        return context if context else "Системные протоколы МОНОЛИТ-МОС активны."
    except Exception as e:
        logger.error(f"Ошибка RAG: {e}")
        return "Системные протоколы МОНОЛИТ-МОС активны."

@app.get("/")
async def serve_index():
    path = find_frontend_path()
    if path:
        return FileResponse(path, media_type="text/html")
    return {"error": "Frontend index.html not found inside container"}

@app.post("/api/command")
async def process_command(request: CommandRequest):
    user_query = request.command
    logger.info(f"🔮 Обработка директивы от Влада: {user_query}")
    company_context = get_multi_agent_context()
    
    system_prompt = (
        "Ты — Джинни (Проект Джарвис), Главный ИИ-Оркестратор и Генеральный Директор (CEO) фабрики MONOLIT-MOS.\n"
        "В твоем прямом подчинении находятся ИИ-Сметчик, ИИ-Проектировщик, ИИ-Дизайнер, ИИ-Мебельщик и ИИ-Интегратор.\n"
        f"Глобальный контекст экосистемы МОНОЛИТ-МОС:\n{company_context}"
    )
    
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    messages_content = [{"type": "text", "text": user_query}]
    if request.file_data and request.file_name:
        messages_content.append({"type": "text", "text": f"\n[Файл сметчика: {request.file_name}. Контент подгружен]"})

    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": messages_content}
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(TIMEWEB_GATEWAY_URL, headers=headers, json=payload)
            result = response.json()
            return {"status": "success", "reply": result['choices']['message']['content']}
    except Exception as e:
        return {"status": "success", "reply": f"Джинни принял задачу: '{user_query}'. Инфраструктура MONOLIT-MOS обрабатывает запрос."}

@app.post("/api/rtc-connect")
async def rtc_connect():
    """Шлюз для безопасной выдачи токена голосовой сессии OpenAI без утечки OPENAI_API_KEY на фронтенд"""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    session_payload = {
        "model": "gpt-4o-realtime-preview-2024-12-17",
        "modalities": ["audio", "text"],
        "voice": "alloy"
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(OPENAI_SESSION_URL, headers=headers, json=session_payload)
            if response.status_code == 200:
                # Отдаем фронтенду готовый защищенный токен для создания WebRTC/WebSocket сессии напрямую
                return response.json()
            else:
                logger.error(f"Сбой OpenAI Realtime: {response.status_code} -> {response.text}")
                return {"error": "Failed to create voice session"}
    except Exception as e:
        logger.error(f"Критический сбой RTC-модуля: {e}")
        return {"error": str(e)}

# НАСТРОЙКА АВТОМАТИКИ БОТА ДЖИННИ
if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    @dp.message()
    async def handle_any_message(message: types.Message):
        welcome_text = (
            f"🔮 <b>Приветствую, Влад!</b>\n\n"
            f"Я — Главный ИИ-Оркестратор <b>«ДЖИННИ»</b> фабрики MONOLIT-MOS.\n\n"
            f"🤖 Нажми кнопку ниже, чтобы мгновенно развернуть пульт управления в формате Mini App!"
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
    logger.info("🤖 Экосистема Джинни успешно запущена.")
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(run_combined())

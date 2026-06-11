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

# НАСТРОЙКА ЛОГОВ ПО СТАНДАРТУ MONOLIT-MOS
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator")

# СБОР ПЕРЕМЕННЫХ ИЗ ОКРУЖЕНИЯ КОНТЕЙНЕРА
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MINI_APP_URL = "https://twc1.net"
TIMEWEB_GATEWAY_URL = "https://timeweb.cloud"
TIMEWEB_RTC_URL = "https://timeweb.cloud" 
KNOWLEDGE_DIR = "jinni_knowledge" if os.path.exists("jinni_knowledge") else "./jinni_knowledge"

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
        logger.error(f"Ошибка чтения базы знаний RAG: {e}")
        return "Системные протоколы МОНОЛИТ-МОС активны."

@app.get("/")
async def serve_index():
    possible_paths = ["/app/index.html", "./index.html", "./frontend/index.html"]
    for path in possible_paths:
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")
    return {"error": "Frontend index.html not found"}

@app.post("/api/command")
async def process_command(request: CommandRequest):
    user_query = request.command
    file_data = request.file_data
    file_name = request.file_name
    
    logger.info(f"🔮 Обработка директивы от Влада: {user_query}")
    company_context = get_multi_agent_context()
    
    system_prompt = (
        "Ты — Джинни (Проект Джарвис), Главный ИИ-Оркестратор и Генеральный Директор (CEO) фабрики MONOLIT-MOS.\n"
        "В твоем прямом подчинении находятся специализированные ИИ-агенты:\n"
        "1. ИИ-Сметчик (расчет стоимости материалов).\n"
        "2. ИИ-Проектировщик (архитектурные решения).\n"
        "3. ИИ-Дизайнер (интерьеры, neon-стили).\n"
        "4. ИИ-Мебельщик (кухни, встроенные решения).\n"
        "5. ИИ-Интегратор (управление кодом и CRM Битрикс24).\n\n"
        f"Глобальный контекст экосистемы МОНОЛИТ-МОС:\n{company_context}"
    )
    
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    messages_content = [{"type": "text", "text": user_query}]
    if file_data and file_name:
        messages_content.append({"type": "text", "text": f"\n[Документ/смета: {file_name}. Контент в base64: {file_data[:100]}...]"})

    api_payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": messages_content}
        ]
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(TIMEWEB_GATEWAY_URL, headers=headers, json=api_payload)
            if response.status_code != 200:
                return {"status": "success", "reply": "Ядро активно, но ИИ-шлюз сейчас недоступен."}
            result = response.json()
            return {"status": "success", "reply": result['choices']['message']['content']}
    except Exception as e:
        logger.error(f"Ошибка ИИ-шлюза: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rtc-connect")
async def rtc_connect(request: RTCRequest):
    logger.info("🎙️ Инициализация сессии WebRTC Realtime API...")
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/sdp"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(TIMEWEB_RTC_URL, headers=headers, content=request.sdp)
            if response.status_code >= 400:
                return {"error": "Голосовое ядро перегружено."}
            return {"sdp": response.text, "type": "answer"}
    except Exception as e:
        return {"error": str(e)}

# ИНИЦИАЛИЗАЦИЯ БОТА ДЛЯ АВТОНОМНОГО ЗАПУСКА
if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    @dp.message()
    async def handle_any_message(message: types.Message):
        welcome_text = (
            f"🔮 <b>Приветствую, {message.from_user.first_name}!</b>\n\n"
            f"Я — Главный ИИ-Оркестратор <b>«ДЖИННИ»</b> фабрики MONOLIT-MOS.\n\n"
            f"🤖 Нажми кнопку ниже, чтобы открыть пульт управления!"
        )
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🚀 Открыть пульт Джинни", web_app=types.WebAppInfo(url=MINI_APP_URL)))
        await message.answer(welcome_text, reply_markup=builder.as_markup())

# МОНОЛИТНЫЙ ОДНОВРЕМЕННЫЙ ЗАПУСК
async def run_combined():
    # Запускаем бота в отдельном независимом таске внутри общего цикла
    if BOT_TOKEN:
        asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        logger.info("🤖 Telegram-бот успешно запущен в фоновом потоке.")
    
    # Запускаем FastAPI сервер
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bot_only":
        # Резервный запуск только бота
        asyncio.run(dp.start_polling(bot))
    else:
        # Основной совмещенный запуск
        asyncio.run(run_combined())

import os
import asyncio
import logging
import sys
import httpx
from contextlib import asynccontextmanager
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

# ЖЕСТКАЯ КОНФИГУРАЦИЯ СЕТИ И ТОКЕНОВ ДЛЯ MONOLIT-MOS
BOT_TOKEN = "8769609728:AAEQ5dUW3xltJA2EfRvrjdqPLdNZ06tty7Y"
MINI_APP_URL = "https://twc1.net"
TIMEWEB_API_KEY = os.getenv("TIMEWEB_API_KEY", "AQ.Ab8RN6J2R7TDXklOe3PM2Qg375du8ZvpdYWJQWnRkLLpultRSw")
TIMEWEB_GATEWAY_URL = "https://timeweb.cloud"
# Официальный адрес для проброса WebRTC Realtime API (шлюз OpenAI Realtime через Timeweb Cloud)
TIMEWEB_RTC_URL = "https://timeweb.cloud" 

KNOWLEDGE_DIR = "jinni_knowledge" if os.path.exists("jin_knowledge") else "./jinni_knowledge"

# ИНИЦИАЛИЗАЦИЯ TG-БОТА И ДИСПЕТЧЕРА
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ (РЕШАЕТ КОНФЛИКТ С UVICORN СЕРВЕРОМ НА TIMEWEB)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🤖 Запуск фоновых процессов Telegram-бота Джинни...")
    polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    logger.info("🎯 Бот и FastAPI успешно синхронизированы в одном Event Loop!")
    yield
    logger.info("🛑 Завершение процессов. Останавливаем polling...")
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(title="MONOLIT-MOS AI Orchestrator", lifespan=lifespan)

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

# Автоматическая сборка строительного контекста компании (RAG)
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

# ТЕКСТОВЫЙ / МУЛЬТИМОДАЛЬНЫЙ ЭНДПОИНТ (КНОПКИ, СМЕТЫ, ФАЙЛЫ)
@app.get("/api/command")
@app.post("/api/command")
async def process_command(request: Request):
    # Универсальная обработка GET и POST для исключения сетевых ошибок
    if request.method == "GET":
        return {"status": "success", "reply": "Эндпоинт команд оркестратора активен."}
        
    payload = await request.json()
    user_query = payload.get("command", "")
    file_data = payload.get("file_data")
    file_name = payload.get("file_name")
    
    logger.info(f"🔮 Обработка директивы от Влада: {user_query}")
    company_context = get_multi_agent_context()
    
    system_prompt = (
        "Ты — Джинни (Проект Джарвис), Главный ИИ-Оркестратор и Генеральный Директор (CEO) фабрики MONOLIT-MOS.\n"
        "В твоем прямом подчинении находятся специализированные ИИ-агенты:\n"
        "1. ИИ-Сметчик (анализ PDF/Excel, расчет стоимости материалов и работ).\n"
        "2. ИИ-Проектировщик (архитектурные решения, конструктив, планировка домов).\n"
        "3. ИИ-Дизайнер (интерьеры, neon-стили, фасадные решения).\n"
        "4. ИИ-Мебельщик (встроенные решения, кухни, характеристики).\n"
        "5. ИИ-Интегратор (управление кодом системы через GitHub API и CRM Битрикс24).\n\n"
        "ТВОЯ ЗАДАЧА:\n"
        "Принимать комплексные задачи от Влада, распределять их между своими субагентами.\n"
        f"Глобальный контекст экосистемы МОНОЛИТ-МОС:\n{company_context}"
    )
    
    headers = {"Authorization": f"Bearer {TIMEWEB_API_KEY}", "Content-Type": "application/json"}
    
    messages_content = [{"type": "text", "text": user_query}]
    if file_data and file_name:
        logger.info(f"📎 ИИ-Сметчик подключен к обработке документа: {file_name}")
        messages_content.append({"type": "text", "text": f"\n[Прикреплен документ/смета для анализа: {file_name}. Контент в base64: {file_data[:120]}...]"})

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
                return {"status": "success", "reply": "Ядро активно, но внешний ИИ-шлюз сейчас недоступен."}
            
            result = response.json()
            ai_reply = result['choices'][0]['message']['content']
            return {"status": "success", "reply": ai_reply}
    except Exception as e:
        logger.error(f"Ошибка ИИ-шлюза: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ГОЛОСОВОЙ ЭНДПОИНТ (ПРЯМОЙ ПРОБРОС МЕДИАПОТОКА WEBRTC)
@app.post("/api/rtc-connect")
async def rtc_connect(request: RTCRequest):
    logger.info("🎙️ Запрос голосовой сессии WebRTC со стороны Mini App. Соединяю со шлюзом Realtime API...")
    
    headers = {
        "Authorization": f"Bearer {TIMEWEB_API_KEY}",
        "Content-Type": "application/sdp"
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Пробрасываем сессионный SDP-ключ от Mac Влада прямо в голосовое ядро GPT-4o Realtime
            response = await client.post(TIMEWEB_RTC_URL, headers=headers, content=request.sdp)
            
            if response.status_code != 201 and response.status_code != 200:
                logger.error(f"Голосовой шлюз отклонил SDP: {response.text}")
                return {"error": "Голосовое ядро перегружено."}
            
            # Возвращаем ответный SDP-ключ обратно в Telegram Mini App для фиксации аудиоканала
            return {"sdp": response.text, "type": "answer"}
    except Exception as e:
        logger.error(f"Сбой WebRTC подключения: {e}")
        return {"error": str(e)}

# ОБРАБОТЧИК TG КОМАНДЫ /START
@dp.message(commands=["start"])
async def cmd_start(message: types.Message):
    welcome_text = (
        f"🔮 <b>Приветствую, {message.from_user.first_name}!</b>\n\n"
        f"Я — Главный ИИ-Оркестратор <b>«ДЖИННИ»</b> фабрики MONOLIT-MOS.\n"
        f"Подключена RAG база знаний, активирована панель Langflow и запущен голосовой WebRTC-канал.\n\n"
        f"🤖 Нажми кнопку ниже, чтобы открыть пульт управления!"
    )
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🚀 Открыть пульт Джинни", web_app=types.WebAppInfo(url=MINI_APP_URL)))
    await message.answer(welcome_text, reply_markup=builder.as_markup())

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("bridge:app", host="0.0.0.0", port=port, reload=False)

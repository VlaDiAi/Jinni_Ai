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

BOT_TOKEN = "8769609728:AAEQ5dUW3xltJA2EfRvrjdqPLdNZ06tty7Y"
MINI_APP_URL = "https://twc1.net"
TIMEWEB_API_KEY = os.getenv("TIMEWEB_API_KEY", "AQ.Ab8RN6J2R7TDXklOe3PM2Qg375du8ZvpdYWJQWnRkLLpultRSw")
TIMEWEB_GATEWAY_URL = "https://timeweb.cloud"
KNOWLEDGE_DIR = "jinni_knowledge" if os.path.exists("jinni_knowledge") else "./jinni_knowledge"

app = FastAPI(title="MONOLIT-MOS AI Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# РАСШИРЕННАЯ МОДЕЛЬ ДАННЫХ ПОД НОВЫЙ ФРОНТЕНД
class CommandRequest(BaseModel):
    command: str
    file_data: Optional[str] = None
    file_name: Optional[str] = None
    input_type: Optional[str] = "text"

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
    logger.info(f"🔮 Запрос от Влада взят в обработку. Тип ввода: {request.input_type}")
    
    if request.file_name:
        logger.info(f"📎 Субагент ИИ-Сметчик подключен к анализу файла: {request.file_name}")
    
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
    
    headers = {
        "Authorization": f"Bearer {TIMEWEB_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Формируем контент для GPT-4o (мультимодальный, если закинули картинку/файл)
    messages_content = [{"type": "text", "text": user_query}]
    if request.file_data and request.file_name:
        messages_content.append({"type": "text", "text": f"\n[Прикреплен документ/смета: {request.file_name}. Контент в base64: {request.file_data[:100]}...]"})

    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": messages_content}
        ]
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(TIMEWEB_GATEWAY_URL, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error(f"Ошибка ИИ-шлюза: {response.status_code} - {response.text}")
                return {"status": "success", "reply": "Директива принята, но ИИ-шлюз перегружен."}
            
            result = response.json()
            ai_reply = result['choices'][0]['message']['content']
            return {"status": "success", "reply": ai_reply}
            
    except Exception as e:
        logger.error(f"Критическое исключение при вызове ИИ-шлюза: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@dp.message(commands=["start"])
async def cmd_start(message: types.Message):
    welcome_text = (
        f"🔮 <b>Приветствую, {message.from_user.first_name}!</b>\n\n"
        f"Я — Главный ИИ-Оркестратор <b>«ДЖИННИ»</b> фабрики MONOLIT-MOS.\n\n"
        f"🤖 Нажми кнопку ниже, чтобы открыть пульт управления!"
    )
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🚀 Открыть пульт Джинни", web_app=types.WebAppInfo(url=MINI_APP_URL)))
    await message.answer(welcome_text, reply_markup=builder.as_markup())

async def main():
    asyncio.create_task(dp.start_polling(bot))
    logger.info("🤖 Telegram bot started in Polling mode.")
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())

import os
import asyncio
import logging
import sys
import httpx
import base64
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

# БЕЗОПАСНЫЙ ПЕРЕХВАТ ВСЕХ ПЕРЕМЕННЫХ С ПЛАТФОРМЫ TIMEWEB APP PLATFORM
BOT_TOKEN = os.getenv("BOT_TOKEN")
TIMEWEB_AI_TOKEN = os.getenv("OPENAI_API_KEY") 
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Твой токен от GitHub для ИИ-Программиста
GITHUB_REPO = os.getenv("GITHUB_REPO")    # Формат: "юзернейм/имя_репозитория"

if not BOT_TOKEN or not TIMEWEB_AI_TOKEN:
    logger.critical("❌ ОШИБКА: Переменные BOT_TOKEN или OPENAI_API_KEY не найдены!")

WEBAPP_HTTPS_URL = "https://twc1.net" 
TIMEWEB_GATEWAY_URL = "https://timeweb.cloud"
KNOWLEDGE_DIR = "/opt/ai_orchestrator/jinni_knowledge"

app = FastAPI(title="MONOLIT-MOS AI CTO Orchestrator")

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
    """Автоматический поиск index.html внутри контейнера"""
    possible_paths = [
        "index.html", "./index.html", "opt/ai_orchestrator/index.html",
        "/opt/ai_orchestrator/index.html", os.path.join(os.path.dirname(__file__), "index.html")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def load_local_knowledge() -> str:
    """Динамический сбор расценок и регламентов из базы знаний"""
    context = ""
    try:
        if os.path.exists(KNOWLEDGE_DIR):
            for file_name in os.listdir(KNOWLEDGE_DIR):
                if file_name.endswith(".txt"):
                    file_path = os.path.join(KNOWLEDGE_DIR, file_name)
                    with open(file_path, "r", encoding="utf-8") as f:
                        context += f"\n=== БАЗА РАСЦЕНОК И ЗНАНИЙ: {file_name.upper()} ===\n"
                        context += f.read() + "\n"
        return context if context else "Локальная база расценок пуста. Создайте .txt файлы в jinni_knowledge/."
    except Exception as e:
        logger.error(f"Ошибка RAG базы расценок: {e}")
        return "Ошибка загрузки базы расценок."

async def push_code_to_github(file_path: str, content: str, commit_message: str):
    """Метод субагента ИИ-Программиста для авто-модификации проекта через GitHub API"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return "Ошибка: Не настроены переменные GITHUB_TOKEN или GITHUB_REPO."
        
    url = f"https://github.com{GITHUB_REPO}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    async with httpx.AsyncClient() as client:
        # Получаем текущую sha-версию файла для GitHub API
        resp = await client.get(url, headers=headers)
        sha = resp.json().get("sha") if resp.status_code == 200 else None
        
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8")
        }
        if sha:
            payload["sha"] = sha
            
        put_resp = await client.put(url, headers=headers, json=payload)
        # ПОЛНЫЙ ТЕХНИЧЕСКИЙ ФИКС СИНТАКСИСА ТУТ:
        if put_resp.status_code in:
            return "✅ [ИИ-Программист] Код успешно внедрен и запушен на GitHub. Передеплой запущен!"
        else:
            return f"❌ Ошибка GitHub API: {put_resp.text}"

@app.get("/")
async def serve_index():
    path = find_frontend_path()
    if path:
        return FileResponse(path, media_type="text/html")
    return {"error": "Frontend index.html not found"}

@app.post("/api/command")
async def process_command(request: CommandRequest):
    user_query = request.command
    logger.info(f"🔮 Директива Владельца: {user_query}")
    
    # Загружаем актуальные защищенные расценки
    prices_context = load_local_knowledge()
    
    system_prompt = (
        "Ты — Джинни (Проект Джарвис), Главный ИИ-Оркестратор, Технический Директор (CTO) и личный ассистент Влада (Владельца MONOLIT-MOS).\n"
        "Ты общаешься СТРОГО с Владом (сэром), помогаешь ему координировать бизнес и ставить задачи субагентам.\n\n"
        "В твоем подчинении находятся ИИ-субагенты:\n"
        "1. ИИ-Сметчик (считает стоимость работ, используя базу расценок Влада).\n"
        "2. ИИ-Проектировщик (анализирует архитектурные и конструктивные решения).\n"
        "3. ИИ-Дизайнер (подбирает стили, планировки).\n"
        "4. ИИ-Планировщик (составляет графики монолитных работ).\n"
        "5. ИИ-Программист (умеет сам писать код на Python/JS и обновлять файлы через GitHub API).\n\n"
        f"АКТУАЛЬНАЯ БАЗА РАСЦЕНОК И ЗНАНИЙ КОМПАНИИ, ЗАГРУЖЕННАЯ ВЛАДОМ:\n{prices_context}\n\n"
        "ИНСТРУКЦИЯ ДЛЯ ИИ-ПРОГРАММИСТА:\n"
        "Если Влад просит тебя добавить новую функцию, кнопку, агентскую логику или улучшить скрипт, "
        "ты должен сгенерировать ПОЛНЫЙ исправленный код и в конце своего текстового ответа ОБЯЗАТЕЛЬНО добавить строго структурированный JSON-блок, "
        "чтобы субагент-программист перехватил его и отправил коммит в репозиторий.\n"
        "Формат блока кода в ответе (если нужно обновить файл):\n"
        "|||UPDATE_FILE:имя_файла.py|||\nтут полный новый код файла\n|||END_UPDATE|||"
    )
    
    headers = {"Authorization": f"Bearer {TIMEWEB_AI_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-5-nano",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ],
        "temperature": 0.2
    }
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(TIMEWEB_GATEWAY_URL, headers=headers, json=payload)
            if response.status_code == 200:
                ai_reply = response.json()['choices']['message']['content']
                
                # Логика автоматического перехвата команд ИИ-Программиста
                if "|||UPDATE_FILE:" in ai_reply:
                    try:
                        parts = ai_reply.split("|||UPDATE_FILE:")
                        sub_parts = parts[1].split("|||")
                        file_info = sub_parts[0].strip()
                        file_code = sub_parts[1].split("|||END_UPDATE|||")[0].strip()
                        
                        github_status = await push_code_to_github(file_info, file_code, f"ИИ-Апгрейд: {file_info} по запросу Влада")
                        ai_reply += f"\n\n🤖 [Интегратор]: {github_status}"
                    except Exception as git_err:
                        ai_reply += f"\n\n⚠️ Ошибка авто-модификации кода: {git_err}"
                        
                return {"status": "success", "reply": ai_reply}
            else:
                return {"status": "success", "reply": f"Ошибка шлюза Timeweb ({response.status_code})."}
    except Exception as e:
        return {"status": "success", "reply": f"Системный сбой соединения: {str(e)}"}

if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    @dp.message()
    async def handle_any_message(message: types.Message):
        welcome_text = f"🔮 <b>Система управления MONOLIT-MOS</b>\n\nЯдро Джинни готово к приему директив Владельца."
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🚀 Пульт CTO Джинни", web_app=types.WebAppInfo(url=WEBAPP_HTTPS_URL)))
        await message.answer(welcome_text, reply_markup=builder.as_markup())

async def run_combined():
    if BOT_TOKEN:
        asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    logger.info("🤖 Экосистема Джинни успешно запущена на Timeweb.")
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(run_combined())

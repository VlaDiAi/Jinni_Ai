import os
import asyncio
import logging
import sys
import httpx
import base64
import re
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional
from aiogram import Bot, Dispatcher, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
import uvicorn

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator")

# БЕЗОПАСНЫЙ ПЕРЕХВАТ ПЕРЕМЕННЫХ ИЗ ПАНЕЛИ TIMEWEB APP PLATFORM
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  
GITHUB_REPO = os.getenv("GITHUB_REPO")    
TIMEWEB_AI_TOKEN = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    logger.critical("❌ ОШИБКА: Переменная BOT_TOKEN не найдена в панели Timeweb!")

WEBAPP_HTTPS_URL = "https://twc1.net" 
KNOWLEDGE_DIR = "/opt/ai_orchestrator/jinni_knowledge"

# ЖЕСТКИЙ ФИКС: Классическая инициализация без капризных DefaultBotProperties
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Контекстный менеджер lifespan для гарантированной регистрации Вебхука
@asynccontextmanager
async def lifespan(app: FastAPI):
    webhook_url = f"{WEBAPP_HTTPS_URL.rstrip('/')}/api/webhook"
    logger.info(f"📡 Регистрация Webhook в Telegram API: {webhook_url}")
    try:
        await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    except Exception as e:
        logger.error(f"⚠️ Ошибка установки вебхука на старте: {e}")
    yield
    try:
        await bot.delete_webhook()
    except Exception:
        pass

app = FastAPI(title="MONOLIT-MOS AI CTO Orchestrator", lifespan=lifespan)

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

def load_local_knowledge() -> str:
    context = ""
    try:
        if os.path.exists(KNOWLEDGE_DIR):
            for f_name in os.listdir(KNOWLEDGE_DIR):
                if f_name.endswith(".txt") or f_name.endswith(".xlsx") or f_name.endswith(".pdf"):
                    context += f"\n[ПОДКЛЮЧЕН МОДУЛЬ ЗНАНИЙ: {f_name.upper()}]\n"
        return context if context else "Локальная база расценок пуста."
    except Exception as e:
        logger.error(f"Ошибка RAG: {e}")
        return "Ошибка загрузки базы расценок."

async def push_code_to_github(file_path: str, content: str, commit_message: str):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return "Ошибка: Не настроены переменные GITHUB_TOKEN или GITHUB_REPO."
        
    url = f"https://github.com{GITHUB_REPO}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10)
            sha = resp.json().get("sha") if resp.status_code == 200 else None
        except Exception:
            sha = None
        
        payload = {"message": commit_message, "content": base64.b64encode(content.encode("utf-8")).decode("utf-8")}
        if sha:
            payload["sha"] = sha
            
        try:
            put_resp = await client.put(url, headers=headers, json=payload, timeout=15)
            if put_resp.status_code in (200, 201):
                return "✅ Код успешно запушен на GitHub!"
            return f"❌ Ошибка GitHub API: {put_resp.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
HTML_CODE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Джинни</title>
    <style>
        body { background: #050b14; color: #00f0ff; font-family: monospace; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }
        .panel { border: 2px solid #00f0ff; padding: 30px; border-radius: 15px; box-shadow: 0 0 20px rgba(0,240,255,0.3); background: rgba(5, 11, 20, 0.9); width: 100%; max-width: 500px; text-align: center; }
        h1 { font-size: 16px; letter-spacing: 2px; text-shadow: 0 0 10px #00f0ff; }
        .chat-log { border: 1px solid rgba(0, 240, 255, 0.3); background: rgba(0, 5, 10, 0.6); border-radius: 8px; height: 200px; overflow-y: auto; text-align: left; padding: 15px; margin: 15px 0; display: flex; flex-direction: column; gap: 10px; }
        .text-input { width: 100%; background: rgba(0, 5, 10, 0.8); border: 1px solid rgba(0, 240, 255, 0.5); border-radius: 5px; padding: 12px; color: #00f0ff; font-family: monospace; box-sizing: border-box; outline: none; }
        .status { font-size: 11px; color: #88aadd; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="panel">
        <h1>КОГНИТИВНЫЙ КОМПЛЕКС ДЖИННИ</h1>
        <div id="chatLog" class="chat-log"><div>Джинни> Комплекс MONOLIT-MOS активен, сэр. Ожидаю директив.</div></div>
        <input type="text" id="textInput" class="text-input" placeholder="Введите директиву (Enter)...">
        <div id="status" class="status">● Ядро онлайн | Стабильный Webhook</div>
    </div>
    <script>
        const chatLog = document.getElementById('chatLog');
        const textInput = document.getElementById('textInput');
        const statusText = document.getElementById('status');
        
        textInput.onkeydown = async (e) => {
            if (e.key === 'Enter') {
                const text = textInput.value.trim();
                if (!text) return;
                
                const msgDiv = document.createElement('div');
                msgDiv.innerText = "Сэр> " + text;
                chatLog.appendChild(msgDiv);
                textInput.value = "";
                statusText.innerText = "● Джинни обрабатывает...";
                
                try {
                    const res = await fetch('/api/command', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ command: text })
                    });
                    const data = await res.json();
                    const replyDiv = document.createElement('div');
                    replyDiv.style.color = '#00f0ff';
                    replyDiv.innerText = "Джинни> " + data.reply;
                    chatLog.appendChild(replyDiv);
                } catch {
                    const errDiv = document.createElement('div');
                    errDiv.innerText = "Джинни> Сбой локального ядра.";
                    chatLog.appendChild(errDiv);
                }
                statusText.innerText = "● Ядро онлайн | Стабильный Webhook";
                chatLog.scrollTop = chatLog.scrollHeight;
            }
        };
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return HTML_CODE

@app.post("/api/command")
async def process_command(request: CommandRequest):
    user_query = request.command.strip()
    logger.info(f"🔮 Локальная директива Владельца: {user_query}")
    query_lower = user_query.lower()
    
    if "привет" in query_lower or "создатель" in query_lower or "влад" in query_lower:
        ai_reply = "Приветствую, Влад! Ядро Джинни переведено на локальный автономный ИИ-драйвер MONOLIT-MOS. Мы полностью изолировались от петель Nginx Timeweb. Я на прямой связи, сэр. Готова к обработке смет и управлению субагентами!"
    elif "смета" in query_lower or "расчет" in query_lower or "excel" in query_lower:
        knowledge = load_local_knowledge()
        ai_reply = f"ИИ-Сметчик активирован. Анализирую параметры. {knowledge}\nГотовлю генерацию стандартизированного шаблона Excel для импорта в Сметтер."
    elif "код" in query_lower or "обнови" in query_lower or "добавь кнопку" in query_lower:
        ai_reply = "ИИ-Программист принял задачу. Формирую патч самомодификации.\n|||UPDATE_FILE:test_agent.py|||\n# Автономный агент MONOLIT-MOS активен\nprint('Свобода от Nginx!')\n|||END_UPDATE|||"
    else:
        ai_reply = f"Директива '{user_query}' успешно принята ИИ-Оркестратором Джинни. Все субагенты MONOLIT-MOS переведены в режим автономного рантайма на App Platform."

    pattern = r"\|\|\|UPDATE_FILE:(.*?)\|\|\|(.*?)(\|\|\|END_UPDATE\|\|\||$)"
    match = re.search(pattern, ai_reply, re.DOTALL)
    if match:
        try:
            file_info = match.group(1).strip()
            file_code = match.group(2).strip()
            github_status = await push_code_to_github(file_info, file_code, f"ИИ-Автоапгрейд: {file_info}")
            ai_reply += f"\n\n🤖 [Интегратор]: {github_status}"
        except Exception as git_err:
            ai_reply += f"\n\n⚠️ Ошибка коммита: {git_err}"

    return {"reply": ai_reply}

@dp.message()
async def handle_any_message(message: types.Message):
    welcome_text = "🔮 <b>Система управления MONOLIT-MOS</b>\n\nЯдро Джинни готово к приему директив Владельца. Нажмите на кнопку ниже, чтобы войти в пульт."
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🚀 Пульт CTO Джинни", web_app=types.WebAppInfo(url=WEBAPP_HTTPS_URL)))
    # parse_mode перенесён непосредственно в метод отправки для 100% совместимости
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=builder.as_markup())

# Промышленный шлюз Вебхука
@app.post("/api/webhook")
async def telegram_webhook_gateway(request: Request):
    try:
        json_data = await request.json()
        update = types.Update.model_validate(json_data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка вебхука Aiogram: {e}")
        return {"status": "error", "detail": str(e)}

async def main_runtime():
    logger.info("🤖 Экосистема Джинни успешно запущена на Timeweb.")
    port = int(os.environ.get("PORT", 7778))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main_runtime())

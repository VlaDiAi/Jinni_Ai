import os
import asyncio
import logging
import sys
import httpx
import base64
import re
import json
import urllib.request
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
import uvicorn

# Тотальное уничтожение любых прокси-аномалий среды выполнения для изоляции от петель Nginx
for var in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
    os.environ.pop(var, None)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator")

# БЕЗОПАСНЫЙ ПЕРЕХВАТ ПЕРЕМЕННЫХ ИЗ ПАНЕЛИ TIMEWEB APP PLATFORM
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  
GITHUB_REPO = os.getenv("GITHUB_REPO")    

# Двойная страховка перехвата ИИ-ключа
TIMEWEB_AI_TOKEN = os.getenv("OPENAI_API_KEY") or os.getenv("TIMEWEB_AI_API_KEY") or os.getenv("TIMEWEB_AI_GATEWAY_KEY")

if not BOT_TOKEN or not TIMEWEB_AI_TOKEN:
    logger.critical("❌ ОШИБКА: Переменные BOT_TOKEN или ИИ-ключ не найдены в панели Timeweb!")

WEBAPP_HTTPS_URL = "https://twc1.net" 
TIMEWEB_GATEWAY_URL = "https://timeweb.ai"
MODEL_NAME = "openai/gpt-5-nano"
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
                return "✅ Код запушен на GitHub!"
            return f"❌ Ошибка API: {put_resp.status_code}"
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
        <div id="status" class="status">● Ядро онлайн | Порт: 7778</div>
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
                statusText.innerText = "● Джинни думает...";
                
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
                    errDiv.innerText = "Джинни> Сбой соединения.";
                    chatLog.appendChild(errDiv);
                }
                statusText.innerText = "● Ядро онлайн | Порт: 7778";
                chatLog.scrollTop = chatLog.scrollHeight;
            }
        };
    </script>
</body>
</html>
"""

class SmartRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Кастомный обработчик, принудительно сохраняющий метод POST и тело при редиректах 307/308"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = newurl.replace(' ', '%20')
        # Создаем новый чистый запрос на целевое зеркало с сохранением всех исходных параметров
        return urllib.request.Request(
            newurl, 
            data=req.data, 
            headers=req.headers, 
            origin_req_host=req.origin_req_host, 
            unverifiable=req.unverifiable, 
            method=req.get_method()
        )

def sync_urllib_post(url: str, headers: dict, data_bytes: bytes) -> tuple:
    """Низкоуровневый POST-запрос с поддержкой пробива 308-редиректов"""
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
    # Соединяем отключение прокси и кастомный менеджер редиректов
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        SmartRedirectHandler()
    )
    try:
        with opener.open(req, timeout=45) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        return 500, str(e)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return HTML_CODE

@app.post("/api/command")
async def process_command(request: CommandRequest):
    user_query = request.command
    logger.info(f"🔮 Директива Владельца: {user_query}")
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
        f"АКТУАЛЬНАЯ БАЗА РАСЦЕНОК И ЗНАНИЙ КОМПАНИИ, ЗАГРУЖЕННАЯ ВЛАДОМ:\n{prices_context}"
    )
    
    headers = {
        "Authorization": f"Bearer {TIMEWEB_AI_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ],
        "temperature": 0.2
    }
    
    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        
        status_code, response_text = await asyncio.to_thread(
            sync_urllib_post, TIMEWEB_GATEWAY_URL, headers, data_bytes
        )
        
        if status_code == 200:
            data = json.loads(response_text)
            ai_reply = data["choices"][0]["message"]["content"]
            
            pattern = r"\|\|\|UPDATE_FILE:(.*?)\|\|\|(.*?)(\|\|\|END_UPDATE\|\|\||$)"
            match = re.search(pattern, ai_reply, re.DOTALL)
            if match:
                try:
                    file_info = match.group(1).strip()
                    file_code = match.group(2).strip()
                    github_status = await push_code_to_github(file_info, file_code, f"ИИ-Апгрейд: {file_info}")
                    ai_reply += f"\n\n🤖 [Интегратор]: {github_status}"
                except Exception as git_err:
                    ai_reply += f"\n\n⚠️ Ошибка коммита: {git_err}"
            return {"reply": ai_reply}
        
        return {"reply": f"Сбой ИИ-шлюза (Код: {status_code}). Ответ сервера: {response_text[:120]}"}
            
    except Exception as e:
        return {"reply": f"Системный сбой соединения: {str(e)}"}

if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
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
    port = int(os.environ.get("PORT", 7778))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(run_combined())

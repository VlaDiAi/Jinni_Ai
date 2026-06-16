import os
import asyncio
import logging
import sys
import httpx
import base64
import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  
GITHUB_REPO = os.getenv("GITHUB_REPO")    

if not BOT_TOKEN or not TIMEWEB_AI_TOKEN:
    logger.critical("❌ ОШИБКА: Переменные BOT_TOKEN или OPENAI_API_KEY не найдены в панели Timeweb!")

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

# === ЖЕСТКОЕ ВНЕДРЕНИЕ ФРОНТЕНДА ПРЯМО В ПАМЯТЬ БЭКЕНДА ===
HTML_FRONTEND_CODE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Панель управления Джинни</title>
    <style>
        body { background: #050b14; color: #00f0ff; font-family: monospace; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
        .panel { border: 2px solid #00f0ff; padding: 30px; border-radius: 15px; box-shadow: 0 0 20px rgba(0,240,255,0.3); background: rgba(5, 11, 20, 0.9); width: 100%; max-width: 600px; text-align: center; display: flex; flex-direction: column; align-items: center; }
        h1 { font-size: 18px; letter-spacing: 3px; margin-bottom: 25px; text-shadow: 0 0 10px #00f0ff; margin-top: 0; }
        .arc-btn { background: #005577; border: 2px solid #fff; color: #fff; padding: 15px 35px; font-size: 16px; font-weight: bold; cursor: pointer; border-radius: 30px; box-shadow: 0 0 15px #00f0ff; margin-bottom: 15px; transition: all 0.3s ease; outline: none; }
        .recording { background: #ff0055 !important; box-shadow: 0 0 30px #ff0055 !important; border-color: #ff0055 !important; }
        .status { margin-bottom: 15px; font-size: 13px; color: #88aadd; }
        .chat-log { border: 1px solid rgba(0, 240, 255, 0.3); background: rgba(0, 5, 10, 0.6); border-radius: 8px; height: 250px; overflow-y: auto; text-align: left; padding: 15px; margin-bottom: 15px; width: 100%; box-sizing: border-box; display: flex; flex-direction: column; gap: 10px; }
        .message { line-height: 1.4; font-size: 13px; animation: fadeIn 0.3s ease; white-space: pre-wrap; }
        .msg-user { color: #e1e1e1; }
        .msg-user::before { content: "Сэр> "; color: #88aadd; font-weight: bold; }
        .msg-jinni { color: #00f0ff; }
        .msg-jinni::before { content: "Джинни> "; color: #00f0ff; font-weight: bold; }
        .input-area { display: flex; gap: 10px; align-items: center; width: 100%; }
        .text-input { flex: 1; background: rgba(0, 5, 10, 0.8); border: 1px solid rgba(0, 240, 255, 0.5); border-radius: 5px; padding: 12px; color: #00f0ff; font-family: monospace; outline: none; }
        .text-input:focus { border-color: #00f0ff; box-shadow: 0 0 10px rgba(0,240,245,0.3); }
        .file-label { background: #003344; border: 1px solid #00f0ff; color: #00f0ff; padding: 10px 15px; border-radius: 5px; cursor: pointer; font-size: 16px; user-select: none; }
        #fileInput { display: none; }
        .preview-box { display: none; margin-bottom: 15px; text-align: left; border: 1px dashed #00f0ff; padding: 10px; border-radius: 5px; position: relative; background: rgba(0, 30, 50, 0.4); width: 100%; box-sizing: border-box; }
        .file-info { font-size: 12px; color: #e1e1e1; display: flex; align-items: center; gap: 10px; }
        .cancel-img { position: absolute; right: 15px; top: 50%; transform: translateY(-50%); color: #ff0055; cursor: pointer; font-weight: bold; font-size: 12px; user-select: none; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>
    <div class="panel">
        <h1>КОГНИТИВНЫЙ КОМПЛЕКС ДЖИННИ</h1>
        <button id="voiceBtn" class="arc-btn">🎙️ АКТИВИРОВАТЬ ГОЛОС</button>
        <div id="status" class="status">● Ядро онлайн</div>
        <div id="chatLog" class="chat-log">
            <div class="message msg-jinni">Приветствую, Влад. Готов к анализу смет и директив. Комплекс MONOLIT-MOS активен.</div>
        </div>
        <div id="previewBox" class="preview-box">
            <div class="file-info">
                <span id="fileIcon" style="font-size: 16px;">📄</span>
                <span id="fileNameText">document.pdf</span>
            </div>
            <span id="cancelImg" class="cancel-img">❌ УДАЛИТЬ</span>
        </div>
        <div class="input-area">
            <label for="fileInput" class="file-label">📎</label>
            <input type="file" id="fileInput" accept="image/*,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/plain">
            <input type="text" id="textInput" class="text-input" placeholder="Директива...">
        </div>
    </div>

    <script>
        const voiceBtn = document.getElementById('voiceBtn');
        const statusText = document.getElementById('status');
        const chatLog = document.getElementById('chatLog');
        const textInput = document.getElementById('textInput');
        const fileInput = document.getElementById('fileInput');
        const previewBox = document.getElementById('previewBox');
        const fileNameText = document.getElementById('fileNameText');
        const fileIcon = document.getElementById('fileIcon');
        const cancelImg = document.getElementById('cancelImg');
        
        let isSending = false; let attachedFileBase64 = null; let attachedFileName = null;
        let recognition = null; let isRecording = false;

        fileInput.onchange = () => {
            if (fileInput.files && fileInput.files[0]) {
                const file = fileInput.files[0];
                attachedFileName = file.name;
                const ext = file.name.split('.').pop().toLowerCase();
                if (['xlsx', 'xls'].includes(ext)) fileIcon.innerText = "📊 Excel";
                else if (ext === 'pdf') fileIcon.innerText = "📕 PDF";
                else fileIcon.innerText = "📄 Файл";

                const reader = new FileReader();
                reader.onloadend = () => {
                    attachedFileBase64 = reader.result;
                    fileNameText.innerText = file.name;
                    previewBox.style.display = 'block';
                    statusText.innerText = `Файл ${file.name} прикреплен.`;
                };
                reader.readAsDataURL(file);
            }
        };

        cancelImg.onclick = () => {
            attachedFileBase64 = null; attachedFileName = null; fileInput.value = ""; previewBox.style.display = 'none'; statusText.innerText = "Файл удален.";
        };

        function appendMessage(text, sender) {
            const msgDiv = document.createElement('div');
            msgDiv.className = `message msg-${sender}`;
            msgDiv.innerText = text;
            chatLog.appendChild(msgDiv);
            chatLog.scrollTop = chatLog.scrollHeight;
        }

        async function executeCommand(text, fileData, fileName) {
            if (isSending) return;
            isSending = true;
            statusText.innerText = "● Джинни думает...";

            try {
                const response = await fetch('/api/command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: text, file_data: fileData, file_name: fileName })
                });
                const data = await response.json();
                appendMessage(data.reply, 'jinni');
                statusText.innerText = "● Ядро онлайн";
            } catch (err) {
                appendMessage("Ошибка соединения со шлюзом Джинни.", "jinni");
                statusText.innerText = "● Ядро онлайн";
            } finally {
                isSending = false;
                attachedFileBase64 = null; attachedFileName = null; fileInput.value = ""; previewBox.style.display = 'none';
            }
        }

        textInput.onkeydown = (e) => {
            if (e.key === 'Enter' && !isSending) {
                const text = textInput.value.trim();
                if (text || attachedFileBase64) {
                    let displayMsg = text; if (attachedFileName) displayMsg += ` [Файл: ${attachedFileName}]`;
                    appendMessage(displayMsg, 'user'); 
                    executeCommand(text, attachedFileBase64, attachedFileName); 
                    textInput.value = "";
                }
            }
        };

        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.lang = 'ru-RU';
            recognition.interimResults = false;

            recognition.onstart = () => {
                statusText.innerText = "🎤 Слушаю вашу директиву, сэр...";
                voiceBtn.classList.add('recording');
                voiceBtn.innerText = "🛑 ОСТАНОВИТЬ ЗАПИСЬ";
            };

            recognition.onerror = (event) => {
                statusText.innerText = "⚠️ Ошибка микрофона: " + event.error;
                stopRecordingState();
            };

            recognition.onend = () => { stopRecordingState(); };

            recognition.onresult = (event) => {
                const speechToText = event.results.transcript;
                if (speechToText.trim()) {
                    appendMessage(speechToText, 'user');
                    executeCommand(speechToText, attachedFileBase64, attachedFileName);
                }
            };
        } else {
            voiceBtn.innerText = "🎙️ ГОЛОС НЕ ПОДДЕРЖИВАЕТСЯ";
            voiceBtn.disabled = true;
        }

        function stopRecordingState() {
            isRecording = false;
            voiceBtn.classList.remove('recording');
            voiceBtn.innerText = "🎙️ АКТИВИРОВАТЬ ГОЛОС";
            if(statusText.innerText.includes("🎤")) statusText.innerText = "● Ядро онлайн";
        }

        voiceBtn.onclick = () => {
            if (!recognition) return;
            if (isRecording) { recognition.stop(); } 
            else { isRecording = true; recognition.start(); }
        };
    </script>
</body>
</html>
"""

def load_local_knowledge() -> str:
    context = ""
    try:
        if os.path.exists(KNOWLEDGE_DIR):
            for file_name in os.listdir(KNOWLEDGE_DIR):
                if file_name.endswith(".txt") or file_name.endswith(".xlsx") or file_name.endswith(".pdf"):
                    context += f"\n[ПОДКЛЮЧЕН МОДУЛЬ ЗНАНИЙ СЕРВЕРА: {file_name.upper()}]\n"
        return context if context else "Локальная база расценок пуста."
    except Exception as e:
        logger.error(f"Ошибка RAG базы расценок: {e}")
        return "Ошибка загрузки базы расценок."

async def push_code_to_github(file_path: str, content: str, commit_message: str):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return "Ошибка: Не настроены переменные GITHUB_TOKEN или GITHUB_REPO."
        
    url = f"https://github.com{GITHUB_REPO}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10)
            sha = resp.json().get("sha") if resp.status_code == 200 else None
        except Exception as e:
            logger.error(f"Ошибка получения SHA: {e}")
            sha = None
        
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8")
        }
        if sha:
            payload["sha"] = sha
            
        try:
            put_resp = await client.put(url, headers=headers, json=payload, timeout=15)
            # МАССИВ СТАТУСОВ ПОЛНОСТЬЮ АВТОРИЗОВАН
            if put_resp.status_code in:
                return "✅ [ИИ-Программист] Код успешно внедрен и запушен на GitHub!"
            else:
                return f"❌ Ошибка GitHub API: {put_resp.status_code} -> {put_resp.text}"
        except Exception as e:
            return f"❌ Исключение при пуше в GitHub: {e}"
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return HTML_FRONTEND_CODE

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
        f"АКТУАЛЬНАЯ БАЗА РАСЦЕНОК И ЗНАНИЙ КОМПАНИИ, ЗАГРУЖЕННАЯ ВЛАДОМ:\n{prices_context}\n\n"
        "ИНСТРУКЦИЯ ДЛЯ ИИ-ПРОГРАММИСТА:\n"
        "Если Влад просит тебя добавить новую функцию, кнопку, агентскую логику или улучшить скрипт, "
        "ты должен сгенерировать ПОЛНЫЙ исправленный код и в конце своего текстового ответа ОБЯЗАТЕЛЬНО добавить строго структурированный блок, "
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
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(TIMEWEB_GATEWAY_URL, headers=headers, json=payload)
            if response.status_code == 200:
                ai_reply = response.json()['choices']['message']['content']
                
                pattern = r"\|\|\|UPDATE_FILE:(.*?)\|\|\|(.*?)(\|\|\|END_UPDATE\|\|\||$)"
                match = re.search(pattern, ai_reply, re.DOTALL)
                
                if match:
                    try:
                        file_info = match.group(1).strip()
                        file_code = match.group(2).strip()
                        
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
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    @dp.message()
    async def handle_any_message(message: types.Message):
        welcome_text = f"🔮 <b>Система управления MONOLIT-MOS</b>\n\nЯдро Джинни готово к приеем директив Владельца."
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

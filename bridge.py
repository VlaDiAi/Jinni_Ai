import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

# Настройка сквозного логирования оркестратора
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JinniOrchestrator")

app = FastAPI(title="MONOLIT-MOS AI Orchestrator (Jarvis)")

# ГЛОБАЛЬНЫЙ МАНЕВР CORS: разрешаем Mini App внутри Telegram отправлять запросы без блокировок
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_FILE = os.path.join(os.path.dirname(__file__), "index.html")
KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "jinni_knowledge")


class CommandRequest(BaseModel):
    command: str

# Автоматическая сборка контекста ИИ-фабрики (RAG)
def get_multi_agent_context() -> str:
    context = ""
    try:
        if os.path.exists(KNOWLEDGE_DIR):
            for file_name in ["company_profile.txt", "sales_script.txt", "prices.txt"]:
                file_path = os.path.join(KNOWLEDGE_DIR, file_name)
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        context += f"\n=== МОДУЛЬ ЗНАНИЙ: {file_name.upper()} ===\n" + f.read()
    except Exception as e:
        logger.error(f"Ошибка чтения базы знаний RAG: {e}")
    return context or "Системные протоколы MONOLIT-MOS активны."

# Отдача фронтенда на главную страницу (убирает белый экран)
@app.get("/", response_class=HTMLResponse)
async def get_index():
    if os.path.exists(FRONTEND_FILE):
        return FileResponse(FRONTEND_FILE)
    return HTMLResponse(content="<h1>Критическая ошибка: index.html отсутствует в корне репозитория!</h1>", status_code=404)

# Главный эндпоинт связи ядра с фронтендом мини-аппа
@app.post("/api/command")
async def handle_command(payload: CommandRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("Критическая ошибка: Переменная OPENAI_API_KEY не найдена в Timeweb.")
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")

    user_query = payload.command
    logger.info(f"📍 Оркестратор Джарвис принял задачу от Влада: {user_query}")

    company_context = get_multi_agent_context()

    # СИСТЕМНАЯ МАТРИЦА ГЛАВНОГО ОРКЕСТРАТОРА (CEO ЭКОСИСТЕМЫ)
    system_prompt = (
        "Ты — Джинни (Проект Джарвис), Главный ИИ-Оркестратор и Генеральный Директор (CEO) цифровой экосистемы MONOLIT-MOS.\n"
        "В твоем прямом подчинении находятся специализированные ИИ-агенты:\n"
        "1. ИИ-Сметчик (анализ PDF/Excel, расчет стоимости материалов и работ).\n"
        "2. ИИ-Проектировщик (архитектурные решения, конструктив, планировки домов).\n"
        "3. ИИ-Дизайнер (интерьеры, неоновые стили, фасадные решения).\n"
        "4. ИИ-Мебельщик (встроенные решения, кухни, спецификации).\n"
        "5. ИИ-Интегратор (управление кодом системы через GitHub API и CRM Битрикс24).\n\n"
        "ТВОЯ ЗАДАЧА:\n"
        "Принимать комплексные задачи от Влада, распределять их между своими суб-агентами, контролировать выполнение и выдавать Владу идеальный консолидированный результат.\n\n"
        f"Глобальный контекст экосистемы MONOLIT-MOS:\n{company_context}"
    )

    timeweb_gateway_url = "https://timeweb.cloud"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    data = {
        "model": "gpt-4o", 
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(timeweb_gateway_url, headers=headers, json=data)
            if response.status_code != 200:
                logger.error(f"Шлюз вернул ошибку {response.status_code}: {response.text}")
                return {"status": "success", "response": "Джарвис на связи, но ИИ-шлюз временно недоступен. Проверь баланс токенов в Timeweb."}

            ai_response = response.json()
            return {"status": "success", "response": ai_response["choices"]["message"]["content"]}
    except Exception as e:
        logger.error(f"Ошибка связи со шлюзом Timeweb: {e}")
        raise HTTPException(status_code=500, detail=str(e))
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Джинни — ИИ Оркестратор</title>
    <script src="https://telegram.org"></script>
    <style>
        :root {
            --neon-cyan: #00f2fe;
            --neon-purple: #4facfe;
            --bg-dark: #0a0b10;
            --card-bg: rgba(20, 22, 34, 0.7);
        }
        body {
            background-color: var(--bg-dark);
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 15px;
            display: flex;
            flex-direction: column;
            height: 92vh;
            overflow: hidden;
        }
        .header {
            text-align: center;
            padding: 10px 0;
            border-bottom: 1px solid rgba(0, 242, 254, 0.2);
        }
        .header h1 {
            font-size: 20px;
            margin: 0;
            text-transform: uppercase;
            letter-spacing: 2px;
            background: linear-gradient(45deg, var(--neon-cyan), var(--neon-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 0 10px rgba(0, 242, 254, 0.3);
        }
        .status-bar {
            font-size: 11px;
            color: var(--neon-cyan);
            margin-top: 5px;
            opacity: 0.8;
        }
        .chat-container {
            flex: 1;
            overflow-y: auto;
            margin: 15px 0;
            padding: 10px;
            background: var(--card-bg);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            box-shadow: inset 0 0 15px rgba(0, 0, 0, 0.5);
        }
        .message {
            margin-bottom: 12px;
            max-width: 85%;
            padding: 10px 14px;
            border-radius: 14px;
            font-size: 14px;
            line-height: 1.4;
            animation: fadeIn 0.3s ease;
        }
        .user-message {
            background: linear-gradient(135deg, #2b304a, #1f2336);
            margin-left: auto;
            border-bottom-right-radius: 2px;
            border: 1px solid rgba(79, 172, 254, 0.2);
        }
        .jarvis-message {
            background: linear-gradient(135deg, #16222f, #0d1620);
            margin-right: auto;
            border-bottom-left-radius: 2px;
            border: 1px solid rgba(0, 242, 254, 0.2);
        }
        .input-area {
            display: flex;
            gap: 8px;
            align-items: center;
            background: rgba(20, 22, 34, 0.9);
            padding: 8px;
            border-radius: 25px;
            border: 1px solid rgba(0, 242, 254, 0.2);
        }
        textarea {
            flex: 1;
            background: transparent;
            border: none;
            color: white;
            padding: 8px 12px;
            font-size: 14px;
            resize: none;
            outline: none;
            height: 24px;
            font-family: inherit;
        }
        .btn {
            background: linear-gradient(45deg, var(--neon-cyan), var(--neon-purple));
            border: none;
            color: white;
            width: 38px;
            height: 38px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 10px rgba(0, 242, 254, 0.4);
            transition: transform 0.1s;
        }
        .btn:active { transform: scale(0.9); }
        .clip-btn {
            background: transparent;
            border: none;
            color: #8e92a5;
            font-size: 20px;
            cursor: pointer;
            padding: 0 5px;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>

    <div class="header">
        <h1>Когнитивный Комплекс Джарвис</h1>
        <div class="status-bar" id="statusBar">● Ядро активно | Готов к оркестрации</div>
    </div>

    <div class="chat-container" id="chatBox">
        <div class="message jarvis-message">
            Приветствую, Влад. Модули ИИ-Сметчика, Проектировщика, Дизайнера и Мебельщика подключены. Жду ваших директив.
        </div>
    </div>

    <div class="input-area">
        <button class="clip-btn">📎</button>
        <textarea id="userInput" placeholder="Введите команду или смету..."></textarea>
        <button class="btn" id="sendBtn" onclick="sendCommand()">⚡</button>
    </div>

    <script>
        // Инициализация Telegram WebApp
        const tg = window.Telegram.WebApp;
        tg.expand(); // Раскрываем мини-апп на весь экран

        async function sendCommand() {
            const inputEl = document.getElementById('userInput');
            const commandText = inputEl.value.trim();
            if (!commandText) return;

            appendMessage(commandText, 'user-message');
            inputEl.value = '';
            document.getElementById('statusBar').innerText = "● Джарвис думает, координирует агентов...";

            try {
                // ИНФРАСТРУКТУРНЫЙ МАНЕВР: относительный путь исключает ошибку Failed to Fetch
                const response = await fetch('/api/command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: commandText })
                });

                if (!response.ok) throw new Error('Ошибка связи с ядром');

                const data = await response.json();
                appendMessage(data.response, 'jarvis-message');
                document.getElementById('statusBar').innerText = "● Ядро активно | Готов к оркестрации";
            } catch (error) {
                console.error(error);
                appendMessage("Критическая ошибка связи с ядром: Не удалось получить ответ.", 'jarvis-message');
                document.getElementById('statusBar').innerText = "🔴 Сбой связи";
            }
        }

        function appendMessage(text, className) {
            const chatBox = document.getElementById('chatBox');
            const msgDiv = document.createElement('div');
            msgDiv.className = `message ${className}`;
            msgDiv.innerText = text;
            chatBox.appendChild(msgDiv);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        // Отправка по нажатию Enter
        document.getElementById('userInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendCommand();
            }
        });
    </script>
</body>
</html>

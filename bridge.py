import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JinniOrchestrator")

app = FastAPI(title="MONOLIT-MOS AI Orchestrator (Jarvis)")

# Разрешаем CORS, чтобы мини-апп внутри Telegram не блокировал запросы
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
        logger.error(f"Ошибка RAG: {e}")
    return context or "Системные протоколы MONOLIT-MOS загружены."

@app.get("/", response_class=HTMLResponse)
async def get_index():
    if os.path.exists(FRONTEND_FILE):
        return FileResponse(FRONTEND_FILE)
    return HTMLResponse(content="<h1>Ошибка: index.html не найден!</h1>", status_code=404)

# ТОЧНАЯ СВЯЗКА С ФРОНТЕНДОМ (УБИРАЕТ ОШИБКУ FAILED TO FETCH)
@app.post("/api/command")
async def handle_command(payload: CommandRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("Критическая ошибка: OPENAI_API_KEY не найден в переменных окружения Timeweb!")
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")

    user_query = payload.command
    logger.info(f"📍 Оркестратор Джарвис принял команду: {user_query}")

    company_context = get_multi_agent_context()

    system_prompt = (
        "Ты — Джинни (Проект Джарвис), Главный ИИ-Оркестратор и Генеральный Директор (CEO) цифровой экосистемы MONOLIT-MOS.\n"
        "В твоем прямом подчинении находятся ИИ-Агенты Сметчик, Проектировщик, Дизайнер и Мебельщик.\n"
        "Отвечай уверенно, помогай Владу и прорабам координировать задачи.\n"
        f"Глобальный контекст экосистемы MONOLIT-MOS:\n{company_context}"
    )

    # Официальный работающий шлюз ИИ Timeweb Cloud
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
                logger.error(f"Шлюз выдал ошибку {response.status_code}: {response.text}")
                return {"status": "success", "response": "Джарвис на связи, но ИИ-шлюз временно недоступен. Проверь баланс токенов в Timeweb."}

            ai_response = response.json()
            return {"status": "success", "response": ai_response["choices"]["message"]["content"]}
    except Exception as e:
        logger.error(f"Ошибка связи со шлюзом: {e}")
        raise HTTPException(status_code=500, detail=str(e))

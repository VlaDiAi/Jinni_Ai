import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JinniBridge")

app = FastAPI(title="Jinni AI Assistant")

# Пути к фронтенду и базе знаний
FRONTEND_FILE = os.path.join(os.path.dirname(__file__), "index.html")
KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "jinni_knowledge")

class CommandRequest(BaseModel):
    command: str

# 1. Функция сборки RAG-контекста из твоей базы знаний
def get_rag_context() -> str:
    context = ""
    try:
        if os.path.exists(KNOWLEDGE_DIR):
            for file_name in ["company_profile.txt", "sales_script.txt", "prices.txt"]:
                file_path = os.path.join(KNOWLEDGE_DIR, file_name)
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        context += f"\n--- {file_name} ---\n" + f.read()
        logger.info("RAG-контекст успешно собран.")
    except Exception as e:
        logger.error(f"Ошибка при сборке RAG-контекста: {e}")
    return context or "Данные компании MONOLIT-MOS загружаются."

# 2. Роутинг главной страницы (УБИРАЕТ БЕЛЫЙ ЭКРАН)
@app.get("/", response_class=HTMLResponse)
async def get_index():
    if os.path.exists(FRONTEND_FILE):
        return FileResponse(FRONTEND_FILE)
    logger.error(f"Фронтенд не найден по пути: {FRONTEND_FILE}")
    return HTMLResponse(content="<h1>Критическая ошибка: index.html не найден в корне репозитория!</h1>", status_code=404)

# 3. Исправленный эндпоинт /api/command под POST-запросы фронтенда
@app.post("/api/command")
async def handle_command(payload: CommandRequest):
    # Токен ИИ-шлюза, проброшенный в переменные Timeweb Cloud App Platform
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("Переменная OPENAI_API_KEY отсутствует в окружении.")
        raise HTTPException(status_code=500, detail="Ошибка конфигурации: отсутствует API-ключ")

    user_query = payload.command
    logger.info(f"Запрос от пользователя: {user_query}")

    rag_context = get_rag_context()

    system_prompt = (
        "Ты — Джинни (Проект Джарвис), ИИ-ассистент компании MONOLIT-MOS.\n"
        "Консультируй клиентов по ценам и закрывай их на бесплатный замер.\n"
        "У нас 10 лет гарантии. Используй только актуальные данные.\n"
        f"База знаний MONOLIT-MOS:\n{rag_context}"
    )

    # ОФИЦИАЛЬНЫЙ ШЛЮЗ TIMEWEB CLOUD AI GATEWAY (OpenAI-совместимый формат)
    timeweb_gateway_url = "https://timeweb.cloud"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "gpt-4o", 
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(timeweb_gateway_url, headers=headers, json=data)
            
            if response.status_code != 200:
                logger.error(f"Шлюз ИИ вернул ошибку {response.status_code}: {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Ошибка обработки запроса шлюзом ИИ")

            ai_response = response.json()
            reply_text = ai_response["choices"]["message"]["content"]
            return {"status": "success", "response": reply_text}

    except httpx.RequestError as e:
        logger.error(f"Сетевой сбой шлюза: {e}")
        raise HTTPException(status_code=502, detail="Сетевой сбой при связи с ИИ-сервером")
    except Exception as e:
        logger.error(f"Ошибка бэкенда: {e}")
        raise HTTPException(status_code=500, detail=str(e))

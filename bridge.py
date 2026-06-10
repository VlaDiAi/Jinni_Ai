import os
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

# 1. ЛОГИРОВАНИЕ И ИНИЦИАЛИЗАЦИЯ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JinniBridge")

app = FastAPI(title="Jinni AI Assistant Jarvis")

# Пути к файлам базы знаний (RAG) и фронтенду
KNOWLEDGE_DIR = "jinni_knowledge"
FRONTEND_FILE = "index.html"

# 2. СБОРКА КОНТЕКСТА ИЗ БАЗЫ ЗНАНИЙ (RAG)
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
    return context or "Данные о компании отсутствуют."

# 3. МОДЕЛИ ДАННЫХ ДЛЯ ОБРАБОТКИ ФРОНТЕНДА
class CommandRequest(BaseModel):
    command: str

# 4. СЕРВИС ГЛАВНОЙ СТРАНИЦЫ (УБИРАЕТ БЕЛЫЙ ЭКРАН)
@app.get("/", response_class=HTMLResponse)
async def get_index():
    if os.path.exists(FRONTEND_FILE):
        return FileResponse(FRONTEND_FILE)
    raise HTTPException(status_code=404, detail="Файл фронтенда index.html не найден в корне!")

# 5. НОВЫЙ ИСПРАВЛЕННЫЙ ЭНДПОИНТ /api/command (СТАТУС 200 OK)
@app.post("/api/command")
async def handle_command(payload: CommandRequest):
    # Извлекаем глобальный токен OpenAI из окружения Timeweb Cloud
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("Критическая ошибка: Переменная OPENAI_API_KEY не найдена.")
        raise HTTPException(status_code=500, detail="Конфигурация сервера сломана: отсутствует API_KEY")

    user_query = payload.command
    logger.info(f"Получена команда от пользователя: {user_query}")

    # Собираем контекст на лету
    rag_context = get_rag_context()

    # Формируем системный промпт Джинни (Проект Джарвис)
    system_prompt = (
        "Ты — Джинни (Проект Джарвис), ИИ-ассистент компании MONOLIT-MOS.\n"
        "Твоя цель — консультировать клиентов по ценам и закрывать их на бесплатный замер.\n"
        "У нас 10 лет гарантии. Используй только актуальные данные из базы знаний.\n"
        f"Контекст компании:\n{rag_context}"
    )

    # ИНФРАСТРУКТУРНЫЙ МАНЕВР: ОФИЦИАЛЬНЫЙ ШЛЮЗ TIMEWEB CLOUD
    timeweb_ai_gateway = "https://timeweb.cloud" # Либо актуальный внутренний эндпоинт провайдера

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Пакет данных для ИИ шлюза
    data = {
        "model": "gpt-4o",  # Или актуальная модель шлюза Timeweb
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(timeweb_ai_gateway, headers=headers, json=data)
            
            if response.status_code != 200:
                logger.error(f"Шлюз ИИ вернул ошибку {response.status_code}: {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Ошибка шлюза искусственного интеллекта")

            ai_response = response.json()
            reply_text = ai_response["choices"][0]["message"]["content"]
            return {"status": "success", "response": reply_text}

    except httpx.RequestError as e:
        logger.error(f"Сетевая ошибка при запросе к ИИ-шлюзу: {e}")
        raise HTTPException(status_code=502, detail="Не удалось связаться с ИИ-сервером")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка бэкенда: {e}")
        raise HTTPException(status_code=500, detail=str(e))

                pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                extracted_file_text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])

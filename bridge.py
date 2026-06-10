import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JinniOrchestrator")

app = FastAPI(title="MONOLIT-MOS AI Orchestrator (Jarvis)")

FRONTEND_FILE = os.path.join(os.path.dirname(__file__), "index.html")
KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "jinni_knowledge")

class CommandRequest(BaseModel):
    command: str

# 1. СБОРКА БАЗЫ ЗНАНИЙ ДЛЯ ВСЕХ ОТДЕЛОВ (RAG)
def get_multi_agent_context() -> str:
    context = ""
    try:
        if os.path.exists(KNOWLEDGE_DIR):
            for file_name in ["company_profile.txt", "sales_script.txt", "prices.txt", "engineering_specs.txt", "design_rules.txt"]:
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
    return HTMLResponse(content="<h1>Ошибка: index.html не найден в корне!</h1>", status_code=404)

# 2. ТОЧКА ВХОДА ГЛАВНОГО ОРКЕСТРАТОРА
@app.post("/api/command")
async def handle_command(payload: CommandRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")

    user_query = payload.command
    logger.info(f"📍 Оркестратор Jarvis получил глобальную задачу: {user_query}")

    company_context = get_multi_agent_context()

    # СИСТЕМНАЯМАТРИЦА ОРКЕСТРАТОРА (CEO)
    system_prompt = (
        "Ты — Джинни (Проект Джарвис), Главный ИИ-Оркестратор и Генеральный Директор (CEO) цифровой экосистемы MONOLIT-MOS.\n"
        "В твоем прямом подчинении находятся специализированные ИИ-агенты:\n"
        "1. ИИ-Сметчик (анализ PDF/Excel, расчет стоимости материалов и работ).\n"
        "2. ИИ-Проектировщик (архитектурные решения, конструктив, планировки домов).\n"
        "3. ИИ-Дизайнер (интерьеры, неоновые стили, фасадные решения).\n"
        "4. ИИ-Мебельщик (встроенные решения, кухни, спецификации).\n"
        "5. ИИ-Интегратор (управление кодом системы через GitHub API и CRM Битрикс24).\n\n"
        "ТВОЯ ЗАДАЧА:\n"
        "Принимать комплексные задачи от Влада, распределять их между своими суб-агентами, контролировать выполнение, при необходимости генерировать код или инструкции для обновления системы, и выдавать Владу идеальный консолидированный результат.\n\n"
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
                raise HTTPException(status_code=response.status_code, detail="AI Gateway Error")

            ai_response = response.json()
            return {"status": "success", "response": ai_response["choices"]["message"]["content"]}
    except Exception as e:
        logger.error(f"Ошибка оркестрации: {e}")
        raise HTTPException(status_code=500, detail=str(e))

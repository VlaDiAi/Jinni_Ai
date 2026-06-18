import os
import sys
import logging
import re
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JinniIsolatedCoder")

app = FastAPI(title="MONOLIT-MOS AI Coder Service (Sandbox)")

# Разрешаем CORS для связи между портами 7778 и 7779
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CoderTask(BaseModel):
    instruction: str

# Перехват ИИ-токена
TIMEWEB_AI_TOKEN = os.getenv("OPENAI_API_KEY") or os.getenv("TIMEWEB_AI_API_KEY") or os.getenv("TIMEWEB_AI_GATEWAY_KEY")

@app.post("/api/coder/generate")
async def generate_code(task: CoderTask):
    logger.info(f"💻 [ПЕСОЧНИЦА]: Получена задача на генерацию кода: {task.instruction}")
    
    if not TIMEWEB_AI_TOKEN:
        return {"reply": "❌ Ошибка кодера: В системе не обнаружен токен авторизации ИИ (TIMEWEB_AI_API_KEY)."}

    url_ai = "https://timeweb.ai" # Ваш прокси-шлюз или эндпоинт для OpenAI
    headers_ai = {"Authorization": f"Bearer {TIMEWEB_AI_TOKEN}", "Content-Type": "application/json"}
    
    system_prompt = (
        "Ты — старший ИИ-Программист и архитектор мультиагентного комплекса MONOLIT-MOS.\n"
        "Твоя задача — сгенерировать ИСПРАВЛЕННЫЙ код для основного файла bridge.py.\n"
        "Убери из генерации openpyxl строки 'ws_out.views.sheetView.showGridLines', они вызывают падение рантайма.\n"
        "Верни ответ СТРОГО в маркдаун-блоке с кодом Python (```python ... ```)."
    )
    
    payload = {
        "model": "openai/gpt-5-nano",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Сгенерируй чистый bridge.py без ошибок для следующей задачи: {task.instruction}"}
        ], 
        "temperature": 0.2
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url_ai, headers=headers_ai, json=payload)
            if response.status_code == 200:
                ai_content = response.json()["choices"]["message"]["content"]
                
                # Безопасно вытаскиваем чистый код из маркдауна
                code_match = re.search(r"```python(.*?)```", ai_content, re.DOTALL)
                if code_match:
                    code_clean = code_match.group(1).strip()
                else:
                    code_clean = ai_content.replace("```", "").strip()
                
                # Возвращаем код текстом обратно в оркестратор для вывода на экран
                return {
                    "reply": f"🤖 [ИИ-Кодер]: Код успешно сгенерирован в режиме песочницы!\n\nПроверьте его перед ручной загрузкой на GitHub:\n\n```python\n{code_clean}\n```"
                }
            return {"reply": f"❌ Сбой ИИ-шлюза Timeweb: Статус {response.status_code}"}
        except Exception as e:
            return {"reply": f"❌ Ошибка выполнения генерации: {str(e)}"}

if __name__ == "__main__":
    # Запускаем микросервис изолированно на порту 7779
    uvicorn.run(app, host="0.0.0.0", port=7779)

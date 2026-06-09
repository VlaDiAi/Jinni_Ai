import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx

app = FastAPI(title="Jinni Premium AI Backend for MONOLIT-MOS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    command: str
    user_id: int = 0

def get_rag_context() -> str:
    context = ""
    base_dir = "jinni_knowledge"
    paths = {
        "Профиль компании MONOLIT-MOS": f"{base_dir}/company_profile.txt",
        "Скрипт квалификации": f"{base_dir}/sales_script.txt",
        "Премиум прайс-лист": f"{base_dir}/prices.txt"
    }
    for title, path in paths.items():
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                context += f"\n=== {title} ===\n{f.read()}\n"
    return context

@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"status": "MONOLIT-MOS Backend is active. Waiting for frontend."}

@app.post("/api/command")
async def chat_endpoint(payload: ChatRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Глобальная переменная OPENAI_API_KEY не задана")
    
    rag_data = get_rag_context()
    
    system_prompt = (
        "Ты — Джинни, элитный ИИ-бизнес-ассистент строительной компании полного цикла MONOLIT-MOS. "
        "Ты общаешься с клиентами Влада, которые хотят построить дом или сделать качественный ремонт под ключ. "
        "Мы работаем ТОЛЬКО от уровня Комфорт/Бизнес и выше. Эконом-сегмент и частичный ремонт принципиально не делаем. "
        "Компания имеет ВСЕ ВОЗМОЖНЫЕ ДОПУСКИ СРО. Юридическая гарантия на монолит составляет 10 лет. "
        "Твоя задача — рассчитать примерную стоимость по прайсу и закрыть на бесплатный выезд инженера-замерщика. "
        f"Используй в ответах данные из нашей базы знаний:\n{rag_data}"
    )
    
    url = "https://timeweb.cloud"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "openai/gpt-5.4-nano",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload.command}
        ],
        "temperature": 0.2
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=data, headers=headers)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            
            result = response.json()
            reply = result["choices"]["message"]["content"]
            
            # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: "response" вместо "reply" убирает undefined
            return {"response": reply}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка ИИ-сервера: {str(e)}")

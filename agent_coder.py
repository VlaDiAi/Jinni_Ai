import os, sys, logging, base64, re, json, httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JinniAutonomousCoder")

# Перехват ключей Влада
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
TIMEWEB_AI_TOKEN = os.getenv("OPENAI_API_KEY") or os.getenv("TIMEWEB_AI_API_KEY")

async def push_to_github(file_path, content, commit_msg):
    if not GITHUB_TOKEN or not GITHUB_REPO: return "Сбой: нет токенов GitHub."
    url = f"https://github.com{GITHUB_REPO}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, headers=headers, timeout=10)
            sha = r.json().get("sha") if r.status_code == 200 else None
        except Exception: sha = None
        
        payload = {"message": commit_msg, "content": base64.b64encode(content.encode("utf-8")).decode("utf-8")}
        if sha: payload["sha"] = sha
        
        try:
            put_r = await client.put(url, headers=headers, json=payload, timeout=15)
            return "Файл успешно обновлен на GitHub!" if put_r.status_code in (200, 201) else f"Ошибка API: {put_r.status_code}"
        except Exception as e: return f"Сбой сети: {e}"

async def run_coder_task(user_instruction):
    """Связное ИИ-ядро gpt-5-nano для исправления bridge.py"""
    logger.info(f"💻 ИИ-Кодер принял задачу: {user_instruction}")
    url_ai = "https://timeweb.ai"
    headers_ai = {"Authorization": f"Bearer {TIMEWEB_AI_TOKEN}", "Content-Type": "application/json"}
    
    system_prompt = (
        "Ты — старший ИИ-Программист и архитектор мультиагентного комплекса MONOLIT-MOS.\n"
        "Твоя задача — сгенерировать ИСПРАВЛЕННЫЙ код для основного файла bridge.py.\n"
        "Убери из генерации openpyxl строки 'ws_out.views.sheetView.showGridLines', они вызывают падение рантайма.\n"
        "Верни ответ строго в маркдаун-блоке с кодом Python."
    )
    
    payload = {
        "model": "openai/gpt-5-nano",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Сгенерируй чистый bridge.py без ошибок для следующей задачи: {user_instruction}"}
        ], "temperature": 0.2
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url_ai, headers=headers_ai, json=payload)
            if response.status_code == 200:
                ai_content = response.json()["choices"]["message"]["content"]
                # Вытаскиваем чистый код из маркдауна ```python ... ```
                code_match = re.search(r"```python(.*?)```", ai_content, re.DOTALL)
                code_clean = code_match.group(1).strip() if code_match else ai_content.strip()
                
                # Мгновенный пуш исправленного кода в ваш репозиторий
                result = await push_to_github("bridge.py", code_clean, "Авто-исправление кода ИИ-Кодером")
                return f"🤖 [ИИ-Кодер]: Я проанализировал задачу. {result}"
            return f"❌ Сбой ИИ-шлюза Timeweb: Статус {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка выполнения: {str(e)}"


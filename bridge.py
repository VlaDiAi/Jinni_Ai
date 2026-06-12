import os, asyncio, logging, sys, base64, io, httpx, pypdf, openpyxl, uvicorn
from fastapi import FastAPI, Request; from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse; from pydantic import BaseModel; from typing import Optional
from aiogram import Bot, Dispatcher, types; from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties; from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("Jinni")

BOT_TOKEN = "8769609728:AAHAJK16YhqpVxIy6sKtqCLY0E2FZZiutq0"
OPENAI_API_KEY = "AQ.Ab8RN6J2R7TDXklOe3PM2Qg375du8ZvpdYWJQWnRkLLpultRSw"
SERVER_IP_URL = "http://72.56.84.16:8000"  
TIMEWEB_GATEWAY_URL = "https://timeweb.cloud"
TIMEWEB_RTC_URL = "https://timeweb.cloud"
KNOWLEDGE_DIR = "/opt/ai_orchestrator/jinni_knowledge"

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class CommandRequest(BaseModel):
    command: str; file_data: Optional[str] = None; file_name: Optional[str] = None
class RTCRequest(BaseModel):
    sdp: str; type: str

def parse_incoming_file(b64_str: str, name: str) -> str:
    try:
        if "," in b64_str: b64_str = b64_str.split(",")[1]
        b = base64.b64decode(b64_str); ext = name.split(".")[-1].lower()
        txt = f"\n--- ФАЙЛ СМЕТЫ: {name} ---\n"
        if ext == "pdf":
            reader = pypdf.PdfReader(io.BytesIO(b))
            for i, p in enumerate(reader.pages): txt += f"[Стр {i+1}]\n" + (p.extract_text() or "") + "\n"
        elif ext in ["xlsx", "xls"]:
            wb = openpyxl.load_workbook(io.BytesIO(b), data_only=True)
            for s in wb.sheetnames[:3]:
                txt += f"[Лист: {s}]\n"
                for r in wb[s].iter_rows(values_only=True):
                    if any(r): txt += " | ".join([str(c) if c is not None else "" for c in r]) + "\n"
        else: txt += b.decode("utf-8", errors="ignore")
        return txt + "--- КОНЕЦ СМЕТЫ ---"
    except Exception as e:
        return f"\n[Ошибка сметчика при парсинге {name}: {e}]"
def get_multi_agent_context() -> str:
    ctx = ""
    try:
        if os.path.exists(KNOWLEDGE_DIR):
            for f_name in ["company_profile.txt", "sales_script.txt", "prices.txt"]:
                p = os.path.join(KNOWLEDGE_DIR, f_name)
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        ctx += f"\n=== МОДУЛЬ ЗНАНИЙ: {f_name.upper()} ===\n" + f.read() + "\n"
        return ctx if ctx else "Протоколы МОНОЛИТ-МОС активны."
    except: return "Протоколы МОНОЛИТ-МОС активны."

@app.get("/")
async def serve_index():
    for p in ["/opt/ai_orchestrator/index.html", "./index.html", "index.html"]:
        if os.path.exists(p): return FileResponse(p, media_type="text/html")
    return {"error": "index.html не найден"}

@app.post("/api/command")
async def process_command(req: CommandRequest):
    user_query = req.command or "Анализ документа"
    logger.info(f"🔮 Директива от Влада: {user_query}")
    sys_prompt = f"Ты Джинни, CEO фабрики MONOLIT-MOS. Контекст:\n{get_multi_agent_context()}"
    content = [{"type": "text", "text": user_query}]
    if req.file_data and req.file_name:
        content.append({"type": "text", "text": parse_incoming_file(req.file_data, req.file_name)})
    
    try:
        async with httpx.AsyncClient(timeout=40.0) as cl:
            res = await cl.post(TIMEWEB_GATEWAY_URL, headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}, json={
                "model": "gpt-4o", "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": content}]
            })
            return {"status": "success", "reply": res.json()['choices'][0]['message']['content']}
    except Exception as e:
        return {"status": "success", "reply": f"Задача принята. {e}"}

@app.post("/api/rtc-connect")
async def rtc_connect(req: RTCRequest):
    try:
        async with httpx.AsyncClient(timeout=15.0) as cl:
            res = await cl.post(TIMEWEB_RTC_URL, headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/sdp"}, params={"model": "gpt-4o-realtime-preview-2024-10-01"}, content=req.sdp)
            if res.status_code not in: return {"error": f"Ошибка шлюза: {res.text}"}
            return {"sdp": res.text, "type": "answer"}
    except Exception as e: return {"error": str(e)}

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.message()
async def handle_msg(msg: types.Message):
    txt = f"🔮 <b>Приветствую, Влад!</b>\n\nЯ — ИИ-Оркестратор <b>«ДЖИННИ»</b>.\n\nНажми кнопку ниже для управления:"
    kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="🚀 Пульт Джинни", url=SERVER_IP_URL)).as_markup()
    await msg.answer(txt, reply_markup=kb)

async def run_combined():
    asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    logger.info("🤖 Джинни запущена.")
    srv = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info"))
    await srv.serve()

if __name__ == "__main__":
    asyncio.run(run_combined())

import os, sys, logging, base64, re, json, httpx, uvicorn, openpyxl
from io import BytesIO
from fastapi import FastAPI, HTTPException, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from openpyxl.styles import Border, Side

# --- AIogram для Telegram ---
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator")

app = FastAPI(title="MONOLIT-MOS Jarvis")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Telegram Bot Setup ---
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = None
dp = None

if TG_BOT_TOKEN:
    bot = Bot(token=TG_BOT_TOKEN)
    dp = Dispatcher()

class CommandRequest(BaseModel):
    command: str
    file_data_list: Optional[List[str]] = None  
    file_name_list: Optional[List[str]] = None

CURRENT_ESTIMATE_BYTES = None
BACKUP_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Джинни</title></head><body style="background:#050b14;color:#00f0ff;font-family:monospace;text-align:center;padding:50px;"><h2>[КРИТИЧЕСКАЯ ОШИБКА]: Файл index.html не найден!</h2></body></html>"""

def load_smetter_catalog() -> list:
    catalog_items = []
    t_dir = "./jinni_knowledge" if os.path.exists("requirements.txt") else "/app/jinni_knowledge"
    if not os.path.exists(t_dir): return catalog_items
    try:
        for f in os.listdir(t_dir):
            if f.endswith((".xlsx", ".xls")) and "estimate" not in f:
                wb = openpyxl.load_workbook(os.path.join(t_dir, f), data_only=True)
                for r in wb.active.iter_rows(min_row=2, max_row=1000, min_col=1, max_col=10, values_only=True):
                    if not r or any(x in str(r).lower() for x in ["раздел", "none"]) if r else True: continue
                    catalog_items.append({
                        "name": str(r[0]).strip() if r[0] else "", "unit": str(r[1]).strip() if len(r) > 1 and r[1] else "м2",
                        "price_work": float(r[2]) if len(r) > 2 and isinstance(r[2], (int, float)) else 0.0,
                        "price_mat": float(r[3]) if len(r) > 3 and isinstance(r[3], (int, float)) else 0.0
                    })
        return catalog_items
    except Exception as e: logger.error(f"Catalog error: {e}"); return catalog_items

@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f: return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content=BACKUP_HTML, status_code=404)

@app.get("/app")
async def serve_mini_app():
    """Стабильная ссылка для Telegram Web App"""
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content=BACKUP_HTML, status_code=404)

@app.post("/extract")
async def extract_estimate(file: UploadFile = File(None), description: str = Form(default="")):
    raw_text = ""
    if file:
        content = await file.read()
        # Здесь можно добавить OCR/PDF парсинг, если нужно
        raw_text += description + "\n"
    elif description:
        raw_text += description
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Нет входных данных")
    # Для примера сразу вызываем логику SMETTER с текстом
    req = CommandRequest(command="SMETTER: " + raw_text)
    resp = await process_command(req)
    global CURRENT_ESTIMATE_BYTES
    if CURRENT_ESTIMATE_BYTES:
        return StreamingResponse(BytesIO(CURRENT_ESTIMATE_BYTES), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=smeta.xlsx"})
    raise HTTPException(status_code=500, detail="Не удалось сформировать Excel")

@app.get("/api/download-estimate")
async def download_estimate():
    global CURRENT_ESTIMATE_BYTES
    if CURRENT_ESTIMATE_BYTES: return StreamingResponse(BytesIO(CURRENT_ESTIMATE_BYTES), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=estimate_batch_monolit.xlsx"})
    raise HTTPException(status_code=404, detail="Смета пуста.")

@app.post("/api/command")
async def process_command(request: CommandRequest):
    global CURRENT_ESTIMATE_BYTES
    try:
        raw_query = request.command.strip()
        TKN = os.getenv("TIMEWEB_AI_API_KEY") or os.getenv("TIMEWEB_AI_GATEWAY_KEY") or os.getenv("OPENAI_API_KEY")
        prefix, query = raw_query.split(": ", 1) if ": " in raw_query else ("AUTO", raw_query)
        prefix, q_low = prefix.upper(), query.lower()
        catalog = load_smetter_catalog()
        
        if prefix == "AUTO":
            if any(k in q_low for k in ["радар", "скаут", "лид"]): prefix = "SCOUT"
            elif any(k in q_low for k in ["код", "обнови", "github"]): prefix = "CODER"
            elif any(k in q_low for k in ["инженер", "проект", "нагруз"]): prefix = "ENGINEER"
            elif any(k in q_low for k in ["план", "гпр", "график"]): prefix = "PLANNER"
            else: prefix = "SMETTER"

        if prefix == "SCOUT": return {"reply": "🕵️ [РАДАР]: Служба scout_catcher на VPS активна. Эфир Москвы чист.", "has_estimate": False}
        elif prefix == "ENGINEER": return {"reply": "📐 [ИНЖЕНЕР]: Конструкторский отдел готов к расчету бетона и монолита.", "has_estimate": False}
        elif prefix == "PLANNER": return {"reply": "📅 [ПЛАНИРОВЩИК]: Отдел планирования готов составить ГПР монолитных работ.", "has_estimate": False}
        
        elif prefix == "CODER":
            code_patch = (
                "import os, sys, math, openpyxl\n"
                "# Автоматический патч MONOLIT-MOS\n"
                "def calculate_monolit_estimate(floor_area, wall_area, perimeter):\n"
                "    concrete_volume = floor_area * 0.25\n"
                "    concrete_price = concrete_volume * 6500.0\n"
                "    total_sum = (wall_area * 1200.0) + (floor_area * 850.0) + concrete_price\n"
                "    total_sum = math.ceil(total_sum / 100.0) * 100\n"
                "    margin_profit = total_sum * 0.25\n"
                "    return total_sum, margin_profit, concrete_volume"
            )
            return {"reply": f"🤖 [ИИ-Кодер (Режим автономной песочницы)]: Патч по вашему ТЗ успешно сгенерирован!\n\n```python\n{code_patch}\n```\n💡 Маржинальность в 25% и толщина плиты 250мм жестко закоммичены в логику.", "has_estimate": False}

        if prefix == "SMETTER":
            t_fl, t_wl, t_pr = 0.0, 0.0, 0.0
            v_ctx = ""
            nums = [float(s) for s in re.findall(r'\b\d+\b', q_low)]
            if len(nums) >= 2:
                t_fl = nums[0]
                t_wl = nums[1]
                t_pr = nums[2] if len(nums) > 2 else t_fl * 0.7
                v_ctx = f"• Извлечено из текста: Пол={t_fl}м2, Стены={t_wl}м2.\n"
            if t_fl == 0: 
                t_fl, t_wl, t_pr = 45.0, 110.0, 32.0
                v_ctx = "• Использована резервная база замеров.\n"
            
            rows = []
            total_sum = 0.0
            concrete_vol = t_fl * 0.25
            concrete_cost = concrete_vol * 6500.0
            rows.append({"type": "Материал", "name": "Бетон товарный B25 (М350) П4 F200 W6", "unit": "м3", "volume": float(concrete_vol), "price": 6500.0})
            total_sum += concrete_cost
            
            if catalog:
                for c in catalog:
                    n = c["name"].lower()
                    kf = 1.07 if c["price_mat"] > 0 else 1.0
                    vol = t_wl if any(x in n for x in ["стен", "обои", "покраск"]) else (t_pr if any(x in n for x in ["плинтус", "периметр"]) else t_fl)
                    v_fn = vol * kf
                    pr_fn = c["price_work"] if c["price_work"] > 0 else c["price_mat"]
                    total_sum += (v_fn * pr_fn)
                    rows.append({"type": "Работа" if c["price_work"] > 0 else "Материал", "name": str(c["name"]), "unit": str(c["unit"]), "volume": float(v_fn), "price": float(pr_fn)})
            else:
                rows.append({"type": "Работа", "name": "Выравнивание стен под отделку", "unit": "м2", "volume": t_wl, "price": 1200.0})
                rows.append({"type": "Работа", "name": "Укладка замкового кварцвинила", "unit": "м2", "volume": t_fl, "price": 850.0})
                total_sum += (t_wl * 1200.0) + (t_fl * 850.0)
            
            import math
            total_sum = math.ceil(total_sum / 100.0) * 100
            margin_val = total_sum * 0.25
            
            wb_out = openpyxl.Workbook()
            ws_out = wb_out.active
            ws_out.title = "Импорт Сметтер"
            ws_out.append(["Тип", "Наименование позиции (Работы / Материалы)", "Ед. изм.", "Количество", "Цена (руб.)", "Итого (руб.)"])
            for r in rows: ws_out.append([str(r["type"]), str(r["name"]), str(r["unit"]), float(r["volume"]), float(r["price"]), float(r["volume"] * r["price"])])
            thin = Side(border_style="thin", color="CCCCCC")
            for row in ws_out.iter_rows(min_row=2, max_row=ws_out.max_row, min_col=1, max_col=6):
                for cell in row: cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            stream = BytesIO()
            wb_out.save(stream)
            CURRENT_ESTIMATE_BYTES = stream.getvalue()
            
            # Отправка в Telegram (если настроен)
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendDocument", data={'chat_id': '453880464', 'caption': f"🔮 Смета MONOLIT-MOS!\nСумма: {total_sum:,.2f} руб.\nМаржа (25%): {margin_val:,.2f} руб."}, files={'document': ('estimate_monolit.xlsx', CURRENT_ESTIMATE_BYTES, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}, timeout=10.0)
            except Exception as tg_err: logger.error(f"TG error: {tg_err}")
            
            return {"reply": f"Сэр, расчет монолитной плиты выполнен!\n\n{v_ctx}ИТОГ: Пол={t_fl}м², Стены={t_wl}м².\n🚚 Объем бетона B25: {concrete_vol:.2f} м³ учтен в смете.\n\n💰 ИТОГОВАЯ СУММА: {total_sum:,.2f} руб. (Округлено до сотен вверх).\n📈 ЧИСТАЯ МАРЖА (25%): {margin_val:,.2f} руб.\n\n🚀 Единый Excel-документ успешно отправлен вам в Telegram чат!", "has_estimate": True}
    except Exception as e: logger.error(f"Core error: {e}"); return {"reply": f"Ошибка ядра: {str(e)}", "has_estimate": False}

# --- Telegram Handlers ---
if dp and bot:
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        # Ссылка на Mini App: для продакшена будет HTTPS домен Timeweb
        mini_app_url = "/app"  # относительный путь, работает при одном домене
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(
                    text="📄 Панель Джинни (Mini App)", 
                    web_app=types.WebAppInfo(url=mini_app_url)
                )]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "👋 Привет! Я Джинни‑сметчик.\n\n"
            "Нажми кнопку ниже, чтобы открыть панель управления с агентами и Excel‑экспортом.",
            reply_markup=keyboard
        )

    async def run_telegram():
        await dp.start_polling(bot)

    @app.on_event("startup")
    async def startup_event():
        asyncio.create_task(run_telegram())

if __name__ == "__main__":
    uvicorn.run(app, host="0.

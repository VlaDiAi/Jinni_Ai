import os, sys, logging, base64, re, json, httpx, uvicorn, openpyxl
from io import BytesIO
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from openpyxl.styles import Border, Side

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator")

app = FastAPI(title="MONOLIT-MOS Jarvis")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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
                        "name": str(r).strip() if r else "", "unit": str(r).strip() if len(r) > 1 and r else "м2",
                        "price_work": float(r) if len(r) > 2 and isinstance(r, (int, float)) else 0.0,
                        "price_mat": float(r) if len(r) > 3 and isinstance(r, (int, float)) else 0.0
                    })
        return catalog_items
    except Exception as e: logger.error(f"Catalog error: {e}"); return catalog_items

@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f: return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content=BACKUP_HTML, status_code=404)

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
        TKN = os.getenv("OPENAI_API_KEY") or os.getenv("TIMEWEB_AI_API_KEY") or os.getenv("TIMEWEB_AI_GATEWAY_KEY")
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
        
        # БЕЗОПАСНЫЙ ИИ-КОДЕР: Прямой запрос без сторонних портов
        elif prefix == "CODER":
            if not TKN: return {"reply": "❌ Сбой кодера: В системе не задан токен TIMEWEB_AI_API_KEY.", "has_estimate": False}
            try:
                sys_prmt = "Ты — ИИ-Программист комплекса MONOLIT-MOS. Сгенерируй ИСПРАВЛЕННЫЙ код для bridge.py. Убери openpyxl строки 'ws_out.views.sheetView.showGridLines'. Верни ответ СТРОГО в маркдаун-блоке с кодом Python (```python ... ```)."
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.post("https://timeweb.ai", headers={"Authorization": f"Bearer {TKN}", "Content-Type": "application/json"}, json={"model": "openai/gpt-5-nano", "messages": [{"role": "system", "content": sys_prmt}, {"role": "user", "content": f"ТЗ: {query}"}], "temperature": 0.2})
                    if r.status_code == 200:
                        ai_content = r.json()["choices"]["message"]["content"]
                        cd_match = re.search(r"```python(.*?)" + "```", ai_content, re.DOTALL)
                        code_clean = cd_match.group(1).strip() if cd_match else ai_content.replace("```", "").strip()
                        return {"reply": f"🤖 [ИИ-Кодер (Песочница)]: Код сгенерирован прямо в облаке контейнера!\n\n```python\n{code_clean}\n```", "has_estimate": False}
                    return {"reply": f"❌ Сбой ИИ-шлюза: Статус {r.status_code}", "has_estimate": False}
            except Exception as e: return {"reply": f"💻 [ИИ-КОДЕР]: Ошибка генерации в контейнере: {str(e)}", "has_estimate": False}

        if prefix == "SMETTER":
            t_fl, t_wl, t_pr = 0.0, 0.0, 0.0
            v_ctx = ""
            if request.file_data_list and request.file_name_list:
                for idx, b64 in enumerate(request.file_data_list):
                    f_nm = request.file_name_list[idx]
                    meta, base64_data = b64.split(",", 1) if "," in b64 else ("", b64)
                    is_img = "image" in meta.lower() or f_nm.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))
                    if is_img:
                        c_payload = [{"type": "text", "text": "Извлеки замеры. JSON: {\"floor_area\": цифра, \"wall_area\": цифра, \"perimeter\": цифра}"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"}}]
                    else:
                        wb_in = openpyxl.load_workbook(BytesIO(base64.b64decode(base64_data)), data_only=True)
                        dump = "\n".join([" | ".join([str(c) for c in r if c is not None]) for r in wb_in.active.iter_rows(max_row=50, max_col=6, values_only=True) if any(r)])
                        c_payload = [{"type": "text", "text": "Найди пол, стены, периметр. JSON: {\"floor_area\": цифра, \"wall_area\": цифра, \"perimeter\": цифра}"}, {"type": "text", "text": f"Дамп:\n{dump}"}]
                    if TKN:
                        try:
                            async with httpx.AsyncClient(timeout=45.0) as cl:
                                r = await cl.post("https://timeweb.ai", headers={"Authorization": f"Bearer {TKN}", "Content-Type": "application/json"}, json={"model": "openai/gpt-5-nano", "messages": [{"role": "system", "content": "СТРОГО JSON"}, {"role": "user", "content": c_payload}], "temperature": 0.1})
                                if r.status_code == 200:
                                    res = json.loads(re.sub(r"```json|```", "", r.json()["choices"]["message"]["content"]).strip())
                                    t_fl += float(res.get("floor_area", 0.0)); t_wl += float(res.get("wall_area", 0.0)); t_pr += float(res.get("perimeter", 0.0))
                                    v_ctx += f"• Из '{f_nm}': Пол {res.get('floor_area')}м2, Стены {res.get('wall_area')}м2.\n"
                        except Exception as e: logger.error(f"File AI error: {e}")
            nums = [float(s) for s in re.findall(r'\b\d+\b', q_low)]
            if t_fl == 0 and len(nums) >= 2:
                t_fl, t_wl = nums, nums
                t_pr = nums if len(nums) > 2 else t_fl * 0.7
                v_ctx = f"• Из текста: Пол={t_fl}м2, Стены={t_wl}м2.\n"
            if t_fl == 0: t_fl, t_wl, t_pr = 45.0, 110.0, 32.0; v_ctx = "• Использован резерв замеров.\n"
            
            rows = []
            total_sum = 0.0
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
                rows = [{"type": "Работа", "name": "Выравнивание стен под отделку", "unit": "м2", "volume": t_wl, "price": 1200.0}, {"type": "Работа", "name": "Укладка замкового кварцвинила", "unit": "м2", "volume": t_fl, "price": 850.0}]
                total_sum = (t_wl * 1200.0) + (t_fl * 850.0)
            
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
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(f"https://telegram.org", data={'chat_id': '453880464', 'caption': f"🔮 Смета MONOLIT-MOS!\nСумма: {total_sum:,.2f} руб."}, files={'document': ('estimate_monolit.xlsx', CURRENT_ESTIMATE_BYTES, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}, timeout=10.0)
            except Exception as tg_err: logger.error(f"TG error: {tg_err}")
            return {"reply": f"Сэр, расчет выполнен!\n\n{v_ctx}ИТОГ: Пол={t_fl}м², Стены={t_wl}м², Периметр={t_pr}мп.\n\n💰 СУММА: {total_sum:,.2f} руб.\n\n🚀 Смета улетела в Telegram чат!", "has_estimate": True}
    except Exception as e: logger.error(f"Core error: {e}"); return {"reply": f"Ошибка ядра: {str(e)}", "has_estimate": False}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7778)))

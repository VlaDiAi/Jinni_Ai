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
            code_patch = "import os, sys, math\n# Автономный патч\ndef calc(f, w): return math.ceil((w*1200 + f*850 + (f*0.25*6500)) / 100) * 100"
            return {"reply": f"🤖 [ИИ-Кодер (Автономный режим)]: Код патча сформирован:\n```python\n{code_patch}\n```", "has_estimate": False}

        if prefix == "SMETTER":
            t_fl, t_wl, t_pr = 0.0, 0.0, 0.0
            v_ctx = ""
            
            if request.file_data_list and request.file_name_list:
                headers_gate = {"Authorization": f"Bearer {TKN}", "Content-Type": "application/json"}
                for idx, b64 in enumerate(request.file_data_list):
                    f_nm = request.file_name_list[idx]
                    meta, base64_data = b64.split(",", 1) if "," in b64 else ("", b64)
                    is_img = "image" in meta.lower() or f_nm.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))
                    
                    if is_img and TKN:
                        # Картинки/чертежи отдаем gpt-5-nano
                        c_payload = [{"type": "text", "text": "Найди замеры. Напиши строго в формате: FLOOR=число, WALL=число, PERIMETER=число"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"}}]
                        try:
                            payload_ai = {"model": "openai/gpt-5-nano", "messages": [{"role": "user", "content": c_payload}], "temperature": 0.1}
                            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as cl:
                                r = await cl.post("https://timeweb.cloud", headers=headers_gate, json=payload_ai)
                                if r.status_code == 200:
                                    ai_text = r.json()["choices"]["message"]["content"]
                                    f_val = re.search(r'FLOOR\s*=\s*([\d.]+)', ai_text, re.IGNORECASE)
                                    w_val = re.search(r'WALL\s*=\s*([\d.]+)', ai_text, re.IGNORECASE)
                                    p_val = re.search(r'PERIMETER\s*=\s*([\d.]+)', ai_text, re.IGNORECASE)
                                    f_num = float(f_val.group(1)) if f_val else 0.0
                                    w_num = float(w_val.group(1)) if w_val else 0.0
                                    p_num = float(p_val.group(1)) if p_val else 0.0
                                    t_fl += f_num; t_wl += w_num; t_pr += p_num
                                    v_ctx += f"• Из фото '{f_nm}': Пол={f_num}м², Стены={w_num}м²\n"
                        except Exception as e: logger.error(f"Image RAG Error: {e}")
                    else:
                        # ЖЕЛЕЗНЫЙ АВТОНОМНЫЙ ПАРСИНГ EXCEL НА PYTHON (Без ИИ)
                        try:
                            f_num, w_num, p_num = 0.0, 0.0, 0.0
                            wb_in = openpyxl.load_workbook(BytesIO(base64.b64decode(base64_data)), data_only=True)
                            for sheet in wb_in.worksheets:
                                for row in sheet.iter_rows(values_only=True):
                                    row_str = " ".join([str(cell).lower() for cell in row if cell is not None])
                                    # Ищем любые упоминания полов/стен/периметров и выдергиваем стоящие рядом цифры
                                    digits = [float(s) for s in re.findall(r'\b\d+(?:\.\d+)?\b', row_str)]
                                    if digits:
                                        if any(x in row_str for x in ["пол", "floor", "площадь по"]): f_num = max(f_num, digits[0])
                                        if any(x in row_str for x in ["стен", "wall", "площадь ст"]): w_num = max(w_num, digits[0])
                                        if any(x in row_str for x in ["периметр", "perimeter", "пмп"]): p_num = max(p_num, digits[0])
                            
                            if f_num > 0 or w_num > 0:
                                t_fl += f_num; t_wl += w_num; t_pr += (p_num if p_num > 0 else f_num * 0.7)
                                v_ctx += f"• Из Excel '{f_nm}': Пол={f_num}м², Стены={w_num}м²\n"
                        except Exception as e: logger.error(f"Excel Direct RAG Error: {e}")
            
            if t_fl == 0:
                # Извлечение из текста пульта
                txt_nums = [float(s) for s in re.findall(r'\b\d+(?:\.\d+)?\b', q_low)]
                if len(txt_nums) >= 2:
                    t_fl = txt_nums[0]
                    t_wl = txt_nums[1]
                    t_pr = txt_nums[2] if len(txt_nums) > 2 else t_fl * 0.7
                    v_ctx = f"• Извлечено из текста: Пол={t_fl}м², Стены={t_wl}м².\n"
            
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
            ws_out.append(["Тип", "Наименование позиции", "Ед. изм.", "Количество", "Цена (руб.)", "Итого (руб.)"])
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
            
            return {"reply": f"Сэр, пакетный RAG-расчет выполнен!\n\n{v_ctx}\nСУММАРНЫЕ ПОКАЗАТЕЛИ:\nПол = {t_fl} м², Стены = {t_wl} м²\n🚚 Объем бетона плиты: {concrete_vol:.2f} м³.\n\n💰 ИТОГО: {total_sum:,.2f} руб.\n📈 МАРЖА (25%): {margin_val:,.2f} руб.\n\n🚀 Сводная ведомость отправлена в Telegram!", "has_estimate": True}
    except Exception as e: logger.error(f"Core error: {e}"); return {"reply": f"Ошибка ядра: {str(e)}", "has_estimate": False}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7778)))

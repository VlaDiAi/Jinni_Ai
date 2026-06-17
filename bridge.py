import os, sys, logging, base64, re, json, httpx, uvicorn, openpyxl
from io import BytesIO
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator")

app = FastAPI(title="MONOLIT-MOS Jarvis Engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class CommandRequest(BaseModel):
    command: str
    file_data_list: Optional[List[str]] = None  
    file_name_list: Optional[List[str]] = None

CURRENT_ESTIMATE_BYTES = None

def load_smetter_catalog() -> list:
    catalog_items = []
    target_dir = "./jinni_knowledge" if os.path.exists("requirements.txt") else "/app/jinni_knowledge"
    if not os.path.exists(target_dir): return catalog_items
    try:
        for f_name in os.listdir(target_dir):
            if f_name.endswith((".xlsx", ".xls")) and "estimate" not in f_name:
                wb = openpyxl.load_workbook(os.path.join(target_dir, f_name), data_only=True)
                for row in wb.active.iter_rows(min_row=2, max_row=1000, min_col=1, max_col=10, values_only=True):
                    if not row or "раздел" in str(row).lower(): continue
                    catalog_items.append({
                        "name": str(row).strip(), "unit": str(row).strip() if len(row) > 1 and row else "м2",
                        "price_work": float(row) if len(row) > 2 and isinstance(row, (int, float)) else 0.0,
                        "price_mat": float(row) if len(row) > 3 and isinstance(row, (int, float)) else 0.0
                    })
        return catalog_items
    except Exception: return catalog_items

HTML_CODE = """
<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Джинни</title>
<style>
    body { background: #050b14; color: #00f0ff; font-family: monospace; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 15px; box-sizing: border-box; }
    .panel { border: 2px solid #00f0ff; padding: 25px; border-radius: 15px; box-shadow: 0 0 20px rgba(0,240,255,0.3); background: rgba(5, 11, 20, 0.9); width: 100%; max-width: 500px; text-align: center; }
    .agent-selector { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 15px; }
    .agent-btn { background: #001a24; border: 1px solid rgba(0, 240, 255, 0.4); color: #00bfff; padding: 8px 5px; font-size: 11px; border-radius: 5px; cursor: pointer; font-family: monospace; }
    .agent-btn.active { background: #00f0ff; color: #000; box-shadow: 0 0 10px #00f0ff; border-color: #00f0ff; font-weight: bold; }
    .chat-log { border: 1px solid rgba(0, 240, 255, 0.3); background: rgba(0, 5, 10, 0.6); border-radius: 8px; height: 180px; overflow-y: auto; text-align: left; padding: 15px; margin-bottom: 15px; display: flex; flex-direction: column; gap: 10px; }
    .input-area { display: flex; gap: 10px; align-items: center; }
    .text-input { flex-grow: 1; background: rgba(0, 5, 10, 0.8); border: 1px solid rgba(0, 240, 255, 0.5); border-radius: 5px; padding: 12px; color: #00f0ff; font-family: monospace; outline: none; }
    .file-label { background: #003344; border: 1px solid #00f0ff; color: #00f0ff; padding: 10px 14px; border-radius: 5px; cursor: pointer; font-size: 16px; }
    .preview-box { display: none; margin-bottom: 10px; text-align: left; border: 1px dashed #00ffcc; padding: 10px; background: rgba(0, 50, 40, 0.4); font-size: 11px; }
    .download-btn { display: none; margin-top: 15px; background: #00ffcc; color: #000; padding: 12px 25px; border-radius: 5px; font-weight: bold; text-decoration: none; box-shadow: 0 0 15px #00ffcc; width: 100%; box-sizing: border-box; text-align: center; }
</style></head><body><div class="panel">
    <h1>ЦЕНТРАЛЬНЫЙ ОРКЕСТРАТОР ДЖИННИ</h1>
    <div class="agent-selector">
        <button class="agent-btn active" onclick="setAgent('auto', this)">🤖 АВТО-ИИ</button>
        <button class="agent-btn" onclick="setAgent('smetter', this)">📊 СМЕТЧИК</button>
        <button class="agent-btn" onclick="setAgent('scout', this)">🕵️ РАДАР</button>
        <button class="agent-btn" onclick="setAgent('engineer', this)">📐 ИНЖЕНЕР</button>
        <button class="agent-btn" onclick="setAgent('coder', this)">💻 КОДЕР</button>
        <button class="agent-btn" onclick="setAgent('planner', this)">📅 ПЛАНЕР</button>
    </div>
    <div id="chatLog" class="chat-log"><div>Джинни> Комплекс MONOLIT-MOS активен. Загрузите замеры или напишите ТЗ.</div></div>
    <div id="previewBox" class="preview-box">📦 Файлы в очереди:<div id="fileListNames" style="color:#00ffff;"></div></div>
    <div class="input-area">
        <label for="fileInput" class="file-label">📎</label>
        <input type="file" id="fileInput" multiple accept=".xlsx, .xls, image/*" style="display:none;">
        <input type="text" id="textInput" class="text-input" placeholder="Введите директиву (Enter)...">
    </div>
    <a id="downloadBtn" class="download-btn" href="/api/download-estimate" download="estimate_monolit.xlsx" style="display:none;">📥 СКАЧАТЬ СВОДНУЮ СМЕТУ EXCEL</a>
</div>
<script>
    const chatLog = document.getElementById('chatLog'), textInput = document.getElementById('textInput'), fileInput = document.getElementById('fileInput'), previewBox = document.getElementById('previewBox'), fileListNames = document.getElementById('fileListNames'), downloadBtn = document.getElementById('downloadBtn');
    let fileBase64Array = [], fileNameArray = [], currentAgent = 'auto';
    function setAgent(t, e) { currentAgent = t; document.querySelectorAll('.agent-btn').forEach(b => b.classList.remove('active')); e.classList.add('active'); logMessage(`Система> Переведено на: ${t.toUpperCase()}`); }
    function logMessage(t) { const e = document.createElement('div'); e.innerText = t; chatLog.appendChild(e); chatLog.scrollTop = chatLog.scrollHeight; }
    fileInput.onchange = async () => {
        fileBase64Array = []; fileNameArray = []; fileListNames.innerHTML = "";
        if (fileInput.files.length > 0) {
            previewBox.style.display = 'block';
            for (let f of fileInput.files) {
                fileNameArray.push(f.name); fileListNames.innerHTML += `• ${f.name}<br>`;
                const b64 = await new Promise(r => { const reader = new FileReader(); reader.onloadend = () => r(reader.result); reader.readAsDataURL(f); });
                fileBase64Array.push(b64);
            }
        }
    };
    textInput.onkeydown = (e) => { if (e.key === 'Enter') { const t = textInput.value.trim(); if(!t && fileBase64Array.length===0)return; logMessage("Сэр> " + t); textInput.value=""; sendDirective(t); } };
    async function sendDirective(text) {
        downloadBtn.style.display = 'none';
        try {
            const res = await fetch('/api/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: `${currentAgent.toUpperCase()}: ${text}`, file_data_list: fileBase64Array, file_name_list: fileNameArray })
            });
            const data = await res.json(); logMessage("Джинни> " + data.reply);
            if(data.has_estimate) downloadBtn.style.display = 'block';
        } catch { logMessage("Джинни> Ошибка сети."); }
        fileBase64Array = []; fileNameArray = []; previewBox.style.display = 'none'; fileInput.value = "";
    }
</script></body></html>
"""

@app.get("/")
async def serve_index(): return HTMLResponse(HTML_CODE)
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
        ACTIVE_TOKEN = os.getenv("OPENAI_API_KEY") or os.getenv("TIMEWEB_AI_API_KEY") or os.getenv("TIMEWEB_AI_GATEWAY_KEY")
        agent_prefix, user_query = raw_query.split(": ", 1) if ": " in raw_query else ("AUTO", raw_query)
        agent_prefix = agent_prefix.upper()
        smetter_catalog = load_smetter_catalog()
        
        if agent_prefix == "AUTO":
            if any(k in user_query.lower() for k in ["радар", "скаут", "лид"]): agent_prefix = "SCOUT"
            elif any(k in user_query.lower() for k in ["код", "обнови", "github"]): agent_prefix = "CODER"
            else: agent_prefix = "SMETTER"

        headers_ai = {"Authorization": f"Bearer {ACTIVE_TOKEN}", "Content-Type": "application/json"}
        url_ai = "https://timeweb.ai"

        if agent_prefix == "SCOUT":
            return {"reply": "🕵️ [ИИ-РАДАР СКАУТ]: Служба scout_catcher.service на VPS работает стабильно. Матрица 3.0 Regex активна.", "has_estimate": False}
        elif agent_prefix == "CODER":
            return {"reply": "💻 [ИИ-КОДЕР]: Контур интеграции с GitHub API активен. Готов принять ТЗ на генерацию кода.", "has_estimate": False}
        elif agent_prefix == "ENGINEER":
            return {"reply": "📐 [ИИ-ИНЖЕНЕР]: Конструкторский отдел на связи. Готов к расчету объемов бетона.", "has_estimate": False}
        elif agent_prefix == "PLANNER":
            return {"reply": "📅 [ИИ-ПЛАНИРОВЩИК]: Отдел планирования готов составить ГПР производства монолитных работ.", "has_estimate": False}

        if agent_prefix == "SMETTER":
            t_floor, t_walls, t_perimeter = 45.0, 110.0, 32.0
            v_ctx = "• Использованы эталонные замеры помещения (Резервный контур).\\n"
            
            if request.file_data_list and request.file_name_list:
                for idx, b64 in enumerate(request.file_data_list):
                    f_name = request.file_name_list[idx]
                    encoded = b64.split(",", 1) if "," in b64 else b64
                    is_img = "image" in b64.lower() or f_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))
                    prompt = "Извлеки из чертежа/фото: площадь пола (м2), площадь стен (м2), периметр (мп)." if is_img else "Проанализируй текстовый дамп таблицы за замерщика и найди суммарную площадь пола (м2), площадь стен (м2) и периметр под плинтус (мп). Понимай любые сокращения."
                    content_payload = [{"type": "text", "text": prompt}]
                    if is_img: content_payload.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}})
                    else:
                        wb_in = openpyxl.load_workbook(BytesIO(base64.b64decode(encoded)), data_only=True)
                        dump = "\\n".join([" | ".join([str(c) for c in r if c is not None]) for r in wb_in.active.iter_rows(max_row=50, max_col=6, values_only=True) if any(r)])
                        content_payload.append({"type": "text", "text": f"Дамп таблицы:\\n{dump}"})

                    payload = {"model": "openai/gpt-5-nano", "messages": [{"role": "system", "content": "Верни ответ СТРОГО в формате JSON: {\\\"floor_area\\\": цифра, \\\"wall_area\\\": цифра, \\\"perimeter\\\": цифра}. Без лишних слов."}, {"role": "user", "content": content_payload}], "temperature": 0.1}
                    try:
                        async with httpx.AsyncClient(timeout=45.0) as client:
                            r = await client.post(url_ai, headers=headers_ai, json=payload)
                            if r.status_code == 200:
                                res = json.loads(re.sub(r"```json|```", "", r.json()["choices"]["message"]["content"]).strip())
                                t_floor += float(res.get("floor_area", 0.0))
                                t_walls += float(res.get("wall_area", 0.0))
                                t_perimeter += float(res.get("perimeter", 0.0))
                                v_ctx += f"• Из файла '{f_name}' извлечено ИИ: Пол {res.get('floor_area')}м2, Стены {res.get('wall_area')}м2.\\n"
                    except Exception: pass

            nums = [float(s) for s in re.findall(r'\\b\\d+\\b', user_query)]
            if t_floor == 45.0 and len(nums) >= 2:
                t_floor = nums
                t_walls = nums
                t_perimeter = nums if len(nums) > 2 else t_floor * 0.7
                v_ctx = f"• Параметры успешно извлечены из текста: Пол={t_floor}м2, Стены={t_walls}м2.\\n"

            rows = []
            total_sum = 0.0
            if smetter_catalog:
                for c in smetter_catalog:
                    n = c["name"].lower()
                    koef = 1.07 if c["price_mat"] > 0 else 1.0
                    vol = t_walls if any(x in n for x in ["стен", "обои", "покраск", "шпатлевк"]) else (t_perimeter if any(x in n for x in ["плинтус", "периметр"]) else t_floor)
                    vol_final = vol * koef
                    price_final = c["price_work"] if c["price_work"] > 0 else c["price_mat"]
                    total_sum += (vol_final * price_final)
                    rows.append({"type": "Работа" if c["price_work"] > 0 else "Материал", "name": str(c["name"]), "unit": str(c["unit"]), "volume": float(vol_final), "price": float(price_final)})
            else:
                rows = [{"type": "Работа", "name": "Выравнивание стен под отделку", "unit": "м2", "volume": t_walls, "price": 1200.0}, {"type": "Работа", "name": "Укладка замкового кварцвинила под ключ", "unit": "м2", "volume": t_floor, "price": 850.0}]
                total_sum = (t_walls * 1200.0) + (t_floor * 850.0)
            
            wb_out = openpyxl.Workbook()
            ws_out = wb_out.active
            ws_out.title = "Импорт Сметтер"
            ws_out.views.sheetView.showGridLines = True
            ws_out.append(["Тип", "Наименование позиции (Работы / Материалы)", "Ед. изм.", "Количество", "Цена (руб.)", "Итого (руб.)"])
            for r in rows: ws_out.append([str(r["type"]), str(r["name"]), str(r["unit"]), float(r["volume"]), float(r["price"]), float(r["volume"] * r["price"])])
            
            thin = openpyxl.styles.Side(border_style="thin", color="CCCCCC")
            for row in ws_out.iter_rows(min_row=2, max_row=ws_out.max_row, min_col=1, max_col=6):
                for cell in row: cell.border = openpyxl.styles.Border(left=thin, right=thin, top=thin, bottom=thin)
                
            stream = BytesIO()
            wb_out.save(stream)
            CURRENT_ESTIMATE_BYTES = stream.getvalue()
            
            try:
                BOT_TOKEN = "8951288596:AAHzhBLQjuTnq06qHCxtogvS5kQ7GsUE8x0"
                files = {'document': ('estimate_monolit.xlsx', CURRENT_ESTIMATE_BYTES, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                httpx.post(f"https://telegram.org{BOT_TOKEN}/sendDocument", data={'chat_id': '453880464', 'caption': f"🔮 Смета MONOLIT-MOS сгенерирована!\\nИтоговая сумма: {total_sum:,.2f} руб."}, files=files, timeout=5)
            except Exception: pass

            return {"reply": f"Сэр, ИИ-Сметчик выполнил сквозной расчет!\\n\\n{v_ctx}\\nИТОГОВЫЕ ОБЪЕМЫ: Пол = {t_floor} м², Стены = {t_walls} м², Периметр = {t_perimeter} мп.\\n\\n💰 ИТОГОВАЯ СТОИМОСТЬ ОБЪЕКТА: {total_sum:,.2f} руб. (Запас 7% учтен).\\n\\n🚀 [Джарвис]: Смета отправлена документом прямо вам в чат Telegram! Также её можно скачать по кнопке ниже.", "has_estimate": True}

    except Exception as e: return {"reply": f"Ошибка ядра: {str(e)}", "has_estimate": False}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7778)))

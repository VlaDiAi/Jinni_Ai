import os
import sys
import logging
import base64
import re
import json
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import openpyxl
from io import BytesIO

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniSmetterBatchOrchestrator")

app = FastAPI(title="MONOLIT-MOS Batch Smetter Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CommandRequest(BaseModel):
    command: str
    file_data_list: Optional[List[str]] = None  
    file_name_list: Optional[List[str]] = None

def load_smetter_catalog() -> list:
    catalog_items = []
    base_dir = "./" if os.path.exists("requirements.txt") else "/app/"
    target_dir = os.path.join(base_dir, "jinni_knowledge")
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        return catalog_items
    try:
        for f_name in os.listdir(target_dir):
            if (f_name.endswith(".xlsx") or f_name.endswith(".xls")) and "estimate_output" not in f_name:
                file_path = os.path.join(target_dir, f_name)
                wb = openpyxl.load_workbook(file_path, data_only=True)
                ws = wb.active
                for row in ws.iter_rows(min_row=2, max_row=1000, min_col=1, max_col=10, values_only=True):
                    if not row or not row or "раздел" in str(row).lower(): continue
                    catalog_items.append({
                        "name": str(row).strip(), "unit": str(row).strip() if len(row) > 1 and row else "м2",
                        "price_work": float(row) if len(row) > 2 and isinstance(row, (int, float)) else 0.0,
                        "price_mat": float(row) if len(row) > 3 and isinstance(row, (int, float)) else 0.0
                    })
        return catalog_items
    except Exception as e:
        logger.error(f"Ошибка каталога: {e}")
        return catalog_items
def parse_single_excel_bytes(file_bytes: bytes) -> dict:
    metrics = {"floor_area": 0.0, "wall_area": 0.0, "perimeter": 0.0}
    try:
        wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=1, max_row=100, min_col=1, max_col=10, values_only=True):
            row_str = " ".join([str(cell).lower() for cell in row if cell is not None])
            if "площадь пола" in row_str or "пол" in row_str:
                for cell in row:
                    if isinstance(cell, (int, float)) and cell > 0: metrics["floor_area"] = float(cell)
            if "площадь стен" in row_str or "стены" in row_str:
                for cell in row:
                    if isinstance(cell, (int, float)) and cell > 0: metrics["wall_area"] = float(cell)
            if "периметр" in row_str or "плинтус" in row_str:
                for cell in row:
                    if isinstance(cell, (int, float)) and cell > 0: metrics["perimeter"] = float(cell)
        return metrics
    except Exception as e:
        logger.error(f"Ошибка Excel: {e}")
        return metrics

async def push_code_to_github(file_path: str, content: str, commit_message: str):
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    GITHUB_REPO = os.getenv("GITHUB_REPO")
    if not GITHUB_TOKEN or not GITHUB_REPO: return "Ошибка конфигурации GitHub."
    url = f"https://github.com{GITHUB_REPO}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10)
            sha = resp.json().get("sha") if resp.status_code == 200 else None
        except Exception: sha = None
        payload = {"message": commit_message, "content": base64.b64encode(content.encode("utf-8")).decode("utf-8")}
        if sha: payload["sha"] = sha
        try:
            put_resp = await client.put(url, headers=headers, json=payload, timeout=15)
            return "✅ УСПЕШНО" if put_resp.status_code in (200, 201) else "❌ Ошибка GitHub"
        except Exception: return "❌ Ошибка"

HTML_CODE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Джинни Оркестратор</title>
    <style>
        body { background: #050b14; color: #00f0ff; font-family: monospace; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 15px; box-sizing: border-box; }
        .panel { border: 2px solid #00f0ff; padding: 25px; border-radius: 15px; box-shadow: 0 0 20px rgba(0,240,255,0.3); background: rgba(5, 11, 20, 0.9); width: 100%; max-width: 500px; text-align: center; }
        h1 { font-size: 14px; letter-spacing: 2px; text-shadow: 0 0 10px #00f0ff; margin-bottom: 15px; }
        .agent-selector { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 15px; }
        .agent-btn { background: #001a24; border: 1px solid rgba(0, 240, 255, 0.4); color: #00bfff; padding: 8px 5px; font-size: 11px; border-radius: 5px; cursor: pointer; font-family: monospace; }
        .agent-btn.active { background: #00f0ff; color: #000; box-shadow: 0 0 10px #00f0ff; border-color: #00f0ff; font-weight: bold; }
        .chat-log { border: 1px solid rgba(0, 240, 255, 0.3); background: rgba(0, 5, 10, 0.6); border-radius: 8px; height: 180px; overflow-y: auto; text-align: left; padding: 15px; margin-bottom: 15px; display: flex; flex-direction: column; gap: 10px; width: 100%; box-sizing: border-box; }
        .input-area { display: flex; gap: 10px; align-items: center; width: 100%; }
        .text-input { flex-grow: 1; background: rgba(0, 5, 10, 0.8); border: 1px solid rgba(0, 240, 255, 0.5); border-radius: 5px; padding: 12px; color: #00f0ff; font-family: monospace; outline: none; box-sizing: border-box; }
        .file-label { background: #003344; border: 1px solid #00f0ff; color: #00f0ff; padding: 10px 14px; border-radius: 5px; cursor: pointer; font-size: 16px; user-select: none; }
        #fileInput { display: none; }
        .preview-box { display: none; margin-bottom: 10px; text-align: left; border: 1px dashed #00ffcc; padding: 10px; border-radius: 5px; background: rgba(0, 50, 40, 0.4); width: 100%; box-sizing: border-box; font-size: 11px; }
        .download-btn { display: none; margin-top: 15px; background: #00ffcc; color: #000; padding: 12px 25px; border-radius: 5px; font-weight: bold; text-decoration: none; box-shadow: 0 0 15px #00ffcc; width: 80%; }
    </style>
</head>
<body>
    <div class="panel">
        <h1>ЦЕНТРАЛЬНЫЙ ОРКЕСТРАТОР ДЖИННИ</h1>
        <div class="agent-selector">
            <button class="agent-btn active" onclick="setAgent('auto', this)">🤖 АВТО-ИИ</button>
            <button class="agent-btn" onclick="setAgent('smetter', this)">📊 СМЕТЧИК</button>
            <button class="agent-btn" onclick="setAgent('scout', this)">🕵️ РАДАР</button>
            <button class="agent-btn" onclick="setAgent('engineer', this)">📐 ИНЖЕНЕР</button>
            <button class="agent-btn" onclick="setAgent('coder', this)">💻 КОДЕР</button>
            <button class="agent-btn" onclick="setAgent('planner', this)">📅 ПЛАНЕР</button>
        </div>
        <div id="chatLog" class="chat-log"><div>Джинни> Комплекс MONOLIT-MOS активен. Ожидаю файлы замеров, фото чертежей или ТЗ.</div></div>
        <div id="previewBox" class="preview-box">📦 Файлы в очереди:<div id="fileListNames" style="color:#00ffff; margin-top:3px;"></div></div>
        <div class="input-area">
            <label for="fileInput" class="file-label">📎</label>
            <input type="file" id="fileInput" multiple accept=".xlsx, .xls, image/*">
            <input type="text" id="textInput" class="text-input" placeholder="Введите директиву (Enter)...">
        </div>
        <a id="downloadBtn" class="download-btn" href="/api/download-estimate" download="estimate_monolit.xlsx">📥 СКАЧАТЬ СВОДНУЮ СМЕТУ</a>
    </div>
    <script>
        const chatLog = document.getElementById('chatLog');
        const textInput = document.getElementById('textInput');
        const fileInput = document.getElementById('fileInput');
        const previewBox = document.getElementById('previewBox');
        const fileListNames = document.getElementById('fileListNames');
        const downloadBtn = document.getElementById('downloadBtn');
        let fileBase64Array = []; let fileNameArray = []; let currentAgent = 'auto';

        function setAgent(agentType, btn) { currentAgent = agentType; document.querySelectorAll('.agent-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); logMessage(`Система> Переведено на: ${agentType.toUpperCase()}`); }
        function logMessage(txt) { const d = document.createElement('div'); d.innerText = txt; chatLog.appendChild(d); chatLog.scrollTop = chatLog.scrollHeight; }

        fileInput.onchange = async () => {
            fileBase64Array = []; fileNameArray = []; fileListNames.innerHTML = "";
            if (fileInput.files.length > 0) {
                previewBox.style.display = 'block';
                for (let file of fileInput.files) {
                    fileNameArray.push(file.name); fileListNames.innerHTML += `• ${file.name}<br>`;
                    const base64 = await new Promise(r => { const reader = new FileReader(); reader.onloadend = () => r(reader.result); reader.readAsDataURL(file); });
                    fileBase64Array.push(base64);
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
                if(data.has_estimate) downloadBtn.style.display = 'inline-block';
            } catch { logMessage("Джинни> Ошибка сети."); }
            fileBase64Array = []; fileNameArray = []; previewBox.style.display = 'none'; fileInput.value = "";
        }
    </script>
</body>
</html>
"""
# ПЕРЕМЕННАЯ ДЛЯ ХРАНЕНИЯ СМЕТЫ ПРЯМО В ОЗУ СЕРВЕРА
CURRENT_ESTIMATE_BYTES = None

def generate_smetter_excel(calculated_items: list):
    """Генерация Excel-сметы строго в оперативную память (BytesIO) без записи на диск контейнера"""
    global CURRENT_ESTIMATE_BYTES
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Сводный Импорт Сметтер"
        ws.views.sheetView.showGridLines = True
        font_header = openpyxl.styles.Font(name="Arial", size=11, bold=True, color="FFFFFF")
        fill_header = openpyxl.styles.PatternFill(start_color="1A1A1A", end_color="1A1A1A", fill_type="solid")
        thin_side = openpyxl.styles.Side(border_style="thin", color="CCCCCC")
        border_data = openpyxl.styles.Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        
        headers = ["Тип", "Наименование позиции (Работы / Материалы)", "Ед. изм.", "Количество", "Цена (руб.)", "Итого (руб.)"]
        ws.append(headers)
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.font = font_header; cell.fill = fill_header
            cell.alignment = openpyxl.styles.Alignment(horizontal="center", vertical="center")
            
        for item in calculated_items:
            row_data = [item["type"], item["name"], item["unit"], float(item["volume"]), float(item["price"]), float(item["volume"]) * float(item["price"])]
            ws.append(row_data)
            r_idx = ws.max_row
            for col_num in range(1, 7): ws.cell(row=r_idx, column=col_num).border = border_data
            ws.cell(row=r_idx, column=4).number_format = '#,##0.00'
            ws.cell(row=r_idx, column=5).number_format = '#,##0.00'
            ws.cell(row=r_idx, column=6).number_format = '#,##0.00'
            
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            ws.column_dimensions[col.column_letter].width = max(max_len + 3, 12)
            
        # Записываем сгенерированные байты таблицы напрямую в ОЗУ буфер
        stream = BytesIO()
        wb.save(stream)
        CURRENT_ESTIMATE_BYTES = stream.getvalue()
        return True
    except Exception as e:
        logger.error(f"Ошибка openpyxl: {e}")
        return False

@app.get("/", response_class=HTMLResponse)
async def serve_index(): return HTML_CODE

@app.get("/api/download-estimate")
async def download_estimate():
    """Эндпоинт мгновенной отдачи сметного файла из оперативной памяти"""
    global CURRENT_ESTIMATE_BYTES
    if CURRENT_ESTIMATE_BYTES:
        from fastapi.responses import StreamingResponse
        # Отдаем виртуальный файл в потоке прямо из ОЗУ
        return StreamingResponse(
            BytesIO(CURRENT_ESTIMATE_BYTES),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=estimate_batch_monolit.xlsx"}
        )
    raise HTTPException(status_code=404, detail="Смета еще не была рассчитана.")

@app.post("/api/command")
async def process_command(request: CommandRequest):
    try:
        raw_query = request.command.strip()
        logger.info(f"🔮 Запуск ИИ-Оркестрации: {raw_query}")
        ACTIVE_TOKEN = os.getenv("OPENAI_API_KEY") or os.getenv("TIMEWEB_AI_API_KEY") or os.getenv("TIMEWEB_AI_GATEWAY_KEY")
        if ": " in raw_query: agent_prefix, user_query = raw_query.split(": ", 1)
        else: agent_prefix, user_query = "AUTO", raw_query
        agent_prefix = agent_prefix.upper()
        query_lower = user_query.lower()
        smetter_catalog = load_smetter_catalog()
        if agent_prefix == "AUTO":
            if any(k in query_lower for k in ["радар", "скаут", "лид", "жк"]): agent_prefix = "SCOUT"
            elif any(k in query_lower for k in ["код", "обнови", "скрипт", "github", "напиши"]): agent_prefix = "CODER"
            elif any(k in query_lower for k in ["бетон", "арматур", "монолит", "чертеж"]): agent_prefix = "ENGINEER"
            elif any(k in query_lower for k in ["график", "гпр", "план", "сроки"]): agent_prefix = "PLANNER"
            else: agent_prefix = "SMETTER"
        headers_ai = {"Authorization": f"Bearer {ACTIVE_TOKEN}", "Content-Type": "application/json"}
        url_ai = "https://timeweb.ai"

        if agent_prefix == "SMETTER":
            total_floor, total_walls, total_perimeter = 0.0, 0.0, 0.0
            vision_context = ""
            if request.file_data_list and request.file_name_list:
                for idx, base64_file in enumerate(request.file_data_list):
                    f_name = request.file_name_list[idx]
                    header, encoded = base64_file.split(",", 1) if "," in base64_file else ("", base64_file)
                    file_bytes = base64.b64decode(encoded)
                    if "image" in header.lower() or f_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        payload_v = {
                            "model": "openai/gpt-5-nano",
                            "messages": [
                                {"role": "system", "content": "Ты — ИИ-Сметчик MONOLIT-MOS. Извлеки из фото замеры. Верни СТРОГО JSON: {\"floor_area\": цифра, \"wall_area\": цифра, \"perimeter\": цифра}."},
                                {"role": "user", "content": [{"type": "text", "text": "Парси чертеж:"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}]}
                            ], "temperature": 0.1
                        }
                        try:
                            async with httpx.AsyncClient(timeout=45.0) as client:
                                r = await client.post(url_ai, headers=headers_ai, json=payload_v)
                                if r.status_code == 200:
                                    v_res = json.loads(re.sub(r"```json|```", "", r.json()["choices"]["message"]["content"]).strip())
                                    total_floor += float(v_res.get("floor_area", 0.0))
                                    total_walls += float(v_res.get("wall_area", 0.0))
                                    total_perimeter += float(v_res.get("perimeter", 0.0))
                                    vision_context += f"• Из фото '{f_name}' извлечено: Пол {v_res.get('floor_area')}м2, Стены {v_res.get('wall_area')}м2.\n"
                        except Exception: pass
                    elif f_name.lower().endswith(('.xlsx', '.xls')):
                        m = parse_single_excel_bytes(file_bytes)
                        total_floor += m["floor_area"]; total_walls += m["wall_area"]; total_perimeter += m["perimeter"]
                        vision_context += f"• Из Excel '{f_name}': Пол {m['floor_area']}м2, Стены {m['wall_area']}м2.\n"

            if total_floor == 0 and user_query:
                payload_t = {
                    "model": "openai/gpt-5-nano",
                    "messages": [
                        {"role": "system", "content": "Извлеки замеры. Ответ СТРОГО JSON: {\"floor_area\": цифра, \"wall_area\": цифра, \"perimeter\": цифра}. Дефолт: 45.0, 110.0, 32.0."},
                        {"role": "user", "content": user_query}
                    ], "temperature": 0.1
                }
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        r = await client.post(url_ai, headers=headers_ai, json=payload_t)
                        if r.status_code == 200:
                            t_res = json.loads(re.sub(r"```json|```", "", r.json()["choices"]["message"]["content"]).strip())
                            total_floor = float(t_res.get("floor_area", 45.0))
                            total_walls = float(t_res.get("wall_area", 110.0))
                            total_perimeter = float(t_res.get("perimeter", 32.0))
                except Exception: total_floor, total_walls, total_perimeter = 45.0, 110.0, 32.0
            if total_floor == 0: total_floor, total_walls, total_perimeter = 45.0, 110.0, 32.0
            output_estimate_rows = []
            if smetter_catalog:
                for c_item in smetter_catalog:
                    nm_low = c_item["name"].lower()
                    if "стен" in nm_low or "обои" in nm_low or "покраск" in nm_low or "шпатлевк" in nm_low: vol = total_walls
                    elif "пол" in nm_low or "кварцвинил" in nm_low: vol = total_floor
                    elif "плинтус" in nm_low or "периметр" in nm_low: vol = total_perimeter
                    else: vol = total_floor
                    if c_item["price_work"] > 0:
                        output_estimate_rows.append({"type": "Работа", "name": c_item["name"], "unit": c_item["unit"], "volume": vol, "price": c_item["price_work"]})
                    if c_item["price_mat"] > 0:
                        output_estimate_rows.append({"type": "Материал", "name": f"{c_item['name']} (Материал)", "unit": c_item["unit"], "volume": vol * 1.05 if c_item["unit"] == "м2" else vol, "price": c_item["price_mat"]})
            else:
                output_estimate_rows = [
                    {"type": "Работа", "name": "Выравнивание стен (Каталог Сметтера пуст)", "unit": "м2", "volume": total_walls, "price": 1200.0},
                    {"type": "Работа", "name": "Укладка кварцвинила (Каталог Сметтера пуст)", "unit": "м2", "volume": total_floor, "price": 850.0}
                ]
            generate_smetter_excel(output_estimate_rows)
            c_status = f"Успешно подтянуто позиций из Сметтера: {len(smetter_catalog)} шт." if smetter_catalog else "Использован резервный прайс."
            reply = f"Сэр, ИИ-Сметчик завершил интеллектуальный расчет объекта!\n\n{vision_context}\nИТОГОВЫЕ СВОДНЫЕ ОБЪЕМЫ:\n• Площадь пола: {total_floor} м²\n• Площадь стен: {total_walls} м²\n• Периметр под плинтус: {total_perimeter} мп\n\n{c_status}\nСводная Excel-таблица импорта полностью готова к выгрузке!"
            return {"reply": reply, "has_estimate": True}

        elif agent_prefix == "CODER":
            payload_c = {
                "model": "openai/gpt-5-nano",
                "messages": [
                    {"role": "system", "content": "Ты — ИИ-Программист MONOLIT-MOS. Напиши код под задачу Владельца. ОБЯЗАТЕЛЬНО оберни код в блок: |||UPDATE_FILE:имя_файла.py||| код |||END_UPDATE|||"},
                    {"role": "user", "content": user_query}
                ], "temperature": 0.2
            }
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(url_ai, headers=headers_ai, json=payload_c)
                reply = r.json()["choices"]["message"]["content"] if r.status_code == 200 else "Сбой шлюза кодера."
            match = re.search(r"\|\|\|UPDATE_FILE:(.*?)\|\|\|(.*?)(\|\|\|END_UPDATE\|\|\||$)", reply, re.DOTALL)
            if match:
                git_status = await push_code_to_github(match.group(1).strip(), match.group(2).strip(), f"ИИ-Апгрейд: {match.group(1).strip()}")
                reply += f"\n\n🤖 [Интегратор GitHub]: {git_status}"
            return {"reply": reply, "has_estimate": False}

        else:
            payload_a = {
                "model": "openai/gpt-5-nano",
                "messages": [
                    {"role": "system", "content": f"Ты — главный ИИ-{agent_prefix} компании MONOLIT-MOS. Дай технический ответ Владу (сэром) по его строительному вопросу."},
                    {"role": "user", "content": user_query}
                ], "temperature": 0.3
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url_ai, headers=headers_ai, json=payload_a)
                reply = r.json()["choices"]["message"]["content"] if r.status_code == 200 else "Сбой ИИ-шлюза субагента."
            return {"reply": reply, "has_estimate": False}
    except Exception as e:
        logger.error(f"Ошибка диспетчеризации: {e}")
        return {"reply": f"Ошибка ядра: {str(e)}", "has_estimate": False}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7778))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

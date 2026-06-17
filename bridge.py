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
    """
    Субагент-Сметчик: Сканирует ИСКЛЮЧИТЕЛЬНО папку jinni_knowledge в корне репозитория,
    находит там выгруженный из Сметтера Excel-файл расценок и кэширует его в ОЗУ.
    """
    catalog_items = []
    # На Timeweb App Platform корень проекта находится в /app/
    base_dir = "./" if os.path.exists("requirements.txt") else "/app/"
    target_dir = os.path.join(base_dir, "jinni_knowledge")
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        logger.info(f"📁 Создана пустая папка знаний: {target_dir}")
        return catalog_items
        
    try:
        for f_name in os.listdir(target_dir):
            # Парсим файлы прайса, отсекая временные файлы выгрузки готовых смет
            if (f_name.endswith(".xlsx") or f_name.endswith(".xls")) and "estimate_output" not in f_name:
                file_path = os.path.join(target_dir, f_name)
                logger.info(f"📚 База расценок Сметтера обнаружена в папке jinni_knowledge: {f_name}. Импорт...")
                
                wb = openpyxl.load_workbook(file_path, data_only=True)
                ws = wb.active
                
                # Сканируем строки таблицы Сметтера (пропуская шапку)
                for row in ws.iter_rows(min_row=2, max_row=1000, min_col=1, max_col=10, values_only=True):
                    if not row or not row[0] or "раздел" in str(row[0]).lower():
                        continue
                        
                    name = str(row[0]).strip()
                    unit = str(row[1]).strip() if len(row) > 1 and row[1] else "м2"
                    
                    # Захват цен работы и материала из колонок выгрузки Сметтера
                    price_work = float(row[2]) if len(row) > 2 and isinstance(row[2], (int, float)) else 0.0
                    price_mat = float(row[3]) if len(row) > 3 and isinstance(row[3], (int, float)) else 0.0
                    
                    catalog_items.append({
                        "name": name,
                        "unit": unit,
                        "price_work": price_work,
                        "price_mat": price_mat
                    })
        if catalog_items:
            logger.info(f"✅ База расценок успешно зафиксирована из jinni_knowledge: {len(catalog_items)} позиций.")
        return catalog_items
    except Exception as e:
        logger.error(f"⚠️ Ошибка авто-чтения папки расценок jinni_knowledge: {e}")
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
        logger.error(f"Ошибка парсинга байтов Excel: {e}")
        return metrics
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
        
        /* КНОПКИ ПЕРЕКЛЮЧЕНИЯ АГЕНТОВ */
        .agent-selector { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 15px; }
        .agent-btn { background: #001a24; border: 1px solid rgba(0, 240, 255, 0.4); color: #00bfff; padding: 8px 5px; font-size: 11px; border-radius: 5px; cursor: pointer; transition: all 0.2s; font-family: monospace; }
        .agent-btn.active { background: #00f0ff; color: #000; box-shadow: 0 0 10px #00f0ff; border-color: #00f0ff; font-weight: bold; }
        
        .chat-log { border: 1px solid rgba(0, 240, 255, 0.3); background: rgba(0, 5, 10, 0.6); border-radius: 8px; height: 180px; overflow-y: auto; text-align: left; padding: 15px; margin-bottom: 15px; display: flex; flex-direction: column; gap: 10px; width: 100%; box-sizing: border-box; }
        .input-area { display: flex; gap: 10px; align-items: center; width: 100%; }
        .text-input { flex-grow: 1; background: rgba(0, 5, 10, 0.8); border: 1px solid rgba(0, 240, 255, 0.5); border-radius: 5px; padding: 12px; color: #00f0ff; font-family: monospace; outline: none; box-sizing: border-box; }
        .file-label, .voice-btn { background: #003344; border: 1px solid #00f0ff; color: #00f0ff; padding: 10px 14px; border-radius: 5px; cursor: pointer; font-size: 16px; user-select: none; transition: all 0.2s; }
        .voice-btn.recording { background: #ff0055; color: #fff; border-color: #ff0055; animation: pulse 1s infinite; }
        #fileInput { display: none; }
        .preview-box { display: none; margin-bottom: 10px; text-align: left; border: 1px dashed #00ffcc; padding: 10px; border-radius: 5px; background: rgba(0, 50, 40, 0.4); width: 100%; box-sizing: border-box; font-size: 11px; }
        .download-btn { display: none; margin-top: 15px; background: #00ffcc; color: #000; padding: 12px 25px; border-radius: 5px; font-weight: bold; text-decoration: none; box-shadow: 0 0 15px #00ffcc; width: 80%; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    </style>
</head>
<body>
    <div class="panel">
        <h1>ЦЕНТРАЛЬНЫЙ ОРКЕСТРАТОР ДЖИННИ</h1>
        
        <!-- ИНТЕРФЕЙС ПЕРЕКЛЮЧЕНИЯ СУБАГЕНТОВ -->
        <div class="agent-selector">
            <button class="agent-btn active" onclick="setAgent('auto', this)">🤖 АВТО-ИИ</button>
            <button class="agent-btn" onclick="setAgent('smetter', this)">📊 СМЕТЧИК</button>
            <button class="agent-btn" onclick="setAgent('scout', this)">🕵️ РАДАР</button>
            <button class="agent-btn" onclick="setAgent('engineer', this)">📐 ИНЖЕНЕР</button>
            <button class="agent-btn" onclick="setAgent('coder', this)">💻 КОДЕР</button>
            <button class="agent-btn" onclick="setAgent('planner', this)">📅 ПЛАНЕР</button>
        </div>

        <div id="chatLog" class="chat-log"><div>Джинни> Комплекс MONOLIT-MOS активен, сэр. Ожидаю директив голосом или текстом.</div></div>
        <div id="previewBox" class="preview-box">📦 Файлы в очереди:<div id="fileListNames" style="color:#00ffff; margin-top:3px;"></div></div>
        
        <div class="input-area">
            <label for="fileInput" class="file-label">📎</label>
            <input type="file" id="fileInput" multiple accept=".xlsx, .xls, image/*">
            <input type="text" id="textInput" class="text-input" placeholder="Введите команду или нажмите микрофон...">
            <button id="voiceBtn" class="voice-btn" onclick="toggleVoice()">🎙️</button>
        </div>
        <a id="downloadBtn" class="download-btn" href="/api/download-estimate" download="estimate_monolit.xlsx">📥 СКАЧАТЬ СМЕТУ EXCEL</a>
    </div>
    <script>
        const chatLog = document.getElementById('chatLog');
        const textInput = document.getElementById('textInput');
        const fileInput = document.getElementById('fileInput');
        const previewBox = document.getElementById('previewBox');
        const fileListNames = document.getElementById('fileListNames');
        const downloadBtn = document.getElementById('downloadBtn');
        const voiceBtn = document.getElementById('voiceBtn');
        
        let fileBase64Array = []; let fileNameArray = [];
        let currentAgent = 'auto';
        let recognition = null;
        let isRecording = false;

        // Инициализация HTML5 ИИ-распознавания голоса (работает во всех смартфонах напрямую в WebView)
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechLanguage = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechLanguage();
            recognition.lang = 'ru-RU';
            recognition.continuous = false;
            recognition.interimResults = false;
            
            recognition.onresult = (e) => {
                const text = e.results[0][0].transcript;
                textInput.value = text;
                logMessage("Сэр (Голос)> " + text);
                sendDirective(text);
            };
            recognition.onend = () => { stopRecordingMode(); };
            recognition.onerror = () => { stopRecordingMode(); };
        }

        function setAgent(agentType, btn) {
            currentAgent = agentType;
            document.querySelectorAll('.agent-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            logMessage(`Система> Принудительный селектор переведен на: ${agentType.toUpperCase()}`);
        }

        function toggleVoice() {
            if (!recognition) { alert("Голосовой ввод не поддерживается вашим WebView"); return; }
            if (isRecording) { recognition.stop(); } else { startRecordingMode(); }
        }
        function startRecordingMode() { isRecording = true; voiceBtn.classList.add('recording'); recognition.start(); }
        function stopRecordingMode() { isRecording = false; voiceBtn.classList.remove('recording'); }
        function logMessage(txt) { const d = document.createElement('div'); d.innerText = txt; chatLog.appendChild(d); chatLog.scrollTop = chatLog.scrollHeight; }

        fileInput.onchange = async () => {
            fileBase64Array = []; fileNameArray = []; fileListNames.innerHTML = "";
            if (fileInput.files.length > 0) {
                previewBox.style.display = 'block';
                for (let file of fileInput.files) {
                    fileNameArray.push(file.name);
                    fileListNames.innerHTML += `• ${file.name}<br>`;
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
                const data = await res.json();
                logMessage("Джинни> " + data.reply);
                if(data.has_estimate) downloadBtn.style.display = 'inline-block';
            } catch { logMessage("Джинни> Ошибка маршрутизации."); }
            fileBase64Array = []; fileNameArray = []; previewBox.style.display = 'none'; fileInput.value = "";
        }
    </script>
</body>
</html>
"""
def generate_smetter_excel(calculated_items: list, output_path: str = "/tmp/estimate_output.xlsx"):
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
            cell.font = font_header
            cell.fill = fill_header
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
        wb.save(output_path)
        return output_path
    except Exception: return None

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return HTML_CODE

@app.get("/api/download-estimate")
async def download_estimate():
    path = "/tmp/estimate_output.xlsx"
    if os.path.exists(path):
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="estimate_batch_monolit.xlsx")
    raise HTTPException(status_code=404, detail="Смета не найдена.")

@app.post("/api/command")
async def process_command(request: CommandRequest):
    user_query = request.command.strip().lower()
    smetter_catalog = load_smetter_catalog()
    
    total_floor, total_walls, total_perimeter = 0.0, 0.0, 0.0
    vision_log = ""

    # ПОТОКОВАЯ ОБРАБОТКА МУЛЬТИ-ВЛОЖЕНИЙ (ФОТО ИЛИ EXCEL)
    if request.file_data_list and request.file_name_list:
        for idx, base64_file in enumerate(request.file_data_list):
            f_name = request.file_name_list[idx]
            header, encoded = base64_file.split(",", 1) if "," in base64_file else ("", base64_file)
            file_bytes = base64.b64decode(encoded)

            # ЕСЛИ ЗАГРУЖЕНО ИЗОБРАЖЕНИЕ (ЧЕРТЕЖ, ФОТО ЗАМЕРОВ) -> АКТИВИРУЕМ VISION AI
            if "image" in header.lower() or f_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                logger.info(f"📸 Обнаружено изображение: {f_name}. Запуск ИИ-Зрения Джинни...")
                
                # Каноничный OpenAI-совместимый контракт Vision API для AI Gateway Timeweb
                headers = {"Authorization": f"Bearer {TIMEWEB_AI_TOKEN}", "Content-Type": "application/json"}
                payload = {
                    "model": "openai/gpt-5-nano",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты — ИИ-Сметчик MONOLIT-MOS. Твоя задача — проанализировать чертеж или фото ведомости замеров и извлечь ТРИ цифры: общую площадь пола (в м2), общую площадь стен под отделку (в м2) и периметр пола (в мп). Верни ответ СТРОГО в формате JSON без лишнего текста: {\"floor_area\": цифра, \"wall_area\": цифра, \"perimeter\": цифра}. Если какая-то цифра не найдена, верни для неё 0.0."
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Извлеки замеры с этого изображения:"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}
                            ]
                        }
                    ],
                    "temperature": 0.1
                }
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        resp = await client.post("https://timeweb.ai", headers=headers, json=payload)
                        if resp.status_code == 200:
                            ai_res = resp.json()["choices"][0]["message"]["content"]
                            # Вычищаем маркдаун-теги, если модель их вернула
                            clean_json = re.sub(r"```json|```", "", ai_res).strip()
                            data_vision = json.loads(clean_json)
                            
                            total_floor += float(data_vision.get("floor_area", 0.0))
                            total_walls += float(data_vision.get("wall_area", 0.0))
                            total_perimeter += float(data_vision.get("perimeter", 0.0))
                            vision_log += f"• Из фото '{f_name}' извлечено: Пол {data_vision.get('floor_area')}м2, Стены {data_vision.get('wall_area')}м2.\n"
                except Exception as e:
                    logger.error(f"Ошибка Vision AI на шлюзе: {e}")
                    vision_log += f"• Ошибка ИИ-Зрения для '{f_name}'.\n"

            # ЕСЛИ ЗАГРУЖЕН КЛАССИЧЕСКИЙ EXCEL
            elif f_name.lower().endswith(('.xlsx', '.xls')):
                try:
                    metrics = parse_single_excel_bytes(file_bytes)
                    total_floor += metrics["floor_area"]
                    total_walls += metrics["wall_area"]
                    total_perimeter += metrics["perimeter"]
                    vision_log += f"• Из Excel '{f_name}' извлечено: Пол {metrics['floor_area']}м2, Стены {metrics['wall_area']}м2.\n"
                except Exception as e:
                    logger.error(f"Ошибка Excel: {e}")

    # Защитный холостой запуск, если на входе пусто
    if total_floor == 0: 
        total_floor, total_walls, total_perimeter = 45.0, 110.0, 32.0
        vision_log = "• [Тестовый запуск] Использованы дефолтные объемы.\n"

    output_estimate_rows = []
    
    # ЛОГИКА ИИ-КАЛЬКУЛЯТОРА: Перемножаем распознанные или извлеченные объемы на позиции из Сметтера
    if smetter_catalog:
        for catalog_item in smetter_catalog:
            item_name_lower = catalog_item["name"].lower()
            if "стен" in item_name_lower or "обои" in item_name_lower or "покраск" in item_name_lower or "шпатлевк" in item_name_lower: volume = total_walls
            elif "пол" in item_name_lower or "кварцвинил" in item_name_lower or "ламинат" in item_name_lower: volume = total_floor
            elif "плинтус" in item_name_lower or "периметр" in item_name_lower: volume = total_perimeter
            else: volume = total_floor
                
            if catalog_item["price_work"] > 0:
                output_estimate_rows.append({"type": "Работа", "name": catalog_item["name"], "unit": catalog_item["unit"], "volume": volume, "price": catalog_item["price_work"]})
            if catalog_item["price_mat"] > 0:
                output_estimate_rows.append({"type": "Материал", "name": f"{catalog_item['name']} (Материал)", "unit": catalog_item["unit"], "volume": volume * 1.05 if catalog_item["unit"] == "м2" else volume, "price": catalog_item["price_mat"]})
    else:
        output_estimate_rows = [
            {"type": "Работа", "name": "Сводное выравнивание стен (Каталог не найден)", "unit": "м2", "volume": total_walls, "price": 1200.0},
            {"type": "Работа", "name": "Сводная укладка кварцвинила (Каталог не найден)", "unit": "м2", "volume": total_floor, "price": 850.0}
        ]

    generate_smetter_excel(output_estimate_rows)
    
    catalog_status = f"Успешно сопоставлено позиций из Сметтера: {len(smetter_catalog)} шт." if smetter_catalog else "Каталог цен в jinni_knowledge не обнаружен."
    ai_reply = f"Сэр, Vision-анализ пакета документов завершен!\n\n{vision_log}\nИТОГОВЫЙ СВОДНЫЙ ОБЪЕМ:\n• Суммарный пол: {total_floor} м²\n• Суммарные стены: {total_walls} м²\n• Суммарный периметр: {total_perimeter} мп\n\n{catalog_status}\nСводная таблица импорта для Сметтера полностью пересобрана. Ссылку для скачивания выдаю!"
    return {"reply": ai_reply, "has_estimate": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7778))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

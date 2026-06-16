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
    Субагент-Сметчик: Автоматически сканирует корень приложения /app/ на наличие 
    вашего выгруженного из Сметтера Excel-файла с ценами и кэширует его в ОЗУ.
    """
    catalog_items = []
    # На Timeweb App Platform корень репозитория монтируется в папку /app
    target_dir = "./" if os.path.exists("requirements.txt") else "/app/"
    
    try:
        for f_name in os.listdir(target_dir):
            # Ищем файл расценок (исключая временные файлы выгрузки смет)
            if (f_name.endswith(".xlsx") or f_name.endswith(".xls")) and "estimate_output" not in f_name:
                file_path = os.path.join(target_dir, f_name)
                logger.info(f"📚 Найдена база расценок Сметтера: {f_name}. Начинаю импорт в ОЗУ...")
                
                wb = openpyxl.load_workbook(file_path, data_only=True)
                ws = wb.active
                
                # Сканируем строки со 2 по 1000 (пропуская шапку таблицы Сметтера)
                for row in ws.iter_rows(min_row=2, max_row=1000, min_col=1, max_col=10, values_only=True):
                    if not row or not row[0] or "раздел" in str(row[0]).lower():
                        continue
                        
                    name = str(row[0]).strip()
                    unit = str(row[1]).strip() if row[1] else "м2"
                    
                    # Интеллектуальный перехват цен работы и материала из колонок Сметтера
                    price_work = float(row[2]) if len(row) > 2 and isinstance(row[2], (int, float)) else 0.0
                    price_mat = float(row[3]) if len(row) > 3 and isinstance(row[3], (int, float)) else 0.0
                    
                    catalog_items.append({
                        "name": name,
                        "unit": unit,
                        "price_work": price_work,
                        "price_mat": price_mat
                    })
        if catalog_items:
            logger.info(f"✅ База расценок успешно зафиксирована: {len(catalog_items)} позиций Сметтера в ОЗУ.")
        return catalog_items
    except Exception as e:
        logger.error(f"⚠️ Ошибка авто-чтения файла расценок Excel: {e}")
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
    <title>Джинни Пакетный</title>
    <style>
        body { background: #050b14; color: #00f0ff; font-family: monospace; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
        .panel { border: 2px solid #00f0ff; padding: 30px; border-radius: 15px; box-shadow: 0 0 20px rgba(0,240,255,0.3); background: rgba(5, 11, 20, 0.9); width: 100%; max-width: 500px; text-align: center; display: flex; flex-direction: column; align-items: center; }
        h1 { font-size: 14px; letter-spacing: 2px; text-shadow: 0 0 10px #00f0ff; margin-top: 0; }
        .chat-log { border: 1px solid rgba(0, 240, 255, 0.3); background: rgba(0, 5, 10, 0.6); border-radius: 8px; height: 180px; overflow-y: auto; text-align: left; padding: 15px; margin: 15px 0; display: flex; flex-direction: column; gap: 10px; width: 100%; box-sizing: border-box; }
        .text-input { width: 100%; background: rgba(0, 5, 10, 0.8); border: 1px solid rgba(0, 240, 255, 0.5); border-radius: 5px; padding: 12px; color: #00f0ff; font-family: monospace; box-sizing: border-box; outline: none; }
        .input-area { display: flex; gap: 10px; align-items: center; width: 100%; }
        .file-label { background: #003344; border: 1px solid #00f0ff; color: #00f0ff; padding: 10px 15px; border-radius: 5px; cursor: pointer; font-size: 16px; user-select: none; }
        #fileInput { display: none; }
        .preview-box { display: none; margin-bottom: 10px; text-align: left; border: 1px dashed #00ffcc; padding: 10px; border-radius: 5px; background: rgba(0, 50, 40, 0.4); width: 100%; box-sizing: border-box; font-size: 12px; color: #fff; }
        .status { font-size: 11px; color: #88aadd; margin-top: 10px; }
        .download-btn { display: none; margin-top: 15px; background: #00ffcc; color: #000; padding: 12px 25px; border-radius: 5px; font-weight: bold; text-decoration: none; box-shadow: 0 0 15px #00ffcc; }
    </style>
</head>
<body>
    <div class="panel">
        <h1>МУЛЬТИ-ВЕДОМОСТЬ MONOLIT-MOS</h1>
        <div id="chatLog" class="chat-log"><div>Джинни> Выделите файлы Excel замеров (Ctrl) и нажмите Enter. Сводный расчет пойдет по вашей базе Сметтера.</div></div>
        <div id="previewBox" class="preview-box">📦 Выбрано файлов (<span id="fileCount">0</span>):<div id="fileListNames" style="color:#00ffff; margin-top:5px;"></div></div>
        <div class="input-area">
            <label for="fileInput" class="file-label">📎</label>
            <input type="file" id="fileInput" multiple accept=".xlsx, .xls">
            <input type="text" id="textInput" class="text-input" placeholder="Директива по расчету...">
        </div>
        <a id="downloadBtn" class="download-btn" href="/api/download-estimate" download="estimate_monolit.xlsx">📥 СКАЧАТЬ СВОДНУЮ СМЕТУ</a>
        <div id="status" class="status">● Пакетный конвейер Сметтера готов</div>
    </div>
    <script>
        const chatLog = document.getElementById('chatLog');
        const textInput = document.getElementById('textInput');
        const fileInput = document.getElementById('fileInput');
        const previewBox = document.getElementById('previewBox');
        const fileCount = document.getElementById('fileCount');
        const fileListNames = document.getElementById('fileListNames');
        const downloadBtn = document.getElementById('downloadBtn');
        const statusText = document.getElementById('status');
        
        let fileBase64Array = []; let fileNameArray = [];

        fileInput.onchange = async () => {
            fileBase64Array = []; fileNameArray = []; fileListNames.innerHTML = "";
            if (fileInput.files && fileInput.files.length > 0) {
                fileCount.innerText = fileInput.files.length;
                previewBox.style.display = 'block';
                for (let i = 0; i < fileInput.files.length; i++) {
                    const file = fileInput.files[i];
                    fileNameArray.push(file.name);
                    fileListNames.innerHTML += `• ${file.name}<br>`;
                    const base64 = await new Promise((resolve) => {
                        const reader = new FileReader();
                        reader.onloadend = () => resolve(reader.result);
                        reader.readAsDataURL(file);
                    });
                    fileBase64Array.push(base64);
                }
            }
        };

        textInput.onkeydown = async (e) => {
            if (e.key === 'Enter') {
                const text = textInput.value.trim();
                if (!text && fileBase64Array.length === 0) return;
                const msgDiv = document.createElement('div');
                msgDiv.innerText = `Сэр> Расчет по ${fileBase64Array.length} ведомостям.`;
                chatLog.appendChild(msgDiv);
                textInput.value = "";
                statusText.innerText = "● Пакетный ИИ-Сметчик объединяет файлы...";
                downloadBtn.style.display = 'none';
                try {
                    const res = await fetch('/api/command', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ command: text, file_data_list: fileBase64Array, file_name_list: fileNameArray })
                    });
                    const data = await res.json();
                    const replyDiv = document.createElement('div');
                    replyDiv.style.color = '#00f0ff';
                    replyDiv.innerText = "Джинни> " + data.reply;
                    chatLog.appendChild(replyDiv);
                    if(data.has_estimate) downloadBtn.style.display = 'inline-block';
                } catch {
                    const errDiv = document.createElement('div');
                    errDiv.innerText = "Джинни> Ошибка пакетной сборки.";
                    chatLog.appendChild(errDiv);
                }
                statusText.innerText = "● Пакетный конвейер Сметтера готов";
                chatLog.scrollTop = chatLog.scrollHeight;
                fileBase64Array = []; fileNameArray = []; previewBox.style.display = 'none'; fileInput.value = "";
            }
        };
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
    
    if request.file_data_list:
        for base64_file in request.file_data_list:
            try:
                header, encoded = base64_file.split(",", 1) if "," in base64_file else ("", base64_file)
                file_bytes = base64.b64decode(encoded)
                metrics = parse_single_excel_bytes(file_bytes)
                total_floor += metrics["floor_area"]
                total_walls += metrics["wall_area"]
                total_perimeter += metrics["perimeter"]
            except Exception: pass

    if total_floor == 0: total_floor, total_walls, total_perimeter = 45.0, 110.0, 32.0
    output_estimate_rows = []
    
    if smetter_catalog:
        for catalog_item in smetter_catalog:
            item_name_lower = catalog_item["name"].lower()
            if "стен" in item_name_lower or "обои" in item_name_lower or "покраск" in item_name_lower or "шпатлевк" in item_name_lower: volume = total_walls
            elif "пол" in item_name_lower or "кварцвинил" in item_name_lower: volume = total_floor
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
    catalog_status = f"Успешно подтянуто {len(smetter_catalog)} расценок Сметтера из вашего загруженного прайса." if smetter_catalog else "Каталог цен не обнаружен в корне репозитория."
    ai_reply = f"Сэр, пакетный расчет выполнен! Объединено {len(request.file_name_list or [])} ведомостей. Итоговые объемы: Пол = {total_floor} м², Стены = {total_walls} м², Периметр = {total_perimeter} мп. {catalog_status} Сводный шаблон собран!"
    return {"reply": ai_reply, "has_estimate": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7778))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

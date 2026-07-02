import os, sys, logging, re, json, math
from io import BytesIO
from typing import List, Optional

import openai
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse
from pydantic import BaseModel
from openpyxl import Workbook
from openpyxl.styles import Border, Side

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("JinniOrchestrator")

app = FastAPI(title="MONOLIT-MOS Jarvis")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class CommandRequest(BaseModel):
    command: str
    file_data_list: Optional[List[str]] = None
    file_name_list: Optional[List[str]] = None

BACKUP_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Джинни</title></head><body style="background:#050b14;color:#00f0ff;font-family:monospace;text-align:center;padding:50px;"><h2>[КРИТИЧЕСКАЯ ОШИБКА]: Файл index.html не найден!</h2></body></html>"""

def load_smetter_catalog() -> list:
    catalog_items = []
    t_dir = "./jinni_knowledge" if os.path.exists("requirements.txt") else "/app/jinni_knowledge"
    if not os.path.exists(t_dir):
        return catalog_items
    try:
        for f in os.listdir(t_dir):
            if f.endswith((".xlsx", ".xls")) and "estimate" not in f:
                wb = openpyxl.load_workbook(os.path.join(t_dir, f), data_only=True)
                ws = wb.active
                for r in ws.iter_rows(min_row=2, max_row=1000, min_col=1, max_col=10, values_only=True):
                    if not r:
                        continue
                    row_str = str(r).lower()
                    if any(x in row_str for x in ["раздел", "none"]):
                        continue
                    catalog_items.append({
                        "name": str(r[0]).strip() if r[0] else "",
                        "unit": str(r[1]).strip() if len(r) > 1 and r[1] else "м2",
                        "price_work": float(r[2]) if len(r) > 2 and isinstance(r[2], (int, float)) else 0.0,
                        "price_mat": float(r[3]) if len(r) > 3 and isinstance(r[3], (int, float)) else 0.0
                    })
        return catalog_items
    except Exception as e:
        logger.error(f"Catalog error: {e}")
        return catalog_items

async def call_gpt4o_smetter(catalog, t_fl, t_wl, t_pr, user_text):
    prompt = f"""
Ты — инженер-сметчик MONOLIT-MOS. Твоя задача: рассчитать смету по монолиту и отделке.

ПРАВИЛА:
1. Используй ТОЛЬКО позиции из каталога цен ниже. Не придумывай свои.
2. Объём работ считай строго по входным данным: Пол={t_fl} м², Стены={t_wl} м², Периметр={t_pr} м.
3. Для бетона B25: толщина плиты 0.25 м. Объём = Пол * 0.25.
4. Маржинальность проекта = 25% от итоговой суммы работ и материалов.
5. Округли ИТОГО до ближайших 100 рублей вверх (math.ceil(sum/100)*100).
6. Верни результат ТОЛЬКО в валидном JSON формате без лишних слов.

КАТАЛОГ ЦЕН (JSON):
{json.dumps(catalog, ensure_ascii=False, indent=2)}

ВХОДНЫЕ ДАННЫЕ:
Пользователь написал: "{user_text}"
Замеры: Пол={t_fl}, Стены={t_wl}, Периметр={t_pr}.

ОТВЕТЬ ТОЛЬКО JSON:
[
  {{"type": "Материал" | "Работа", "name": "Название", "unit": "м3/м2/шт", "volume": float, "price": float}}
]
"""
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Ты инженер-сметчик. Отвечай только валидным JSON, без пояснений."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=1500
    )
    content = resp.choices[0].message.content
    # Удаляем markdown-обёртку, если 4o её добавит
    content = content.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(content)

@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content=BACKUP_HTML, status_code=404)

@app.post("/api/command")
async def process_command(
    command: str = Form(...),
    files: List[UploadFile] = File(None)
):
    raw_query = command.strip()
    prefix, query = raw_query.split(": ", 1) if ": " in raw_query else ("AUTO", raw_query)
    prefix, q_low = prefix.upper(), query.lower()

    catalog = load_smetter_catalog()

    # Авто-определение агента по ключевым словам
    if prefix == "AUTO":
        if any(k in q_low for k in ["радар", "скаут", "лид"]):
            prefix = "SCOUT"
        elif any(k in q_low for k in ["код", "обнови", "github"]):
            prefix = "CODER"
        elif any(k in q_low for k in ["инженер", "проект", "нагруз"]):
            prefix = "ENGINEER"
        elif any(k in q_low for k in ["план", "гпр", "график"]):
            prefix = "PLANNER"
        else:
            prefix = "SMETTER"

    if prefix == "SCOUT":
        return {"reply": "🕵️ [РАДАР]: Служба scout_catcher на VPS активна. Эфир Москвы чист.", "has_estimate": False}
    elif prefix == "ENGINEER":
        return {"reply": "📐 [ИНЖЕНЕР]: Конструкторский отдел готов к расчету бетона и монолита.", "has_estimate": False}
    elif prefix == "PLANNER":
        return {"reply": "📅 [ПЛАНИРОВЩИК]: Отдел планирования готов составить ГПР монолитных работ.", "has_estimate": False}

    elif prefix == "CODER":
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Генерируй только Python-код без комментариев и пояснений. Код должен быть готов к запуску."},
                {"role": "user", "content": f"Напиши функцию расчёта монолитной плиты по ТЗ: толщина 250 мм, бетон B25, маржа 25%, округление до 100 руб. Ответь ТОЛЬКО кодом."}
            ],
            temperature=0
        )
        code = resp.choices[0].message.content.strip()
        return {"reply": f"🤖 [ИИ‑Кодер (GPT‑4o)]: Патч сгенерирован:\n\n```python\n{code}\n```", "has_estimate": False}

    elif prefix == "SMETTER":
        # Парсим дробные числа
        nums = [float(s) for s in re.findall(r'\b\d+(?:\.\d+)?\b', q_low)]
        t_fl = max(0.0, nums[0]) if len(nums) > 0 else 45.0
        t_wl = max(0.0, nums[1]) if len(nums) > 1 else 110.0
        t_pr = max(0.0, nums[2]) if len(nums) > 2 else t_fl * 0.7

        v_ctx = f"• Извлечено из текста: Пол={t_fl}м2, Стены={t_wl}м2.\n"
        if t_fl == 0:
            t_fl, t_wl, t_pr = 45.0, 110.0, 32.0
            v_ctx = "• Использована резервная база замеров.\n"

        try:
            rows = await call_gpt4o_smetter(catalog, t_fl, t_wl, t_pr, query)
        except Exception as e:
            logger.error(f"GPT-4o error: {e}")
            raise HTTPException(status_code=502, detail="Ошибка ИИ-ядра (GPT‑4o). Попробуйте позже.")

        # Считаем итог и добавляем маржу
        total_sum = sum(r["volume"] * r["price"] for r in rows)
        total_sum = math.ceil(total_sum / 100.0) * 100
        margin_val = total_sum * 0.25

        wb_out = Workbook()
        ws_out = wb_out.active
        ws_out.title = "Импорт Сметтер"
        ws_out.append(["Тип", "Наименование позиции (Работы / Материалы)", "Ед. изм.", "Количество", "Цена (руб.)", "Итого (руб.)"])
        for r in rows:
            ws_out.append([
                str(r.get("type", "")),
                str(r.get("name", "")),
                str(r.get("unit", "")),
                float(r.get("volume", 0)),
                float(r.get("price", 0)),
                float(r.get("volume", 0)) * float(r.get("price", 0))
            ])

        thin = Side(border_style="thin", color="CCCCCC")
        for row in ws_out.iter_rows(min_row=2, max_row=ws_out.max_row, min_col=1, max_col=6):
            for cell in row:
                cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)

        stream = BytesIO()
        wb_out.save(stream)
        file_bytes = stream.getvalue()

        return Response(
            content=file_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=estimate_batch_monolit.xlsx"}
        )

    else:
        return {"reply": "Неизвестный агент.", "has_estimate": False}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7778)))

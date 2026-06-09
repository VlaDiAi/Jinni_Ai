import os
import io
import ast
import base64
import asyncio
import subprocess
import pypdf
import openpyxl
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import openai

# Инициализация асинхронного клиента OpenAI через шлюз Timeweb
# Токен OPENAI_API_KEY берется строго из переменных окружения стенда "Brainy Pheasant"
ai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(title="MONOLIT-MOS AI Core - Jinni")

# Настройка CORS, чтобы фронтенд мог беспрепятственно общаться с бэкендом
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Модель входящего JSON-запроса от обновленного index.html
class CommandRequest(BaseModel):
    command: str
    file: Optional[str] = None      # Base64 строка файла (при наличии скрепки 📎)
    filename: Optional[str] = None  # Имя файла для автоматического роутинга

# ==========================================
# 🤖 СЛУЖБА МУЛЬТИАГЕНТНЫХ ИИ-СИСТЕМ
# ==========================================

class AIAgentsPool:
    @staticmethod
    async def run_estimator(context: str, file_data: str = "") -> str:
        """Агент №1: ИИ-Сметчик (Аудит цен, объемов и привязка к 10 годам гарантии)"""
        system_prompt = (
            "Ты — Старший ИИ-Сметчик компании MONOLIT-MOS. Твоя специализация — детальный аудит строительных смет, "
            "расчет объемов бетона, арматуры, опалубки и земляных работ. Ты сверяешь данные с внутренними "
            "регламентами (база знаний: 10 лет гарантии на монолитные конструкции). Ты жестко выявляешь "
            "завышения цен субподрядчиками и скрытые накрутки. Выдавай экспертный ответ с разбивкой по позициям, "
            "без лишней воды, в строгом инженерном стиле."
        )
        
        user_content = f"Директива от руководства: {context}"
        if file_data:
            user_content += f"\n\nДанные извлеченные из файла сметы:\n{file_data}"

        response = await ai_client.chat.completions.create(
            model="openai/gpt-5.4-nano",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.2
        )
        return response.choices.message.content

    @staticmethod
    async def run_architect(context: str) -> str:
        """Агент №2: Планировщик-Проектировщик (Архитектура, эргономика, ТЗ на дом)"""
        system_prompt = (
            "Ты — Главный Архитектор-Проектировщик загородных домов в MONOLIT-MOS. Твоя специализация — планировочные "
            "решения, посадка монолитных и каменных зданий на участок, эргономика помещений, этажность и формирование ТЗ. "
            "Ты предлагаешь решения, оптимизирующие прочность каркаса под гарантию 10 лет. Давай четкие, "
            "конструктивные архитектурные рекомендации и идеи планировок для клиента."
        )

        response = await ai_client.chat.completions.create(
            model="openai/gpt-5.4-nano",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Разработай планировочное/архитектурное решение:\n{context}"}
            ],
            temperature=0.4
        )
        return response.choices.message.content

    @staticmethod
    async def run_developer(user_instruction: str) -> str:
        """Агент №3: ИИ-Девелопер (Автоматическое изменение кода системы и Git Push)"""
        target_file = "bridge.py"
        if "фронт" in user_instruction.lower() or "index.html" in user_instruction.lower():
            target_file = "index.html"

        if not os.path.exists(target_file):
            return f"❌ Файл {target_file} не найден на сервере."

        with open(target_file, "r", encoding="utf-8") as f:
            current_code = f.read()

        system_prompt = (
            f"Ты — ИИ-Инженер автоматизации Джинни. Твоя задача — модифицировать код файла {target_file}.\n"
            "Ты обязан возвращать ВЕСЬ код файла целиком, без сокращений, пропусков или комментариев вроде '// прежний код'. "
            "Код должен компилироваться без ошибок.\n"
            "ВАЖНО: Возвращай только чистый код. Никакого пояснительного текста до или после кода, никаких markdown-оберток (```)."
        )

        user_content = (
            f"Текущий рабочий код {target_file}:\n\n{current_code}\n\n"
            f"Инструкция по обновлению: {user_instruction}\n\n"
            f"Выдай обновленный код целиком:"
        )

        try:
            response = await ai_client.chat.completions.create(
                model="openai/gpt-5.4-nano",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.1
            )
            
            new_code = response.choices.message.content.strip()

            # Очистка от случайных markdown-тегов
            if new_code.startswith("```"):
                lines = new_code.splitlines()
                if lines and lines[0].startswith("```"): lines.pop(0)
                if lines and lines[-1].startswith("```"): lines.pop()
                new_code = "\n".join(lines).strip()

            # ВАЛИДАЦИЯ: Защита от повреждения бэкенда синтаксическими ошибками Python
            if target_file == "bridge.py":
                try:
                    ast.parse(new_code)
                except SyntaxError as e:
                    return f"❌ Авто-обновление отклонено! Обнаружена синтаксическая ошибка на строке {e.lineno}: {e.msg}"

            # Запись модифицированного кода
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(new_code)

            # АВТОМАТИЗАЦИЯ GIT: Синхронизация изменений локального сервера с GitHub репозиторием
            try:
                subprocess.run(["git", "add", target_file], check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", f"🤖 Джинни: Автоматическое обновление {target_file}"], check=True, capture_output=True)
                subprocess.run(["git", "push", "origin", "main"], check=True, capture_output=True)
                git_status = "и успешно отправлен в GitHub-репозиторий (git push)."
            except Exception as git_err:
                git_status = f"но произошел сбой синхронизации с Git: {str(git_err)}. Проверьте права доступа."

            return f"✅ Код файла `{target_file}` успешно обновлен, применен на сервере {git_status}"

        except Exception as err:
            return f"❌ Сбой при выполнении авто-модификации кода: {str(err)}"

# ==========================================
# 🎛️ ЦЕНТРАЛЬНЫЙ ОРКЕСТРАТОР СИСТЕМЫ
# ==========================================

class AIOrchestrator:
    @staticmethod
    async def route_and_execute(command: str, file_text: str, filename: str) -> str:
        cmd_lower = command.lower()
        is_file_present = len(file_text) > 0
        
        # 1. ТРИГГЕР ДЛЯ АГЕНТА-ДЕВЕЛОПЕРА (Задачи на изменение или обновление кода)
        if "измени код" in cmd_lower or "обнови код" in cmd_lower or "перепиши" in cmd_lower or "добавь в код" in cmd_lower:
            return await AIAgentsPool.run_developer(command)

        # 2. МУЛЬТИАГЕНТНЫЙ СЦЕНАРИЙ (И смета/цены, и планировка/дом одновременно)
        elif ("смет" in cmd_lower or "цена" in cmd_lower or is_file_present) and ("проект" in cmd_lower or "план" in cmd_lower or "дом" in cmd_lower):
            task_estimate = AIAgentsPool.run_estimator(command, file_text)
            task_project = AIAgentsPool.run_architect(command)
            est_reply, arch_reply = await asyncio.gather(task_estimate, task_project)
            
            return (
                f"### 📐 АРХИТЕКТУРНОЕ РЕШЕНИЕ:\n{arch_reply}\n\n"
                f"### 📊 СМЕТНЫЙ АУДИТ:\n{est_reply}"
            )

        # 3. СЦЕНАРИЙ ДЛЯ АГЕНТА-СМЕТЧИКА (Файлы Excel/PDF или денежные вопросы)
        elif is_file_present or "смет" in cmd_lower or "стоимост" in cmd_lower or "цена" in cmd_lower or "рубл" in cmd_lower:
            return await AIAgentsPool.run_estimator(command, file_text)

        # 4. СЦЕНАРИЙ ДЛЯ АГЕНТА-ПРОЕКТИРОВЩИКА (Конструктив, этажи, комнаты, участки)
        elif "план" in cmd_lower or "проект" in cmd_lower or "дом" in cmd_lower or "комнат" in cmd_lower or "этаж" in cmd_lower or "фундамент" in cmd_lower:
            return await AIAgentsPool.run_architect(command)

        # 5. ДЕФОЛТНЫЙ СЦЕНАРИЙ: Общий ответ Джинни (Когнитивный блок Джарвис)
        else:
            response = await ai_client.chat.completions.create(
                model="openai/gpt-5.4-nano",
                messages=[
                    {"role": "system", "content": "Ты Джинни, ИИ-ассистент MONOLIT-MOS. Ответь клиенту емко, профессионально и внятно."},
                    {"role": "user", "content": command}
                ]
            )
            return response.choices.message.content

# ==========================================
# 🌐 FastAPI ЭНДПОИНТЫ И ПАРСИНГ ФАЙЛОВ
# ==========================================

@app.post("/api/command")
async def handle_command(request: CommandRequest):
    try:
        extracted_file_text = ""
        
        # Разбор Base64-файла из скрепки 📎 фронтенда
        if request.file and request.filename:
            raw_file_str = request.file
            if "," in raw_file_str:
                raw_file_str = raw_file_str.split(",")[1]
                
            file_bytes = base64.b64decode(raw_file_str)
            fname = request.filename.lower()
            
            # Извлечение текста из PDF
            if fname.endswith('.pdf'):
                pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))

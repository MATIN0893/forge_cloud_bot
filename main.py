import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from groq import Groq
from github import Github

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment variables (no hard‑coded secrets)
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("FORGE_CLOUD_BOT_TOKEN")
GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")

# ---------------------------------------------------------------------------
# External service clients – created lazily when the corresponding token exists
# ---------------------------------------------------------------------------
groq_client: Optional[Groq] = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
github_client: Optional[Github] = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None

# ---------------------------------------------------------------------------
# Telegram command handlers
# ---------------------------------------------------------------------------
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report service status, Groq model connection and GitHub connectivity."""
    gh_status = "Подключен" if github_client else "Отключен (нет токена)"
    groq_status = (
        "Подключен (llama-3.1-8b-instant)" if groq_client else "Отключен"
    )
    text = (
        "⚒️ **MATIN FORGE CLOUD В СТРОЮ!**\n\n"
        f"• 🌐 Хост: FastAPI (async)\n"
        f"• 🧠 Модель: {groq_status}\n"
        f"• 🐙 GitHub: {gh_status}\n"
        "• ⚡️ Статус: Активен\n"
        "• 📦 Команды: /repos, /ask <вопрос>"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def repos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return first 10 repositories of the authenticated GitHub user."""
    if not github_client:
        await update.message.reply_text(
            "❌ Ошибка: GITHUB_TOKEN не задан в переменных окружения."
        )
        return
    try:
        user = github_client.get_user()
        repos = [f"• {repo.name}" for repo in user.get_repos()[:10]]
        if not repos:
            reply = "📦 У вас нет публичных репозиториев."
        else:
            reply = "📦 **Твои репозитории на GitHub:**\n" + "\n".join(repos)
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception as exc:
        logger.exception("Error while fetching GitHub repos")
        await update.message.reply_text(f"❌ Ошибка получения репозиториев: {exc}")

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a prompt to Groq Llama‑3.1‑8b‑instant model and return the answer."""
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("ℹ️ Использование: /ask <твой запрос>")
        return
    if not groq_client:
        await update.message.reply_text("❌ Ошибка: GROQ_API_KEY не задан.")
        return
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты MATIN FORGE CLOUD — облачный инженер системы MATIN BRAIN CORE. "
                        "Отвечай кратко и строго по делу."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        answer = completion.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as exc:
        logger.exception("Error while calling Groq API")
        await update.message.reply_text(f"❌ Ошибка генерации: {exc}")

# ---------------------------------------------------------------------------
# FastAPI application with lifespan that starts/stops the Telegram bot
# ---------------------------------------------------------------------------
app = FastAPI()

tg_app: Optional[Application] = None

@asynccontextmanager
async def lifespan(_: FastAPI):
    global tg_app
    if TELEGRAM_BOT_TOKEN:
        request_config = HTTPXRequest(
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=30.0,
        )
        tg_app = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .request(request_config)
            .build()
        )
        tg_app.add_handler(CommandHandler("status", status_cmd))
        tg_app.add_handler(CommandHandler("repos", repos_cmd))
        tg_app.add_handler(CommandHandler("ask", ask_cmd))

        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        logger.info("⚒️ Telegram бот запущен внутри FastAPI")
    else:
        logger.warning("⚠️ Токен бота не найден в переменных окружения (FORGE_CLOUD_BOT_TOKEN)")

    yield

    if tg_app:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        logger.info("🛑 Telegram бот корректно остановлен")

app.router.lifespan_context = lifespan

# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------
@app.get("/")
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "MATIN FORGE CLOUD"}

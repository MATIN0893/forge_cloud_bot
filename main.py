import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
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
# Environment variables (no secrets in code)
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
PORT = int(os.getenv("PORT", "8080"))

# ---------------------------------------------------------------------------
# External service clients (initialized only if keys are present)
# ---------------------------------------------------------------------------
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
github_client = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None

# ---------------------------------------------------------------------------
# Bot command handlers
# ---------------------------------------------------------------------------
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    gh_status = "Подключен" if github_client else "Отключен (нет токена)"
    groq_status = (
        "Подключен (llama-3.1-8b-instant)" if groq_client else "Отключен"
    )
    text = (
        "⚒️ **MATIN FORGE CLOUD В СТРОЮ!**\n\n"
        f"• 🌐 Хост: Render (24/7 Web Server)\n"
        f"• 🧠 Модель: {groq_status}\n"
        f"• 🐙 GitHub: {gh_status}\n"
        "• ⚡️ Статус: Активен, защита от сбоев включена\n"
        "• 📦 Команды: /repos, /ask <вопрос>, /status"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def repos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not github_client:
        await update.message.reply_text(
            "❌ Ошибка: GITHUB_TOKEN не задан в переменных окружения."
        )
        return
    try:
        user = github_client.get_user()
        repos = [f"• {repo.name}" for repo in user.get_repos()[:10]]
        if not repos:
            repos_text = "_Нет публичных репозиториев_"
        else:
            repos_text = "\n".join(repos)
        await update.message.reply_text(
            f"📦 **Твои репозитории на GitHub:**\n{repos_text}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:
        logger.exception("Failed to fetch GitHub repositories")
        await update.message.reply_text(f"❌ Ошибка получения репозиториев: {exc}")

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
                        "Ты MATIN FORGE CLOUD — облачный архитектор и инженер системы MATIN BRAIN CORE. "
                        "Отвечай технически точно и лаконично."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        answer = completion.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as exc:
        logger.exception("Groq generation failed")
        await update.message.reply_text(f"❌ Ошибка генерации: {exc}")

# ---------------------------------------------------------------------------
# aiohttp web server (для Render keep‑alive)
# ---------------------------------------------------------------------------
async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK - MATIN FORGE CLOUD ALIVE", status=200)

async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    logger.info(f"Web server started on port {PORT}")
    return runner

# ---------------------------------------------------------------------------
# Bot initialization and run logic
# ---------------------------------------------------------------------------
async def run_bot() -> None:
    # HTTPX request configuration for Telegram API
    request_config = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request_config)
        .build()
    )

    # Register command handlers
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("repos", repos_cmd))
    application.add_handler(CommandHandler("ask", ask_cmd))

    # Run the bot (polling mode). This coroutine returns only when stopped.
    await application.run_polling(drop_pending_updates=True)

# ---------------------------------------------------------------------------
# Main entry point with auto‑restart
# ---------------------------------------------------------------------------
async def main() -> None:
    while True:
        runner: web.AppRunner | None = None
        try:
            runner = await start_web_server()
            await run_bot()
        except Exception as exc:
            logger.exception("Unexpected error in bot runtime, restarting in 5 seconds")
            await asyncio.sleep(5)
        finally:
            if runner:
                await runner.cleanup()
                logger.info("Web server stopped")
            # Small pause before next restart attempt to avoid tight loop
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")

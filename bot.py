import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, ContextTypes
from database import Task, get_session
from datetime import time, datetime
import pytz  # Para zonas horarias
from sqlalchemy import func
from flask import Flask, jsonify, request
import asyncio

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
PORT = int(os.environ.get("PORT", 10000))

appWeb = Flask(__name__)

# Configuración del bot
bot_app = ApplicationBuilder().token(TOKEN).build()

# Handlers de comandos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra un mensaje de bienvenida con los comandos disponibles"""
    mensaje = """📝 ¡Hola! Soy tu bot de tareas. Comandos disponibles:
    
            /add [tarea] [fecha] - Añadir tarea (ej: /add Comprar leche 25/12/2024)
            /list - Ver todas las tareas
            /delete [número] - Eliminar una tarea
            /vencimiento [fecha] - Filtrar tareas por fecha
            /start_daily - Activar recordatorios diarios
    """
    await update.message.reply_text(mensaje)
    
    """ await update.message.reply_text(
        "🎮 **Menú Principal**\nElige una acción:",
        reply_markup=reply_markup
    ) """

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los clics en los botones inline."""
    query = update.callback_query
    await query.answer()  # Elimina el estado de "cargando" en el cliente
    
    if query.data == "add_task":
        await query.edit_message_text("📝 Escribe la tarea que quieres añadir (ej: /add Regar las plantas 25/03/2025)")
    
    elif query.data == "list_tasks":
        with get_session() as session:
            tasks = session.query(Task).filter(Task.chat_id == query.message.chat_id).all()
            
            if not tasks:
                await query.edit_message_text("🎉 ¡No hay tareas pendientes!")
                return
            
            response = "📋 **Tareas Pendientes:**\n"
            keyboard = []
            for task in tasks:
                response += f"- {task.task}"
                if task.due_date:
                    response += f" (📅 {task.due_date.strftime('%d/%m/%Y')})\n"
                else:
                    response += "\n"
                # Botón para eliminar cada tarea
                keyboard.append([InlineKeyboardButton(
                    f"❌ Eliminar '{task.task[:10]}...'",
                    callback_data=f"delete_{task.id}"
                )])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(response, reply_markup=reply_markup)
    
    elif query.data.startswith("delete_"):
        task_id = int(query.data.split("_")[1])
        with get_session() as session:
            task = session.query(Task).get(task_id)
            if task:
                session.delete(task)
                await query.edit_message_text(f"🗑️ Tarea eliminada: {task.task}")
            else:
                await query.edit_message_text("❌ La tarea ya no existe.")


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as session:
        chat_id = update.message.chat_id
        args = context.args

        if len(args) < 1:
            await update.message.reply_text("❌ Formato: /add <tarea> [DD/MM/AAAA]")
            return

        # Intentar extraer fecha (último elemento del mensaje)
        try:
            # Probar formatos DD/MM/AAAA o DD-MM-AAAA
            due_date_str = args[-1]
            due_date = None
            
            for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
                try:
                    due_date = datetime.strptime(due_date_str, fmt).date()
                    task_text = " ".join(args[:-1])  # Separar tarea y fecha
                    break
                except ValueError:
                    continue
            
            if not due_date:
                raise ValueError("Formato inválido")
                
        except (ValueError, IndexError):
            task_text = " ".join(args)
            due_date = None

        if due_date and due_date < datetime.now().date():
            await update.message.reply_text(f"❌ La fecha {due_date.strftime('%d/%m/%Y')} ya pasó.")
            return

        new_task = Task(
            chat_id=chat_id,
            task=task_text,
            due_date=due_date
        )
        
        session.add(new_task)
        session.commit()
        
        # Mensaje en español con fecha formateada
        fecha_formateada = due_date.strftime("%d/%m/%Y") if due_date else ""
        respuesta = f"✅ Tarea añadida: {task_text}"
        if fecha_formateada:
            respuesta += f"\n📅 Fecha límite: {fecha_formateada}"
        
        await update.message.reply_text(respuesta)

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as session:
        chat_id = update.message.chat_id
        tasks = session.query(Task).filter(Task.chat_id == chat_id).all()
        
        if not tasks:
            await update.message.reply_text("🎉 ¡No hay tareas pendientes!")
            return
        
        response = "📋 **Tareas pendientes:**\n"
        today = datetime.now().date()
        
        for i, task in enumerate(tasks, 1):
            line = f"{i}. {task.task}"
            
            # Manejo seguro de fechas nulas
            if task.due_date is not None:
                fecha_str = task.due_date.strftime("%d/%m/%Y")
                status = ""
                
                if task.due_date.date() < today:
                    status = " (❗ VENCIDA)"
                elif task.due_date.date() == today:
                    status = " (⚠️ HOY)"
                elif (task.due_date.date() - today).days <= 3:
                    dias = (task.due_date.date() - today).days
                    status = f" (⏳ {dias} día{'s' if dias > 1 else ''})"
                
                line += f" | 📅 {fecha_str}{status}"
            
            response += line + "\n"
        
        await update.message.reply_text(response)

async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as session:
        chat_id = update.message.chat_id
        
        try:
            task_num = int(context.args[0]) - 1
        except (IndexError, ValueError):
            await update.message.reply_text("❌ Usa: /delete [número]")
            return
        
        tasks = session.query(Task).filter(Task.chat_id == chat_id).all()
        
        if 0 <= task_num < len(tasks):
            task_to_delete = tasks[task_num]
            session.delete(task_to_delete)
            session.commit()
            await update.message.reply_text(f"🗑️ Tarea eliminada: {task_to_delete.task}")
        else:
            await update.message.reply_text("❌ Número inválido.")

async def filter_due(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as session:
        chat_id = update.message.chat_id
        args = context.args
        
        if len(args) != 1:
            await update.message.reply_text("❌ Formato: /vencimiento DD/MM/AAAA")
            return
        
        try:
            # Probar formatos DD/MM/AAAA y DD-MM-AAAA
            for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
                try:
                    filter_date = datetime.strptime(args[0], fmt).date()
                    break
                except ValueError:
                    continue
            else:
                raise ValueError("Formato inválido")
                
        except ValueError:
            await update.message.reply_text("❌ Fecha inválida. Usa DD/MM/AAAA.")
            return
        
        tasks = session.query(Task).filter(
            Task.chat_id == chat_id,
            func.date(Task.due_date) == filter_date
        ).all()
        
        fecha_formateada = filter_date.strftime("%d/%m/%Y")
        
        if not tasks:
            await update.message.reply_text(f"🎉 ¡No hay tareas para el {fecha_formateada}!")
            return
        
        response = f"📅 **Tareas para el {fecha_formateada}:**\n"
        for i, task in enumerate(tasks, 1):
            response += f"{i}. {task.task}\n"
        
        await update.message.reply_text(response)

async def notify_due_tasks(context: CallbackContext):
    with get_session() as session:
        today = datetime.now().date()
        tasks = session.query(Task).filter(Task.due_date == today).all()
        
        for task in tasks:
            fecha_str = task.due_date.strftime("%d/%m/%Y")
            await context.bot.send_message(
                chat_id=task.chat_id,
                text=f"⚠️ ¡Hoy ({fecha_str}) vence: *{task.task}*!",
                parse_mode="Markdown"
            )

# Función que se ejecutará diariamente
async def daily_task(context: ContextTypes.DEFAULT_TYPE):
    mensaje = "☀️ ¡Buenos días! Es hora de revisar tus tareas pendientes."
    await context.bot.send_message(
        chat_id=context.job.chat_id,  # CHAT_ID guardado al crear el job
        text=mensaje
    )

# Comando para activar la programación
async def start_daily_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # Programar tarea diaria a las 08:00 (hora local)
    job = context.job_queue.run_daily(
        daily_task,
        time=time(hour=8, minute=0, tzinfo=pytz.timezone("Europe/Madrid")),
        days=(0, 1, 2, 3, 4, 5, 6),  # Todos los días
        chat_id=chat_id  # Guardar chat_id en el job
    )
    
    await update.message.reply_text(f"⏰ Recordatorio diario activado (ID: {job.name})")

async def setup_webhook(app: ApplicationBuilder):
    await app.bot.set_webhook(
        url="https://task-ninja-bot.onrender.com",  # URL pública de tu servicio en Render
        #secret_token="TU_SECRETO"  # Opcional: token de seguridad
    )

async def setup_handlers():
    # Registrar comandos
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("add", add_task))
    bot_app.add_handler(CommandHandler("list", list_tasks))
    bot_app.add_handler(CommandHandler("delete", delete_task))
    bot_app.add_handler(CommandHandler("vencimiento", filter_due)) 
    #Iniciar jobs
    bot_app.add_handler(CommandHandler("start_daily", start_daily_task))
    # app.add_handler(CallbackQueryHandler(button_click))  # Maneja los botones inline

    
    print("🤖 Bot activado...")

    #Añadir jobs
    """ tz=pytz.timezone("Europe/Madrid")
    hora_programada = time(hour=12, minute=0, tzinfo=tz)
    app.job_queue.run_daily(notify_due_tasks, time=hora_programada) """

    # app.run_polling()
    
    # Configurar webhook al iniciar
    """ await app.run_webhook(
        listen="0.0.0.0",  # Escuchar en todas las interfaces
        port=PORT,
        #secret_token="TU_SECRETO",
        webhook_url="https://task-ninja-bot.onrender.com"
    ) """

########################
#Servidor web con Flask#
########################

# Endpoint de health
@appWeb.route("/health")
def health():
    return jsonify({"status": "OK"}), 200

# Ruta para webhook de Telegram
@appWeb.route('/webhook', methods=['POST'])
async def webhook():
    update = Update.de_json(await request.get_json(), bot_app.bot)
    await bot_app.process_update(update)
    return 'OK', 200

async def setup_webhook():
    await bot_app.bot.set_webhook(
        url=f"https://task-ninja-bot.onrender.com/webhook",
        #secret_token='TU_SECRETO'
    )

def run_server():
    setup_handlers()
    
    # Configurar webhook asincrónicamente
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_webhook())
    
    # Iniciar servidor Flask
    print("🌐 Servidor Flask iniciado...")
    appWeb.run(host='0.0.0.0', port=PORT, use_reloader=False)

if __name__ == '__main__':
    run_server()
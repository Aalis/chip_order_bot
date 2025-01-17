import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

from bot.handlers.auth_handlers import check_auth
from bot.handlers.order_handlers import (
    command_new_order, handle_name, handle_location,
    handle_product_selection, handle_quantity
)
from bot.handlers.stats_handlers import command_stats
from bot.utils.constants import NAME, LOCATION, PRODUCT_SELECTION, QUANTITY, EMOJIS
from bot.database.database import db

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
        
    # Set up menu commands
    commands = [
        ('start', 'Start the bot'),
        ('new_order', 'Add a new order'),
        ('stats', 'Download statistics')
    ]
    await context.bot.set_my_commands(commands)
        
    keyboard = [
        [InlineKeyboardButton("➕ Add New Order", callback_data='new_order')],
        [InlineKeyboardButton("📊 Download Statistics", callback_data='export_orders')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f'{EMOJIS["WAVE"]} Welcome to the Order Management Bot!\n'
        f'{EMOJIS["ARROW"]} What would you like to do?',
        reply_markup=reply_markup
    )

def main() -> None:
    # Create application
    application = Application.builder().token(os.getenv('BOT_TOKEN')).build()

    # Add conversation handler for order flow
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('new_order', command_new_order),
            CallbackQueryHandler(command_new_order, pattern='^new_order$')
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            LOCATION: [CallbackQueryHandler(handle_location, pattern='^[^:]+$')],
            PRODUCT_SELECTION: [CallbackQueryHandler(handle_product_selection, pattern='^(input_quantity:[0-9]+|confirm_order)$')],
            QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quantity)]
        },
        fallbacks=[
            CommandHandler('start', start),
            CallbackQueryHandler(command_new_order, pattern='^new_order$')  # Allow new_order at any time
        ],
        allow_reentry=True,  # Allow conversation to be restarted
        per_chat=True  # Create separate conversation for each chat
    )

    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stats', command_stats))
    application.add_handler(CallbackQueryHandler(command_stats, pattern='^export_orders$'))
    application.add_handler(conv_handler)

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 
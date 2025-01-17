import io
import csv
import time
import logging
from telegram import Update
from telegram.ext import ContextTypes
from ..utils.constants import EMOJIS
from ..database.database import db

logger = logging.getLogger(__name__)

async def command_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .auth_handlers import check_auth
    if not await check_auth(update):
        return
    
    try:
        # Get statistics using Database class
        rows, total_quantity, total_revenue, total_cost, total_profit = db.get_statistics()
        
        if not rows:
            await update.message.reply_text(f"{EMOJIS['ERROR']} No orders found.")
            return
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Product Name',
            'Total Quantity',
            'Total Revenue (₴)',
            'Total Cost (₴)',
            'Profit (₴)'
        ])
        writer.writerows(rows)
        
        # Add totals row
        writer.writerow([''])  # Empty row for spacing
        writer.writerow([
            'TOTAL',
            total_quantity,
            f'{total_revenue:.2f}',
            f'{total_cost:.2f}',
            f'{total_profit:.2f}'
        ])
        
        # Convert to bytes
        output.seek(0)
        bytes_output = output.getvalue().encode()
        
        # Send file
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(bytes_output),
            filename=f'orders_statistics_{int(time.time())}.csv',
            caption=(
                f'Statistics Summary:\n'
                f'{EMOJIS["MONEY"]} Total Revenue: ₴{total_revenue:.2f}\n'
                f'{EMOJIS["SHOPPING"]} Total Cost: ₴{total_cost:.2f}\n'
                f'{EMOJIS["STATS"]} Total Profit: ₴{total_profit:.2f}'
            )
        )
        
    except Exception as e:
        logger.error(f"Error exporting orders: {e}")
        await update.message.reply_text(
            f"{EMOJIS['ERROR']} Sorry, there was an error downloading statistics."
        ) 
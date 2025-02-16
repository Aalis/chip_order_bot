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
        rows, total_quantity, total_revenue, total_cost, total_profit, recent_orders = db.get_statistics()
        
        if not rows:
            await update.message.reply_text(f"{EMOJIS['ERROR']} No orders found.")
            return
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write product statistics
        writer.writerow([
            'Product Statistics',
            '', '', '', ''  # Empty columns for alignment
        ])
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
        
        # Add recent orders section
        writer.writerow([''])  # Empty row for spacing
        writer.writerow([''])  # Empty row for spacing
        writer.writerow([
            'Recent Orders',
            '', '', '', ''  # Empty columns for alignment
        ])
        writer.writerow([
            'Client Name',
            'Location',
            'Product',
            'Quantity',
            'Total Price (₴)',
            'Date'
        ])
        for order in recent_orders:
            writer.writerow([
                order[0],  # client_name
                order[1],  # location
                order[2],  # product_name
                order[3],  # quantity
                f'{order[4]:.2f}',  # total_price
                order[5].strftime('%Y-%m-%d')  # created_at
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
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
import psycopg
from psycopg import Error
import csv
import io
import time

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
NAME, LOCATION, PRODUCT_SELECTION, QUANTITY = range(4)

EMOJIS = {
    'CART': '🛒',
    'MONEY': '💰',
    'PRODUCT': '💠',
    'CONFIRM': '✅',
    'WARNING': '⚠️',
    'ERROR': '❌',
    'PERSON': '👤',
    'LOCATION': '📍',
    'SHOPPING': '🛍️',
    'PACKAGE': '📦',
    'ARROW': '🔽',
    'WAVE': '👋',
    'PLUS': '➕',
    'STATS': '📊'
}

BUILDINGS = {
    '4Seasons': '🏢',
    'Omega': '🏬',
    'Kamanina': '🏘️',
    'Genuez': '🏡'
}

@dataclass
class Product:
    id: int
    name: str
    price: float

@dataclass
class CartItem:
    name: str
    price: float
    quantity: int

class Database:
    def __init__(self):
        self.DATABASE_URL = os.getenv('DATABASE_URL')
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is not set")

    def get_connection(self) -> psycopg.Connection:
        return psycopg.connect(
            self.DATABASE_URL,
            connect_timeout=30,
            application_name='chip_order_bot'
        )

    def get_products(self) -> List[Product]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, price FROM products ORDER BY name")
                return [Product(id=id, name=name, price=price) for id, name, price in cur.fetchall()]

    def save_order(self, client_name: str, username: Optional[str], location: str, cart: Dict[str, CartItem]) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Save client info
                cur.execute(
                    "INSERT INTO clients (name, username, location) VALUES (%s, %s, %s) RETURNING id",
                    (client_name, username, location)
                )
                client_id = cur.fetchone()[0]
                
                # Save each order
                for product_id, item in cart.items():
                    cur.execute(
                        "INSERT INTO orders (client_id, product_id, quantity, total_price) VALUES (%s, %s, %s, %s)",
                        (client_id, int(product_id), item.quantity, item.quantity * item.price)
                    )
                conn.commit()

    def get_statistics(self) -> Tuple[List[Tuple], float, float, float, float]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        p.name as product_name,
                        SUM(o.quantity) as total_quantity,
                        SUM(o.total_price) as total_revenue,
                        p.orig_price * SUM(o.quantity) as total_cost,
                        SUM(o.total_price) - (p.orig_price * SUM(o.quantity)) as profit
                    FROM orders o
                    JOIN products p ON o.product_id = p.id
                    GROUP BY p.name, p.orig_price
                    ORDER BY profit DESC
                """)
                rows = cur.fetchall()
                
                if not rows:
                    return [], 0, 0, 0, 0
                
                total_quantity = sum(row[1] for row in rows)
                total_revenue = sum(row[2] for row in rows)
                total_cost = sum(row[3] for row in rows)
                total_profit = sum(row[4] for row in rows)
                
                return rows, total_quantity, total_revenue, total_cost, total_profit

# Initialize database
db = Database()

def create_product_keyboard(products: List[Product], show_confirm: bool = False) -> InlineKeyboardMarkup:
    """Create a keyboard with product buttons and optional confirm button."""
    keyboard = [
        [InlineKeyboardButton(
            f"{EMOJIS['PRODUCT']} {product.name} - ₴{product.price}",
            callback_data=f'input_quantity:{product.id}'
        )]
        for product in products
    ]
    
    if show_confirm:
        keyboard.append([
            InlineKeyboardButton(f"{EMOJIS['CONFIRM']} Confirm Order", callback_data='confirm_order')
        ])
    
    return InlineKeyboardMarkup(keyboard)

def format_cart_text(cart: Dict[str, CartItem]) -> Tuple[str, float]:
    """Format cart contents and calculate total."""
    total = 0
    cart_lines = []
    
    for item in cart.values():
        subtotal = item.quantity * item.price
        total += subtotal
        cart_lines.append(f"• {item.name}: {item.quantity} × ₴{item.price} = ₴{subtotal}")
    
    cart_text = f"{EMOJIS['CART']} Cart:\n" + "\n".join(cart_lines)
    cart_text += f"\n\n{EMOJIS['MONEY']} Total: ₴{total:.2f}"
    cart_text += f"\n\n{EMOJIS['ARROW']} Select more products or confirm order:"
    
    return cart_text, total

# Add authorized users list
AUTHORIZED_USERS_IDS = set()
AUTHORIZED_USERS_USERNAMES = set()

for user in os.getenv('AUTHORIZED_USERS', '').split(','):
    user = user.strip()
    if user.startswith('@'):
        AUTHORIZED_USERS_USERNAMES.add(user.lower())
    elif user.isdigit():
        AUTHORIZED_USERS_IDS.add(int(user))

async def check_auth(update: Update) -> bool:
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if user_id in AUTHORIZED_USERS_IDS:
        return True
    
    if username and f"@{username.lower()}" in AUTHORIZED_USERS_USERNAMES:
        return True
        
    await update.message.reply_text("Sorry, you are not authorized to use this bot.")
    return False

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
        '👋 Welcome to the Order Management Bot!\n'
        '🔽 What would you like to do?',
        reply_markup=reply_markup
    )

async def command_new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
    # Clear any existing conversation data
    context.user_data.clear()
    
    await update.message.reply_text("👤 Please enter the customer name:")
    return NAME

async def command_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        await update.message.reply_document(
            document=io.BytesIO(bytes_output),
            filename='statistics.csv',
            caption=(
                f'Statistics Summary:\n'
                f'{EMOJIS["MONEY"]} Total Revenue: ₴{total_revenue:.2f}\n'
                f'{EMOJIS["SHOPPING"]} Total Cost: ₴{total_cost:.2f}\n'
                f'{EMOJIS["STATS"]} Total Profit: ₴{total_profit:.2f}'
            )
        )
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text(f"{EMOJIS['ERROR']} Sorry, there was an error downloading statistics. Please try again.")

async def new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
    # Clear any existing conversation data
    context.user_data.clear()
    
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("👤 Please enter the customer name:")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
    # Parse name and optional username
    text = update.message.text
    if '@' in text:
        name, username = text.split('@', 1)
        context.user_data['name'] = name.strip()
        # Add @ if not already present
        username = username.strip()
        context.user_data['username'] = f"@{username}" if not username.startswith('@') else username
    else:
        context.user_data['name'] = text.strip()
        context.user_data['username'] = None
    
    # Create location selection keyboard with apartment emojis
    keyboard = [
        [InlineKeyboardButton("🏢 4Seasons", callback_data='location:4Seasons')],
        [InlineKeyboardButton("🏬 Omega", callback_data='location:Omega')],
        [InlineKeyboardButton("🏘️ Kamanina", callback_data='location:Kamanina')],
        [InlineKeyboardButton("🏡 Genuez", callback_data='location:Genuez')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📍 Select customer location:", reply_markup=reply_markup)
    return LOCATION

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_auth(update):
        return ConversationHandler.END
    
    query = update.callback_query
    await query.answer()
    
    location = query.data.split(':')[1]
    context.user_data['location'] = location
    
    try:
        products = db.get_products()
        
        if not products:
            await query.message.reply_text(f"{EMOJIS['ERROR']} No products available.")
            return ConversationHandler.END
        
        keyboard = create_product_keyboard(products)
        await query.message.reply_text(
            f"{EMOJIS['SHOPPING']} Select products to add to cart:",
            reply_markup=keyboard
        )
        
        # Initialize cart in context
        context.user_data['cart'] = {}
        context.user_data['products'] = {
            str(p.id): {'name': p.name, 'price': p.price}
            for p in products
        }
        
        return PRODUCT_SELECTION
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await query.message.reply_text(f"{EMOJIS['ERROR']} Sorry, there was an error. Please try again.")
        return ConversationHandler.END

async def handle_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_auth(update):
        return ConversationHandler.END
    
    query = update.callback_query
    if query:
        await query.answer()
        
        if query.data.startswith('input_quantity:'):
            product_id = query.data.split(':')[1]
            product = context.user_data['products'][product_id]
            context.user_data['current_product'] = product_id
            
            await query.message.reply_text(
                f"{EMOJIS['PACKAGE']} Enter quantity for {product['name']} (₴{product['price']}):"
            )
            return PRODUCT_SELECTION
            
        elif query.data == 'confirm_order':
            cart = context.user_data.get('cart', {})
            if not cart:
                await query.message.reply_text(f"{EMOJIS['WARNING']} Please add at least one product to cart.")
                return PRODUCT_SELECTION
            
            return await process_order(update, context)
    
    else:  # Text message with quantity
        try:
            quantity = int(update.message.text)
            if quantity <= 0:
                await update.message.reply_text(f"{EMOJIS['WARNING']} Please enter a positive number.")
                return PRODUCT_SELECTION
            
            product_id = context.user_data.get('current_product')
            if not product_id:
                await update.message.reply_text(f"{EMOJIS['WARNING']} Please select a product first.")
                return PRODUCT_SELECTION
            
            product = context.user_data['products'][product_id]
            context.user_data['cart'][product_id] = CartItem(
                name=product['name'],
                price=product['price'],
                quantity=quantity
            )
            
            cart_text, _ = format_cart_text(context.user_data['cart'])
            keyboard = create_product_keyboard(
                [Product(id=int(pid), **p) for pid, p in context.user_data['products'].items()],
                show_confirm=True
            )
            
            await update.message.reply_text(cart_text, reply_markup=keyboard)
            return PRODUCT_SELECTION
            
        except ValueError:
            await update.message.reply_text(f"{EMOJIS['WARNING']} Please enter a valid number.")
            return PRODUCT_SELECTION

async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    cart = context.user_data['cart']
    
    try:
        # Use the Database class to save the order
        db.save_order(
            client_name=context.user_data['name'],
            username=context.user_data.get('username'),
            location=context.user_data['location'],
            cart=cart
        )
        
        # Format confirmation message
        cart_text, total_price = format_cart_text(cart)
        confirmation = (
            f"{EMOJIS['CONFIRM']} Order confirmed!\n\n"
            f"{EMOJIS['PERSON']} Customer: {context.user_data['name']}\n"
            f"{EMOJIS['LOCATION']} Location: {context.user_data['location']}\n\n"
            f"{EMOJIS['SHOPPING']} Products:\n"
        )
        
        # Add cart items
        for item in cart.values():
            subtotal = item.quantity * item.price
            confirmation += f"• {item.name}: {item.quantity} × ₴{item.price} = ₴{subtotal}\n"
        confirmation += f"\n{EMOJIS['MONEY']} Total Price: ₴{total_price:.2f}"
        
        await query.message.reply_text(confirmation)
        
        # Clear user data and show main menu
        context.user_data.clear()
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['PLUS']} Add New Order", callback_data='new_order')],
            [InlineKeyboardButton(f"{EMOJIS['STATS']} Download Statistics", callback_data='export_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(f"{EMOJIS['ARROW']} What would you like to do next?", reply_markup=reply_markup)
        return ConversationHandler.END
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await query.message.reply_text(f"{EMOJIS['ERROR']} Sorry, there was an error saving your order. Please try again.")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
    context.user_data.clear()
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def export_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update):
        return
    
    query = update.callback_query
    await query.answer()
    
    try:
        # Get statistics using Database class
        rows, total_quantity, total_revenue, total_cost, total_profit = db.get_statistics()
        
        if not rows:
            await query.message.reply_text(f"{EMOJIS['ERROR']} No orders found.")
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
        await query.message.reply_document(
            document=io.BytesIO(bytes_output),
            filename='statistics.csv',
            caption=(
                f'Statistics Summary:\n'
                f'{EMOJIS["MONEY"]} Total Revenue: ₴{total_revenue:.2f}\n'
                f'{EMOJIS["SHOPPING"]} Total Cost: ₴{total_cost:.2f}\n'
                f'{EMOJIS["STATS"]} Total Profit: ₴{total_profit:.2f}'
            )
        )
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await query.message.reply_text(f"{EMOJIS['ERROR']} Sorry, there was an error downloading statistics. Please try again.")

def main():
    # Initialize the Application with the bot token
    application = Application.builder().token(os.getenv('BOT_TOKEN')).build()

    # Add handlers in the correct order
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", command_stats))
    
    # Add export_orders handler before conversation handler
    application.add_handler(CallbackQueryHandler(export_orders, pattern='^export_orders$'))
    
    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('new_order', command_new_order),
            CallbackQueryHandler(new_order, pattern='^new_order$')
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            LOCATION: [CallbackQueryHandler(get_location, pattern='^location:')],
            PRODUCT_SELECTION: [
                CallbackQueryHandler(handle_product_selection, pattern='^(input_quantity:|confirm_order)'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_product_selection)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('start', start)
        ],
        allow_reentry=True
    )

    # Add conversation handler
    application.add_handler(conv_handler)

    # Start the bot
    print("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 
import os
import logging
from datetime import datetime
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

# States for conversation
NAME, LOCATION, PRODUCT_SELECTION, QUANTITY = range(4)

# Add authorized users list
AUTHORIZED_USERS_IDS = set()
AUTHORIZED_USERS_USERNAMES = set()

for user in os.getenv('AUTHORIZED_USERS', '').split(','):
    user = user.strip()
    if user.startswith('@'):
        AUTHORIZED_USERS_USERNAMES.add(user.lower())
    elif user.isdigit():
        AUTHORIZED_USERS_IDS.add(int(user))

# Database connection function
def get_db_connection():
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is not set")
        
        conn = psycopg.connect(
            DATABASE_URL,
            connect_timeout=30,
            application_name='chip_order_bot'
        )
        return conn
    except psycopg.Error as e:
        logger.error(f"Database connection error: {e}")
        raise e

# Initialize database tables
def init_db():
    retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(retries):
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                # Create clients table if not exists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS clients (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        username VARCHAR(100),
                        location VARCHAR(50) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create products table if not exists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS products (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        type VARCHAR(50) NOT NULL,
                        price DECIMAL(10,2) NOT NULL,
                        orig_price DECIMAL(10,2) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create orders table if not exists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        product_id INTEGER REFERENCES products(id),
                        quantity INTEGER NOT NULL,
                        total_price DECIMAL(10,2) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.commit()
            conn.close()
            logger.info("Database initialized successfully")
            return
        except psycopg.Error as e:
            logger.error(f"Database initialization error (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(retry_delay)
            else:
                raise e

# Initialize database on startup
try:
    init_db()
    logger.info("Database initialization completed")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    # Continue running the bot even if database init fails

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
    
    await update.message.reply_text("👤 Please enter the customer name:")
    return NAME

async def command_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    
    # Reuse the export_orders logic but for command
    try:
        conn = get_db_connection()
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
        conn.close()
        
        if not rows:
            await update.message.reply_text("No orders found.")
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
        
        # Calculate totals
        total_quantity = sum(row[1] for row in rows)
        total_revenue = sum(row[2] for row in rows)
        total_cost = sum(row[3] for row in rows)
        total_profit = sum(row[4] for row in rows)
        
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
            caption=f'Statistics Summary:\nTotal Revenue: ₴{total_revenue:.2f}\nTotal Cost: ₴{total_cost:.2f}\nTotal Profit: ₴{total_profit:.2f}'
        )
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text("Sorry, there was an error downloading statistics. Please try again.")

async def new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
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

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
    query = update.callback_query
    await query.answer()
    
    location = query.data.split(':')[1]
    context.user_data['location'] = location
    
    # Get products from database
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, price FROM products ORDER BY name")
            products = cur.fetchall()
        conn.close()
        
        if not products:
            await query.message.reply_text("❌ No products available.")
            return ConversationHandler.END
        
        # Create keyboard with product buttons - one per row
        keyboard = []
        for id, name, price in products:
            keyboard.append([
                InlineKeyboardButton(
                    f"💠 {name} - ₴{price}",
                    callback_data=f'input_quantity:{id}'
                )
            ])
        
        # Add confirm button at the bottom
        keyboard.append([
            InlineKeyboardButton("✅ Confirm Order", callback_data='confirm_order')
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(
            "🛍️ Select products to add to cart:",
            reply_markup=reply_markup
        )
        
        # Initialize cart in context
        context.user_data['cart'] = {}
        context.user_data['products'] = {
            str(id): {'name': name, 'price': price}
            for id, name, price in products
        }
        
        return PRODUCT_SELECTION
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await query.message.reply_text("❌ Sorry, there was an error. Please try again.")
        return ConversationHandler.END

async def handle_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                f"📦 Enter quantity for {product['name']} (₴{product['price']}):"
            )
            return PRODUCT_SELECTION
            
        elif query.data == 'confirm_order':
            cart = context.user_data.get('cart', {})
            if not cart:
                await query.message.reply_text("⚠️ Please add at least one product to cart.")
                return PRODUCT_SELECTION
            
            return await process_order(update, context)
    
    else:  # Text message with quantity
        try:
            quantity = int(update.message.text)
            if quantity <= 0:
                await update.message.reply_text("⚠️ Please enter a positive number.")
                return PRODUCT_SELECTION
            
            product_id = context.user_data.get('current_product')
            if not product_id:
                await update.message.reply_text("⚠️ Please select a product first.")
                return PRODUCT_SELECTION
            
            product = context.user_data['products'][product_id]
            context.user_data['cart'][product_id] = {
                'quantity': quantity,
                'price': product['price'],
                'name': product['name']
            }
            
            # Show updated cart and product selection
            cart_text = "🛒 Cart:\n"
            total = 0
            for pid, item in context.user_data['cart'].items():
                subtotal = item['quantity'] * item['price']
                total += subtotal
                cart_text += f"• {item['name']}: {item['quantity']} × ₴{item['price']} = ₴{subtotal}\n"
            cart_text += f"\n💰 Total: ₴{total:.2f}\n\n🔽 Select more products or confirm order:"
            
            # Recreate keyboard with product buttons - one per row
            keyboard = []
            for pid, product in context.user_data['products'].items():
                keyboard.append([
                    InlineKeyboardButton(
                        f"💠 {product['name']} - ₴{product['price']}",
                        callback_data=f'input_quantity:{pid}'
                    )
                ])
            
            # Add confirm button
            keyboard.append([
                InlineKeyboardButton("✅ Confirm Order", callback_data='confirm_order')
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(cart_text, reply_markup=reply_markup)
            
            return PRODUCT_SELECTION
            
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid number.")
            return PRODUCT_SELECTION

async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cart = context.user_data['cart']
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Save client info
            cur.execute(
                "INSERT INTO clients (name, username, location) VALUES (%s, %s, %s) RETURNING id",
                (context.user_data['name'], context.user_data.get('username'), context.user_data['location'])
            )
            client_id = cur.fetchone()[0]
            
            # Save each order
            for product_id, item in cart.items():
                cur.execute(
                    "INSERT INTO orders (client_id, product_id, quantity, total_price) VALUES (%s, %s, %s, %s)",
                    (client_id, int(product_id), item['quantity'], item['quantity'] * item['price'])
                )
            conn.commit()
        conn.close()
        
        # Send confirmation
        confirmation = f"✅ Order confirmed!\n\n"
        confirmation += f"👤 Customer: {context.user_data['name']}\n"
        confirmation += f"📍 Location: {context.user_data['location']}\n\n"
        confirmation += "🛍️ Products:\n"
        total_price = 0
        for item in cart.values():
            subtotal = item['quantity'] * item['price']
            total_price += subtotal
            confirmation += f"• {item['name']}: {item['quantity']} × ₴{item['price']} = ₴{subtotal}\n"
        confirmation += f"\n💰 Total Price: ₴{total_price:.2f}"
        
        await query.message.reply_text(confirmation)
        
        # Clear user data and show main menu
        context.user_data.clear()
        keyboard = [
            [InlineKeyboardButton("➕ Add New Order", callback_data='new_order')],
            [InlineKeyboardButton("📊 Download Statistics", callback_data='export_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("🔽 What would you like to do next?", reply_markup=reply_markup)
        return ConversationHandler.END
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await query.message.reply_text("❌ Sorry, there was an error saving your order. Please try again.")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
    context.user_data.clear()
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def export_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    
    query = update.callback_query
    await query.answer()
    
    try:
        conn = get_db_connection()
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
        conn.close()
        
        if not rows:
            await query.message.reply_text("No orders found.")
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
        
        # Calculate totals
        total_quantity = sum(row[1] for row in rows)
        total_revenue = sum(row[2] for row in rows)
        total_cost = sum(row[3] for row in rows)
        total_profit = sum(row[4] for row in rows)
        
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
            caption=f'Statistics Summary:\nTotal Revenue: ₴{total_revenue:.2f}\nTotal Cost: ₴{total_cost:.2f}\nTotal Profit: ₴{total_profit:.2f}'
        )
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await query.message.reply_text("Sorry, there was an error downloading statistics. Please try again.")

def main():
    # Initialize the Application with the bot token
    application = Application.builder().token(os.getenv('BOT_TOKEN')).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(new_order, pattern='^new_order$'),
            CommandHandler('new_order', command_new_order)
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            LOCATION: [CallbackQueryHandler(get_location, pattern='^location:')],
            PRODUCT_SELECTION: [
                CallbackQueryHandler(handle_product_selection, pattern='^(input_quantity:|confirm_order)'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_product_selection)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", command_stats))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(export_orders, pattern='^export_orders$'))

    # Start the bot
    print("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 
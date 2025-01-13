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
        
        conn = psycopg.connect(DATABASE_URL)
        return conn
    except psycopg.Error as e:
        logger.error(f"Database connection error: {e}")
        raise e

# Initialize database tables
def init_db():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Create clients table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    username VARCHAR(100),
                    location VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create products table
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
            
            # Create orders table
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
    except psycopg.Error as e:
        logger.error(f"Database initialization error: {e}")
        raise e

# Initialize database on startup
init_db()

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
        
    keyboard = [
        [InlineKeyboardButton("+ Add New Order", callback_data='new_order')],
        [InlineKeyboardButton("📋 Download Statistics", callback_data='export_orders')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        'Welcome to the Order Management Bot!\n'
        'What would you like to do?',
        reply_markup=reply_markup
    )

async def new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Please enter the customer name:")
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
    
    # Create location selection keyboard
    keyboard = [
        [InlineKeyboardButton("4Seasons", callback_data='location:4Seasons')],
        [InlineKeyboardButton("Omega", callback_data='location:Omega')],
        [InlineKeyboardButton("Kamanina", callback_data='location:Kamanina')],
        [InlineKeyboardButton("Genuez", callback_data='location:Genuez')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please select the customer location:", reply_markup=reply_markup)
    return LOCATION

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
    query = update.callback_query
    await query.answer()
    
    location = query.data.split(':')[1]
    context.user_data['location'] = location
    
    # Initialize empty cart
    context.user_data['cart'] = {}
    
    # Save client information
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Check if client already exists
            cur.execute("""
                SELECT id FROM clients 
                WHERE name = %s AND location = %s
            """, (
                context.user_data['name'],
                context.user_data['location']
            ))
            client_result = cur.fetchone()
            
            if client_result:
                client_id = client_result[0]
                # Update username if provided
                if context.user_data.get('username'):
                    cur.execute("""
                        UPDATE clients 
                        SET username = %s 
                        WHERE id = %s
                    """, (context.user_data['username'], client_id))
            else:
                # Create new client entry
                cur.execute("""
                    INSERT INTO clients (name, username, location)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (
                    context.user_data['name'],
                    context.user_data.get('username'),
                    context.user_data['location']
                ))
                client_id = cur.fetchone()[0]
            
            context.user_data['client_id'] = client_id
            conn.commit()
            
            # Fetch available products
            cur.execute("""
                SELECT id, name, type, price 
                FROM products 
                ORDER BY type, price
            """)
            products = cur.fetchall()
            
        conn.close()
        
        # Create product selection keyboard with quantity controls
        keyboard = []
        for product in products:
            product_id, name, type_, price = product
            # Store product info in context
            if 'products' not in context.user_data:
                context.user_data['products'] = {}
            context.user_data['products'][product_id] = {
                'name': name,
                'price': price,
                'type': type_
            }
            
            # Product button with quantity controls
            quantity = context.user_data['cart'].get(product_id, {}).get('quantity', 0)
            row = [
                InlineKeyboardButton(f"{name:<30} - ₴{price:.2f}", callback_data=f'product_info:{product_id}'),
                InlineKeyboardButton("−", callback_data=f'adjust:{product_id}:minus'),
                InlineKeyboardButton(f"{quantity}", callback_data=f'quantity:{product_id}'),
                InlineKeyboardButton("+", callback_data=f'adjust:{product_id}:plus')
            ]
            keyboard.append(row)
        
        # Always show confirm button with total if cart has items
        total = sum(
            products[pid]['price'] * item['quantity']
            for pid, item in context.user_data['cart'].items()
        )
        if context.user_data['cart']:
            keyboard.append([InlineKeyboardButton(f"✅ Confirm Order (Total: ₴{total:.2f})", callback_data='confirm_cart')])
        else:
            keyboard.append([InlineKeyboardButton("✅ Confirm Order", callback_data='confirm_cart')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(
            "Select products and quantities:\n"
            "(Use + and - buttons to adjust quantities)",
            reply_markup=reply_markup
        )
        return PRODUCT_SELECTION
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await query.message.reply_text("Sorry, there was an error saving client information. Please try again.")
        return ConversationHandler.END

async def handle_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
    query = update.callback_query
    await query.answer()
    
    if query.data == 'confirm_cart':
        if not context.user_data.get('cart'):
            await query.message.reply_text("Please select at least one product.")
            return PRODUCT_SELECTION
        return await process_cart(update, context)
    
    action, product_id = query.data.split(':')[0:2]
    product_id = int(product_id)
    
    if action == 'adjust':
        operation = query.data.split(':')[2]
        cart = context.user_data.get('cart', {})
        
        if product_id not in cart:
            cart[product_id] = {'quantity': 0}
        
        if operation == 'plus':
            cart[product_id]['quantity'] = cart[product_id].get('quantity', 0) + 1
        elif operation == 'minus':
            cart[product_id]['quantity'] = max(0, cart[product_id].get('quantity', 0) - 1)
            if cart[product_id]['quantity'] == 0:
                del cart[product_id]
        
        context.user_data['cart'] = cart
    
    # Update keyboard with new quantities
    keyboard = []
    products = context.user_data['products']
    for pid, details in products.items():
        quantity = context.user_data['cart'].get(pid, {}).get('quantity', 0)
        row = [
            InlineKeyboardButton(
                f"{details['name']:<30} - ₴{details['price']:.2f}",
                callback_data=f'product_info:{pid}'
            ),
            InlineKeyboardButton("−", callback_data=f'adjust:{pid}:minus'),
            InlineKeyboardButton(f"{quantity}", callback_data=f'quantity:{pid}'),
            InlineKeyboardButton("+", callback_data=f'adjust:{pid}:plus')
        ]
        keyboard.append(row)
    
    # Always show confirm button with total if cart has items
    total = sum(
        products[pid]['price'] * item['quantity']
        for pid, item in context.user_data['cart'].items()
    )
    if context.user_data['cart']:
        keyboard.append([InlineKeyboardButton(f"✅ Confirm Order (Total: ₴{total:.2f})", callback_data='confirm_cart')])
    else:
        keyboard.append([InlineKeyboardButton("✅ Confirm Order", callback_data='confirm_cart')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Show cart summary
    cart_text = "Select products and quantities:\n"
    if context.user_data['cart']:
        cart_text += "\nCurrent cart:\n"
        for pid, item in context.user_data['cart'].items():
            product = products[pid]
            subtotal = product['price'] * item['quantity']
            cart_text += f"• {product['name']}: {item['quantity']} x ₴{product['price']:.2f} = ₴{subtotal:.2f}\n"
    
    try:
        await query.message.edit_text(cart_text, reply_markup=reply_markup)
    except Exception as e:
        # If message is identical, just continue
        pass
    
    return PRODUCT_SELECTION

async def process_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cart = context.user_data['cart']
    products = context.user_data['products']
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            for product_id, item in cart.items():
                quantity = item['quantity']
                product = products[product_id]
                total_price = quantity * product['price']
                
                # Check for existing order
                cur.execute("""
                    SELECT o.id, o.quantity, o.total_price
                    FROM orders o
                    WHERE o.client_id = %s 
                    AND o.product_id = %s 
                    AND DATE(o.created_at) = CURRENT_DATE
                """, (context.user_data['client_id'], product_id))
                existing_order = cur.fetchone()
                
                if existing_order:
                    # Update existing order
                    order_id, existing_quantity, existing_total = existing_order
                    new_quantity = existing_quantity + quantity
                    new_total = existing_total + total_price
                    
                    cur.execute("""
                        UPDATE orders 
                        SET quantity = %s, total_price = %s 
                        WHERE id = %s
                    """, (new_quantity, new_total, order_id))
                else:
                    # Create new order
                    cur.execute("""
                        INSERT INTO orders (client_id, product_id, quantity, total_price)
                        VALUES (%s, %s, %s, %s)
                    """, (context.user_data['client_id'], product_id, quantity, total_price))
            
            conn.commit()
            
            # Fetch client details for confirmation
            cur.execute("""
                SELECT name, location
                FROM clients
                WHERE id = %s
            """, (context.user_data['client_id'],))
            client_name, location = cur.fetchone()
        
        conn.close()
        
        # Send confirmation message
        confirmation_text = "Orders saved successfully!\n\n"
        confirmation_text += f"Customer: {client_name}\n"
        confirmation_text += f"Location: {location}\n\n"
        confirmation_text += "Ordered items:\n"
        
        total_order = 0
        for product_id, item in cart.items():
            product = products[product_id]
            quantity = item['quantity']
            subtotal = quantity * product['price']
            total_order += subtotal
            confirmation_text += f"• {product['name']}: {quantity} x ₴{product['price']:.2f} = ₴{subtotal:.2f}\n"
        
        confirmation_text += f"\nTotal Order: ₴{total_order:.2f}"
        
        await query.message.reply_text(confirmation_text)
        
        # Clear cart and show main menu
        context.user_data.clear()
        keyboard = [
            [InlineKeyboardButton("+ Add New Order", callback_data='new_order')],
            [InlineKeyboardButton("📋 Download Statistics", callback_data='export_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("What would you like to do next?", reply_markup=reply_markup)
        
        return ConversationHandler.END
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await query.message.reply_text("Sorry, there was an error saving your orders. Please try again.")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return ConversationHandler.END
    
    context.user_data.clear()
    await update.message.reply_text("Operation cancelled.")
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
                    SUM(o.total_price) as total_price,
                    p.orig_price * SUM(o.quantity) as total_cost,
                    SUM(o.total_price) - (p.orig_price * SUM(o.quantity)) as profit
                FROM orders o
                JOIN products p ON o.product_id = p.id
                GROUP BY p.name, p.orig_price
                ORDER BY p.name
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
            'Total Revenue',
            'Total Cost',
            'Profit'
        ])
        writer.writerows(rows)
        
        # Convert to bytes
        output.seek(0)
        bytes_output = output.getvalue().encode()
        
        # Send file
        await query.message.reply_document(
            document=io.BytesIO(bytes_output),
            filename='statistics.csv',
            caption='Here are the summarized statistics with profit calculations.'
        )
        
    except Error as e:
        logger.error(f"Database error: {e}")
        await query.message.reply_text("Sorry, there was an error downloading statistics. Please try again.")

def main():
    # Initialize the Application with the bot token
    application = Application.builder().token(os.getenv('BOT_TOKEN')).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(new_order, pattern='^new_order$')],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            LOCATION: [CallbackQueryHandler(get_location, pattern='^location:')],
            PRODUCT_SELECTION: [
                CallbackQueryHandler(handle_product_selection, pattern='^(product_info|adjust|quantity|confirm_cart)')
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(export_orders, pattern='^export_orders$'))

    # Start the bot
    print("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 
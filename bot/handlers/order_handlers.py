from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from ..utils.constants import NAME, LOCATION, PRODUCT_SELECTION, QUANTITY, EMOJIS
from ..utils.keyboards import create_product_keyboard, create_location_keyboard, create_main_menu_keyboard
from ..utils.formatters import format_cart_text
from ..database.database import db
from ..models.models import CartItem

async def command_new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .auth_handlers import check_auth
    if not await check_auth(update):
        return ConversationHandler.END
    
    # Clear any existing conversation data
    context.user_data.clear()
    
    # Handle both direct command and callback query
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
    
    await message.reply_text("Enter the customer name:")
    return NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Parse name and optional username
    if '@' in text:
        name, username = text.split('@', 1)
        context.user_data['name'] = name.strip()
        # Add @ if not already present
        username = username.strip()
        if username:  # Only set username if it's not empty
            context.user_data['username'] = f"@{username}" if not username.startswith('@') else username
        else:
            context.user_data['username'] = None
    else:
        context.user_data['name'] = text.strip()
        context.user_data['username'] = None
    
    await update.message.reply_text(
        f"{EMOJIS['LOCATION']} Please select the delivery location:",
        reply_markup=create_location_keyboard()
    )
    return LOCATION

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    location = query.data.replace('location:', '')
    context.user_data['location'] = location
    context.user_data['cart'] = {}
    
    products = db.get_products()
    keyboard = create_product_keyboard(products)
    
    await query.message.reply_text(
        f"{EMOJIS['SHOPPING']} Please select products to order:",
        reply_markup=keyboard
    )
    return PRODUCT_SELECTION

async def handle_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'confirm_order':
        cart = context.user_data.get('cart', {})
        if not cart:
            await query.message.reply_text(f"{EMOJIS['WARNING']} Cart is empty!")
            return PRODUCT_SELECTION
        
        cart_text, total = format_cart_text(cart)
        await query.message.reply_text(
            f"{EMOJIS['PACKAGE']} Order Summary:\n\n"
            f"👤 Customer: {context.user_data['name']}\n"
            f"📍 Location: {context.user_data['location']}\n\n"
            f"{cart_text}\n\n"
            "Order has been saved! ✅"
        )
        
        # Save order to database
        db.save_order(
            client_name=context.user_data['name'],
            username=context.user_data.get('username'),
            location=context.user_data['location'],
            cart=cart
        )
        
        # Show main menu after order completion
        await query.message.reply_text(
            f"{EMOJIS['ARROW']} What would you like to do next?",
            reply_markup=create_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    product_id = query.data.split(':')[1]
    await query.message.reply_text(f"{EMOJIS['PLUS']} Enter quantity:")
    context.user_data['current_product'] = product_id
    return QUANTITY

async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        quantity = int(update.message.text)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"{EMOJIS['ERROR']} Please enter a valid positive number!")
        return QUANTITY
    
    product_id = context.user_data['current_product']
    products = db.get_products()
    product = next(p for p in products if str(p.id) == product_id)
    
    cart = context.user_data.get('cart', {})
    cart[product_id] = CartItem(
        name=product.name,
        price=product.price,
        quantity=quantity
    )
    context.user_data['cart'] = cart
    
    cart_text, _ = format_cart_text(cart)
    keyboard = create_product_keyboard(products, show_confirm=True)
    
    await update.message.reply_text(
        f"{cart_text}",
        reply_markup=keyboard
    )
    return PRODUCT_SELECTION 
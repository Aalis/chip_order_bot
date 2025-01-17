from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ..models.models import Product
from .constants import EMOJIS, BUILDINGS

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

def create_location_keyboard() -> InlineKeyboardMarkup:
    """Create a keyboard with location buttons."""
    keyboard = [
        [InlineKeyboardButton(
            f"{BUILDINGS[location]} {location}",
            callback_data=location
        )]
        for location in BUILDINGS.keys()
    ]
    return InlineKeyboardMarkup(keyboard)

def create_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Create the main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton(f"{EMOJIS['PLUS']} Add New Order", callback_data='new_order')],
        [InlineKeyboardButton(f"{EMOJIS['STATS']} Download Statistics", callback_data='export_orders')]
    ]
    return InlineKeyboardMarkup(keyboard) 
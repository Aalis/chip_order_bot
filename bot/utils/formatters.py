from typing import Dict, Tuple
from ..models.models import CartItem
from .constants import EMOJIS

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

def format_order_confirmation(client_name: str, location: str, cart: Dict[str, CartItem]) -> str:
    """Format order confirmation message."""
    cart_text, total_price = format_cart_text(cart)
    return (
        f"{EMOJIS['CONFIRM']} Order confirmed!\n\n"
        f"{EMOJIS['PERSON']} Customer: {client_name}\n"
        f"{EMOJIS['LOCATION']} Location: {location}\n\n"
        f"{EMOJIS['SHOPPING']} Products:\n"
        f"{cart_text}\n"
        f"{EMOJIS['MONEY']} Total Price: ₴{total_price:.2f}"
    )

def format_statistics_caption(total_revenue: float, total_cost: float, total_profit: float) -> str:
    """Format statistics caption."""
    return (
        f'Statistics Summary:\n'
        f'{EMOJIS["MONEY"]} Total Revenue: ₴{total_revenue:.2f}\n'
        f'{EMOJIS["SHOPPING"]} Total Cost: ₴{total_cost:.2f}\n'
        f'{EMOJIS["STATS"]} Total Profit: ₴{total_profit:.2f}'
    ) 
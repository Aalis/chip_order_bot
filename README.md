# Order Management Telegram Bot

A Telegram bot for managing orders with the following features:

## Features
- Add new orders with customer details
- Track orders by location (4Seasons, Omega, Kamanina, Genuez)
- Support for customer usernames
- Product catalog with prices in UAH
- Order quantity management with +/- buttons
- Daily order summaries
- Export orders to CSV

## Products
- Plastic: ₴100.00
- Leather: ₴300.00
- Bracelet: ₴200.00

## Setup
1. Create a PostgreSQL database
2. Run `init_db.sql` to create tables and insert products
3. Create `.env` file with:
   ```
   BOT_TOKEN=your_telegram_bot_token
   AUTHORIZED_USERS=comma_separated_user_ids
   ```
4. Install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
5. Run the bot:
   ```bash
   python bot.py
   ```

## Database Schema
- `clients`: Store customer information
- `products`: Product catalog
- `orders`: Track orders with quantities and prices

## Usage
1. Start bot with `/start`
2. Click "Add New Order"
3. Enter customer name (optionally with @username)
4. Select location
5. Choose product
6. Set quantity
7. Confirm order 
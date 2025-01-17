import os
from typing import Dict, List, Optional, Tuple
import psycopg
from psycopg import Error
from ..models.models import Product, CartItem

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
                # First try to find existing client
                cur.execute(
                    "SELECT id FROM clients WHERE name = %s AND location = %s",
                    (client_name, location)
                )
                result = cur.fetchone()
                
                if result:
                    # Use existing client
                    client_id = result[0]
                else:
                    # Create new client
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

# Initialize database instance
db = Database() 
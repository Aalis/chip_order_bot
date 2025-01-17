from dataclasses import dataclass

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
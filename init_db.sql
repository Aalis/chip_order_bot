-- Drop existing tables
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS clients;

-- Create clients table
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    username VARCHAR(100) DEFAULT NULL,
    location VARCHAR(50) NOT NULL,
    created_at DATE DEFAULT CURRENT_DATE,
    UNIQUE(name, location)
);

-- Create products table
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) CHECK (type IN ('plastic', 'leather', 'bracelet')) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    orig_price DECIMAL(10, 2) NOT NULL
);

-- Create orders table
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    total_price DECIMAL(10, 2) NOT NULL,
    created_at DATE DEFAULT CURRENT_DATE
);

-- Insert sample products
INSERT INTO products (name, type, price, orig_price) VALUES
    ('Plastic', 'plastic', 20.00, 10.00),
    ('Leather', 'leather', 300.00, 150.00),
    ('Bracelet', 'bracelet', 200.00, 100.00); 


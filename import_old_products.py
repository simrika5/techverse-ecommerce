from store.models import Product, Category
from decimal import Decimal
from datetime import datetime

products = [
    {
        "name": "MacBook Pro 14-inch M3",
        "description": "Premium Apple laptop with powerful performance, high-resolution display, and long battery life. Great for developers, designers, and everyday work.",
        "price": Decimal("1000"),
        "stock": 6,
        "image": "products/macnook.webp",
        "category": "Laptops",
    },
    {
        "name": "Dell XPS 13",
        "description": "Slim and lightweight Windows laptop with excellent build quality, fast processor, and a sharp display.",
        "price": Decimal("1299"),
        "stock": 2,
        "image": "products/dell-xps-13-9350-2025-laptop.png",
        "category": "Laptops",
    },
    {
        "name": "Lenovo ThinkPad X1 Carbon",
        "description": "Professional business laptop with strong performance, comfortable keyboard, and durable design.",
        "price": Decimal("1200"),
        "stock": 7,
        "image": "products/61nm3dwXAmL._AC_SL1500_.jpg",
        "category": "Laptops",
    },
    {
        "name": "Logitech Wireless Mouse",
        "description": "Comfortable wireless mouse with smooth tracking and long battery life.",
        "price": Decimal("39"),
        "stock": 23,
        "image": "products/product_image-logitech-mx-master-4-wireless-mouse-grey-0774.webp",
        "category": "Accessories",
    },
    {
        "name": "Laptop Backpack",
        "description": "Water-resistant laptop backpack with padded protection for laptops and accessories.",
        "price": Decimal("59"),
        "stock": 43,
        "image": "products/f794298104cfe4adc7eecbb3b08c42da.jpg_720x720q80.jpg",
        "category": "Accessories",
    },
    {
        "name": "USB-C Laptop Hub",
        "description": "Multi-port USB-C hub with HDMI, USB ports, and charging support for modern laptops.",
        "price": Decimal("79"),
        "stock": 52,
        "image": "products/3450f8e396324d17cc82db0010d37ca2.png_720x720q80.png",
        "category": "Accessories",
    },
    {
        "name": "Mechanical Keyboard",
        "description": "Premium mechanical keyboard with comfortable keys, ideal for programming and gaming.",
        "price": Decimal("99"),
        "stock": 27,
        "image": "products/mehanical.webp",
        "category": "Accessories",
    },
    {
        "name": "Laptop Cooling Pad",
        "description": "Cooling stand with fans to improve laptop airflow during heavy use.",
        "price": Decimal("49"),
        "stock": 22,
        "image": "products/cooling.webp",
        "category": "Accessories",
    },
]

for data in products:
    category = Category.objects.get(name=data["category"])

    product, created = Product.objects.get_or_create(
        name=data["name"],
        defaults={
            "description": data["description"],
            "price": data["price"],
            "stock": data["stock"],
            "image": data["image"],
            "category": category,
        },
    )

    if created:
        print(f"IMPORTED: {product.name}")
    else:
        print(f"ALREADY EXISTS: {product.name}")

print()
print(f"Total products now: {Product.objects.count()}")

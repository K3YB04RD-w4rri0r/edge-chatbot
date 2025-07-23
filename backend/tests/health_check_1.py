import requests

item = {
    "name": "Test Item",
    "description": "A test",
    "price": 9.99,
    "tax": 0.5
}

response = requests.post("http://localhost:8000/items", json=item)

print(response.json())

# Base URL
base_url = "http://localhost:8000"

# Health check
response = requests.get(f"{base_url}/health")
print(response.json())

# Create an item
item_data = {
    "name": "Python Book",
    "price": 39.99,
    "description": "Learn Python Programming"
}
response = requests.post(f"{base_url}/items", json=item_data)
print(response.json())

# Get all items
response = requests.get(f"{base_url}/items")
print(response.json())
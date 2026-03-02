from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import URLSafeSerializer
from secrets import token_urlsafe, token_hex
from sqlalchemy import create_engine, text
import bleach
import uvicorn

productdb = create_engine("mysql+pymysql://4J4VubRMtDYVKrk.root:UtLbWgr32k7ka8sW@gateway01.ap-southeast-1.prod.aws.tidbcloud.com:4000/perfume_product_db", pool_pre_ping=True)
cart1_db = create_engine("mysql+pymysql://4J4VubRMtDYVKrk.root:UtLbWgr32k7ka8sW@gateway01.ap-southeast-1.prod.aws.tidbcloud.com:4000/perfume_product_db", pool_pre_ping=True)
cart2_db = create_engine("mysql+pymysql://4J4VubRMtDYVKrk.root:UtLbWgr32k7ka8sW@gateway01.ap-southeast-1.prod.aws.tidbcloud.com:4000/perfume_product_db", pool_pre_ping=True)
connected_clients: dict[WebSocket, str] = {}

def delete_cart(cartdb, name):
    with cartdb.connect() as conn:
        cart = conn.execute(text("SELECT email, cart_json FROM cart_tbl WHERE cart_json LIKE :w"), {"w": f"%{name}%"})
        if len(cart) == 0: pass
        for email, cartdata in cart:
            cartdata = json.loads(cartdata)
            del cartdata[name]
            conn.execute(text("UPDATE cart_tbl SET cart_json = :c WHERE email = :e", {"e": email, "c": json.dumps(cartdata)})
        print("success")

def update_cart(cartdb, change, data):
    with cartdb.connect() as conn:
        cart = conn.execute(text("SELECT email, cart_json FROM cart_tbl WHERE cart_json LIKE :w"), {"w": f"%{name}%"})
        if len(cart) == 0: pass
        cartdata = json.loads(cartdata)
        for email, cartdata in cart:
            if change == "name":
              qty = cartdata[data["name"]]
              del cartdata[data["previous-name"]]
              cartdata[data["name"]] = qty
            elif change == "qty":
                if cartdata[data["name"]] > data["qty"]:
                    cartdata[data["name"]] = data["qty"]
            elif change == "qty and name":
                if cartdata[data["name"]] > data["qty"]:
                    cartdata[data["name"]] = data["qty"]
                del cartdata[data["previous-name"]]
            else:
                print("Error on editing cart")
            conn.execute(text("UPDATE cart_tbl SET cart_json = :c WHERE email = :e", {"e": email, "c": json.dumps(cartdata)})
        print("success")
        

def get_data():
    with productdb.connect() as conn:
      items = conn.execute(text("SELECT name, quantity, price, img_link, description FROM products_tbl"))
      list_items = []
      for x in items:
          list_items.append([x.name, x.quantity, str(x.price), x.img_link, x.description])
      return list_items
    
async def broadcast(message: dict):
    disconnected = []

    for socket in connected_clients.keys():
        try:
            await socket.send_json(message)
        except:
            disconnected.append(socket)

    # Clean up dead connections
    for socket in disconnected:
        connected_clients.pop(socket, None)
# ------------------------------
# Token generation & verification
# ------------------------------
serializer = URLSafeSerializer(secret_key=token_hex(16))

def verify_token(token: str) -> bool:
    if not token:
        return False
    try:
        serializer.loads(token, salt="websocket_token", max_age=3600)
        return True
    except Exception:
        return False

def generate_token() -> str:
    return serializer.dumps(token_urlsafe(16), salt="websocket_token")

# ------------------------------
# FastAPI setup
# ------------------------------
app = FastAPI()
templates = Jinja2Templates(directory="/Users/jayren/Desktop/Developer Files/perfume/Python /templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ------------------------------
# Example login endpoint to generate token
# ------------------------------
@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.post("/login")
async def login(request: Request):
    form = await request.form()
    password = form.get("password")
    username = form.get("username")
    if password == "admin123" and username == "admin":
        token = generate_token()
        return templates.TemplateResponse("dashboard.html", {"request": request, "token": token})
    return {"error": "Invalid password"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")

    if not verify_token(token):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    # Store websocket with server-side session id
    connected_clients[websocket] = token

    # Send initial data
    await websocket.send_json({"data": get_data()})

    print(f"Client connected. Total: {len(connected_clients)}")

    try:
        while True:
            data = await websocket.receive_json()
            print(f"Received: {data}")

            await main(data)

    except WebSocketDisconnect:
        connected_clients.pop(websocket, None)
        print(f"Client disconnected. Total: {len(connected_clients)}")

async def main(data):
    # Sanitize input
    for key, value in data.items():
        if isinstance(value, str):
            data[key] = bleach.clean(value)

    query = data.get("query")

    with productdb.begin() as conn:

        match query:
            case "insert":
                conn.execute(text("""
                    INSERT INTO products_tbl (name, quantity, price, img_link, description)
                    VALUES (:name, :qty, :price, :img, :description)
                """), {
                    "name": data["product_name"],
                    "price": round(float(data["product_price"]), 2),
                    "description": data["product_description"],
                    "qty": int(data["product_qty"]),
                    "img": data["img_link"]
                })

            case "update":
                conn.execute(text("""
                    UPDATE products_tbl
                    SET name=:name, price=:price, 
                        description=:description,
                        qty=:qty, img_link=:img
                    WHERE name=:name
                """), {
                    "name": data["product_name"],
                    "price": data["product_price"],
                    "description": data["product_description"],
                    "qty": data["product_qty"],
                    "img": data["img_link"]
                })
                update_cart(cart1_db, data["change"], {"name": data["product_name"], "previous-name": data["previous_name"], "qty": data["product_qty"] })
                update_cart(cart2_db, data["change"], {"name": data["product_name"], "previous-name": data["previous_name"], "qty": data["product_qty"] })

            case "delete":
                conn.execute(text("""
                    DELETE FROM products_tbl
                    WHERE name=:name
                """), {
                    "name": data["product_name"]
                })
                delete_cart(cart1_db, data["product_name"])
                delete_cart(cart2_db, data["product_name"])

            case _:
                print("Unknown query")

    # Broadcast updated data to ALL clients
    await broadcast({
        "message": "success",
        "data": get_data()
    })

if __name__ == "__main__":
    uvicorn.run("product_dash:app", reload=True)

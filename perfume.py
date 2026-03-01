from flask import Flask, jsonify, request, make_response, render_template_string, abort
from flask_limiter import Limiter
from flask_cors import CORS
from sqlalchemy import create_engine, text
from argon2 import PasswordHasher
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import json
import secrets
from datetime import datetime, timedelta, timezone
import re
import requests as req
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from argon2.exceptions import VerifyMismatchError
from urllib.parse import quote_plus
import firebase_admin
from firebase_admin import credentials, firestore
import random
import logging
import bleach
import threading
import httpx
import asyncio
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import hashlib
import hmac
import requests
import os

"""
client = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_name("credentials.json", ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]))

sheet_cash = client.open("Perfume Orders").worksheet("Cash")
sheet_tng = client.open("Perfume Orders").worksheet("TNG")
"""

# ------------------ CONFIG ------------------

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^\+[1-9]\d{1,14}$")
POSTCODE = re.compile(r"^[1-9]\d{4}$")
PEPPER = "ert9iop"
SECRET_KEY = "super-secret-key"
TOKEN_SALT = "cart-salt"
BILLPLZ_API_KEY = ""
cred = credentials.Certificate("/Users/jayren/Downloads/perfume-rna-firebase-adminsdk-fbsvc-4a8aa949ba.json")
firebase_admin.initialize_app(cred)
fs_db = firestore.client()
malaysia_states_and_federal_territories = [
    "Johor",
    "Kedah",
    "Kelantan",
    "Melaka",
    "Negeri Sembilan",
    "Pahang",
    "Perak",
    "Perlis",
    "Pulau Pinang",
    "Sabah",
    "Sarawak",
    "Selangor",
    "Terengganu",
    "Kuala Lumpur",
    "Putrajaya",
    "Labuan"
]

# ---------------- TOKEN ----------------

serializer = URLSafeTimedSerializer("another-super-secret-key")
TOKEN_SALT_ORDER = "bcsfo"

def generate_token():
    return serializer.dumps(secrets.token_hex(16), salt=TOKEN_SALT_ORDER)

def check_token(token):
    try:
        serializer.loads(token, salt=TOKEN_SALT_ORDER, max_age=900)
        return True
    except (BadSignature, SignatureExpired):
        return False

# ------------------ HELPERS ------------------

def is_valid_email(email):
    return EMAIL_RE.match(email)

def is_valid_phone(phone):
    return PHONE_RE.match(phone)

def check_postcode(code):
    return POSTCODE.match(code)

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, salt_len=16)

def hash_password(password):
    return ph.hash(password + PEPPER)

def verify_password(hashed, password):
    return ph.verify(hashed, password + PEPPER)

serializer = URLSafeTimedSerializer(SECRET_KEY)
signed_signature = URLSafeTimedSerializer("A@123!23")

def generate_token_reset():
    return signed_signature.dumps(secrets.token_hex(16), salt="abc")

def check_token_reset(token_id: str):
    try:
        signed_signature.loads(token_id, salt="abc", max_age=3600)
        return True
    except (BadSignature, SignatureExpired):
        return False

def check_new_password(password):
    if (
        len(password) >= 6 and
        any(c.isupper() for c in password) and
        any(c.islower() for c in password) and
        any(c.isdigit() for c in password) and
        any(c in "!@#$%^&*()" for c in password)
    ):
        return True
    return False

def get_ip():
    return request.remote_addr

# ---------------- CACHE ----------------

product_data = {}
product_lock = threading.Lock()

def product_fetch():
    with productdb.connect() as conn:
        rows = conn.execute(text("SELECT name, img_link FROM product_tbl"))
        with product_lock:
            product_data.clear()
            for n, i in rows:
                product_data[n] = i

# ------------------ DATABASES ------------------
def make_engine(user, password, host, port, db):
    password = quote_plus(password)  # encode special chars
    return create_engine(
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}",
        pool_pre_ping=True,
        connect_args={"ssl": {"ca": "/etc/ssl/cert.pem"}}
    )

productdb = make_engine("4J4VubRMtDYVKrk.root", "UtLbWgr32k7ka8sW", "gateway01.ap-southeast-1.prod.aws.tidbcloud.com", 4000, "perfume_product_db")
clientdb  = make_engine("2p82bsJkP25gYSs.root", "utbWAfpf74f4kKVg", "gateway01.us-west-2.prod.aws.tidbcloud.com", 4000, "clientdb")
orderdb   = make_engine("3ePjuz2Qec5Dphc.root", "TFHd3bdTUar44EQL", "gateway01.ap-southeast-1.prod.aws.tidbcloud.com", 4000, "order_db")
cartdb    = make_engine("3SMehWwqfhnNVbU.root", "kJSWY0ti6IeVBB4u", "gateway01.ap-southeast-1.prod.aws.tidbcloud.com", 4000, "client_cart")
tokendb   = make_engine("3SZzKdxQsk3bRh1.root", "dtdp9GoMT97B6b8L", "gateway01.ap-southeast-1.prod.aws.tidbcloud.com", 4000, "cart_token_db")
order_cache_db = make_engine("488EN1h3SHK5USZ.root", "tZHWCFdtOqa8pvrt", "gateway01.ap-southeast-1.prod.aws.tidbcloud.com", 4000, "order_cache_db")
reservedb = make_engine("2ufYbQ2RxhJDTsn.root", "pjStpb6AMMurZuqS", "gateway01.us-west-2.prod.aws.tidbcloud.com", 4000, "stock_reservation_db")

uri = "mongodb+srv://ooijaysheng_db_user:killer1268@osyztke.mongodb.net/?appName=reset-password-perfume"
client = MongoClient(uri, server_api=ServerApi("1"))

db = client["reset-password-perfume"]
collections = db["token_reset_password_document"]
collections_post = db["token_reset_password_post"]

collections.create_index("token", unique=True)
collections_post.create_index("token_post", unique=True)
collections.create_index("expires_at", expireAfterSeconds=0)
collections_post.create_index("expires_at", expireAfterSeconds=0)

def get_data():
    with productdb.connect() as conn:
      items = conn.execute(text("SELECT name, quantity, price, img_link, description FROM products_tbl"))
      list_items = []
      for x in items:
          list_items.append(list(x))
      return list_items
    
product_list = get_data()

# ------------------ APP ------------------

app = Flask(__name__)
CORS(app, supports_credentials=True, allow_headers=["Content-Type", "Authorisation"], methods=["GET", "POST", "OPTIONS"])
limiter = Limiter(app=app, key_func=get_ip, storage_uri="rediss://default:AUnRAAIncDI3YTk1YTk5NjBmYzU0YWY0OWMzZTRiMDBjNGJiZmYwYXAyMTg4OTc@enormous-mule-18897.upstash.io:6379",
storage_options={"socket_connect_timeout": 9}, fail_on_first_breach = True)

# ------------------ LOGIN ------------------

@app.route("/login", methods=["POST"])
@limiter.limit("5/minute")
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "No data received"}), 401

    email = data.get("email")
    password = data.get("password")

    try: 
     with clientdb.connect() as conn:
        result = conn.execute(
            text("SELECT password_hashed, phone_number, date_joined FROM client_tbl WHERE email=:email"),
            {"email": email}
        ).fetchone()
    except:
     return jsonify({"error"})

    if not result:
        return jsonify({"message": "Invalid credentials"}), 401

    stored_password, phone, joined = result

    try:
        verify_password(stored_password, password)
    except VerifyMismatchError:
        print(f"Failed login attempt for {email} from IP: {get_ip()}")
        return jsonify({"message": "password incorrect"}), 401

    cart_token = serializer.dumps({"email": email, "token": secrets.token_urlsafe(16)}, salt=TOKEN_SALT)

    try:
     with tokendb.begin() as conn:
        conn.execute(text("UPDATE cart_token_tbl SET cart_token=:token WHERE email=:email"), {"token": cart_token, "email": email})
    except:
        print("Error on token")

    """

    cartdata = None
    try: 
     with cartdb.connect() as cart:
        cartdata = cart.execute(text("SELECT cart_json FROM cart_one_tbl WHERE email=:email"), {"email": email}).fetchone()
        cartdata2 = json.loads(cartdata)
     with productdb.connect() as conn:
      items = conn.execute(text("SELECT name, quantity FROM products_tbl"))
      list_product_name = []
      for x in items:
         list_product_name.append(x[0])
      for product_name,qty in cartdata2:
         for x in items:
            if product_name not in list_product_name: del cartdata2[product_name]
            if product_name == x[0]:
               if qty > x[1]:
                  del cartdata2[product_name]

      if (json.dumps(cartdata2) != cartdata):
         if cartdata2 == None: 
            cartdata2 = {}
         with cartdb.begin() as cart:
          cart.execute(text("UPDATE cart_one_tbl SET cart_json=:cart WHERE email=:email"),
                     {"cart": json.dumps(cartdata2), "email": email})
    except Exception as e:
        print(e)
    """

    orderdata = []
    try: 
     with orderdb.connect() as order:
        orderdata = order.execute(text("SELECT * FROM order_tbl WHERE email=:email"), {"email": email}).fetchall()
        orderdata = [dict(row._mapping) for row in orderdata]
    except:
        print("Error on order")

    response = make_response(jsonify({
        "account": [email, phone, str(joined), cart_token],
        "orderdata": orderdata,
        #"cartdata": cartdata[0] if cartdata else {},
        "message": "success"
    }))

    print(f"User logged in: {email} from IP: {get_ip()}, cart_token: {cart_token}")
    return response

# ------------------ REGISTER ------------------

@app.route("/register", methods=["POST"])
def register():
  try:
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON"}), 400

    email = data["email"]
    password = data["password"]
    repeat = data["repeat_password"]
    phone = data["phone_no"]

    if password != repeat or not check_new_password(password):
        return jsonify({"message": "Password do not meet the criteria."}), 400

    if not is_valid_email(email) or not is_valid_phone(phone):
        return jsonify({"message": "Invalid email or phone"}), 400
    
    with clientdb.connect() as conn:
     exists = conn.execute(
        text("SELECT 1 FROM client_tbl WHERE email=:email LIMIT 1"),
        {"email": email}
     ).fetchone()

     if exists:
      return jsonify({"message": "Email already registered"}), 409
    
    token = secrets.token_urlsafe(20)
    code_number = random.randint(100000, 999999)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=0.25)
    doc_ref = fs_db.collection("users").document(token)
    doc_ref.set({
      "email": email,
      "password": password,
      "phone_number": phone,
      "code": code_number,
      "expires_at": expires_at
    })

    payload = {"token": token, "email": email, "code": code_number}

    response = req.post("https://script.google.com/macros/s/AKfycbxIBxtUvV7oyJqWsX_HvncNekRW7JEuWG2HYTo6X1uDEHhnwvWqtXNTbY0cQUlC6MKtjw/exec", json=payload)
    if response.status_code != 200:
        print("Error sending email:", response.text)
        return jsonify({"message": "failed to send email"}), 500
    return jsonify({"message": "success", "token": token, "code": code_number})
  except Exception as e:
    print(e)
    return jsonify({"message": "Failed to register"}), 500


@app.route("/final_register", methods=["GET", "POST"])
def final_register():
  if request.method == "POST":
    data = request.get_json(silent=True)
    user_code = data["code"]
    token_user = data["token"]
    doc_ref = fs_db.collection("users").document(token_user).get()
    if doc_ref.exists:
        doc_ref = doc_ref.to_dict()
        if str(doc_ref["code"]) != str(user_code):
            print(doc_ref["code"], user_code)
            return jsonify({"message": "firebase failed"})
        
        hashed = hash_password(doc_ref["password"])
        email = doc_ref["email"]
        phone = doc_ref["phone_number"]
        now = datetime.now().strftime("%d/%m/%Y")

        try:
          with clientdb.begin() as conn:
           conn.execute(text("""
             INSERT INTO client_tbl (email, password_hashed, phone_number, date_joined)
             VALUES (:email, :password, :phone, :date)
            """), {"email": email, "password": hashed, "phone": phone, "date": now})
        except Exception as e:
          print(e)
          return jsonify({"message": "User existed"})

        try:
         with cartdb.begin() as cart:
           cart.execute(text("INSERT INTO cart_one_tbl (email, cart_json) VALUES (:email, '{}')"),{"email": email})
        except:
           print("error on cart")
           return jsonify({"message": "User existed"})


        try:
         with tokendb.begin() as token:
          token.execute(text("INSERT INTO cart_token_tbl (email, cart_token) VALUES (:email, :token)"), {"email": email, "token": ""})
        except:
          print("error on token")
          return jsonify({"message": "User existed"})

        fs_db.collection("users").document(token_user).delete()
        print("User registered:", email)
        return jsonify({"message": "success"})
  else:
     token = request.args.get("token")
     return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Confirm Sign-up</title>
  <style>
    #confirm_sign-up_container {
      width: 100%;
      min-height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
      background-color: rgb(231, 233, 235);
    }

    #confirm_form {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 20px;
      background-color: white;
      padding: 20px;
      box-shadow: 3px 3px 6px 1px grey;
    }

    .otp-container {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: center;
    }

    .otp {
      height: 50px;
      width: 40px;
      font-size: 23px;
      border: 0.5px solid black;
      text-align: center;
      outline: none;
      box-sizing: border-box;
    }

    .otp:focus {
      border-color: blue;
    }

    #confirm_form button {
      background-color: blue;
      color: white;
      padding: 10px 20px;
      font-size: 16px;
      border: none;
      cursor: pointer;
    }

    #confirm_form p {
      font-weight: bold;
      font-size: 25px;
    }

    #confirm_form img {
      width: 60px;
      height: 60px;
      display: none;
    }

    #success, #error {
      flex-direction: column;
      align-items: center;
      background-color: white;
      box-shadow: 3px 3px 6px 1px grey;
      width: 70%;
      padding: 20px;
      display: none;
    }

    #success h3 {
      font-size: 24px;
      color: green;
      margin: 0;
    }

    #error h3 {
      font-size: 24px;
      color: red;
      margin: 0;
    }

    #success button, #error button {
      font-size: 16px;
      color: white;
      padding: 10px;
      border-radius: 6px;
      border: none;
      margin-top: 10px;
    }

    #error button {
      background-color: red;
    }

    #success button {
      background-color: green;
    }

    @media (max-width: 360px) {
      .otp {
        height: 40px;
        width: 30px;
        font-size: 18px;
      }
    }
  </style>
</head>
<body>

<div id="confirm_sign-up_container">
  <div id="confirm_form">
    <p>Confirm sign-up</p>
    <div class="otp-container">
      <input class="otp" type="text" maxlength="1">
      <input class="otp" type="text" maxlength="1">
      <input class="otp" type="text" maxlength="1">
      <input class="otp" type="text" maxlength="1">
      <input class="otp" type="text" maxlength="1">
      <input class="otp" type="text" maxlength="1">
    </div>
    <button onclick="send_code()">Proceed</button>
    <img id="loading_img" src="https://blog.teamtreehouse.com/wp-content/uploads/2015/05/InternetSlowdown_Day.gif" />
  </div>

  <div id="success">
    <h3>Success</h3>
    <p>You may return to the mainpage.</p>
    <button onclick="redirect()">Back</button>
  </div>

  <div id="error">
    <h3>Error</h3>
    <p>Either token is expired or code is wrong.</p>
    <p>Please return to the mainpage to try again.</p>
    <button onclick="redirect()">Back</button>
  </div>
</div>

<script>
  const inputs = document.querySelectorAll(".otp");

  inputs.forEach((input, index) => {
    input.addEventListener("input", () => {
      if (!/^[0-9]$/.test(input.value)) {
        input.value = "";
        return;
      }
      if (index < inputs.length - 1) {
        inputs[index + 1].focus();
      }
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !input.value && index > 0) {
        inputs[index - 1].focus();
      }
    });

    input.addEventListener("paste", (e) => {
      e.preventDefault();
      const pasted = e.clipboardData.getData("text").replace(/\D/g, "");
      pasted.split("").forEach((char, i) => {
        if (inputs[index + i]) {
          inputs[index + i].value = char;
        }
      });
      const next = index + pasted.length;
      if (inputs[next]) inputs[next].focus();
    });
  });

  function send_code() {
    const otp = Array.from(inputs).map(i => i.value).join("");
    if (otp.length !== inputs.length) {
      alert("Please enter the full code");
      return;
    }

    document.getElementById("loading_img").style.display = "block";

    fetch("http://127.0.0.1:5002/final_register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ "code": otp, "token": "{{ token }}" })
    })
    .then(response => response.json())
    .then(data => {
      document.getElementById("loading_img").style.display = "none";
      document.getElementById("confirm_form").style.display = "none";
      if (data.message === "success") {
        document.getElementById("success").style.display = "flex";
      } else {
        document.getElementById("error").style.display = "flex";
      }
    })
    .catch(() => {
      document.getElementById("loading_img").style.display = "none";
      document.getElementById("confirm_form").style.display = "none";
      document.getElementById("error").style.display = "flex";
    });
  }

  function redirect() {
    window.location.href = "/";
  }
</script>
</body>
</html>
   """, token=token)  
# ------------------ CART ------------------

@app.route("/cart", methods=["POST"])
def cart():
    print("Cart accessed from IP:", get_ip())
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON"}), 400
    
    token = data.get("token")
    if not token:
        return jsonify({"message": "Missing token"}), 403
    print(token)

    try:
        payload = serializer.loads(token, salt=TOKEN_SALT, max_age=3600)
        email = payload["email"]

        with tokendb.connect() as conn:
            original_token = conn.execute(
                text("SELECT cart_token FROM cart_token_tbl WHERE email=:email"),
                {"email": email}
            ).fetchone()

        if not original_token or original_token[0] != token:
            return jsonify({"message": "Invalid token. Either another device is using this account or the token is expired."}), 403

    except (BadSignature, SignatureExpired):
        return jsonify({"message": "Invalid token"}), 403

    action = data["query"]
    product = data.get("product_name")
    quantity = int(data.get("quantity", 1))

    if action == "select":
        with cartdb.begin() as conn:
         row = conn.execute(text("SELECT cart_json FROM cart_one_tbl WHERE email=:email"),
                           {"email": email}).fetchone()
         cart = json.loads(row[0]) if row and row[0] else {}
        return jsonify(cart)


    with productdb.connect() as con:
        pq = con.execute(text("SELECT quantity FROM products_tbl WHERE name=:name"),
                         {"name": product}).fetchone()
        print(pq[0])
        if not pq:
          return jsonify({"message": "Product not found"}), 404

        product_qty = pq[0]

        if product_qty <= 0:
           return jsonify({"message": "Out of stock"}), 400

    with cartdb.begin() as conn:
        row = conn.execute(text("SELECT cart_json FROM cart_one_tbl WHERE email=:email"),
                           {"email": email}).fetchone()
        cart = json.loads(row[0]) if row and row[0] else {}

        if action == "insert":
            cart[product] = min(max(1, quantity), product_qty)

        elif action == "add":
            print(cart.get(product, 0) + 1, product_qty)
            if cart.get(product, 0) + 1 > product_qty:
                return jsonify({"message": "Maximum products."})
            cart[product] = cart.get(product, 0) + 1

        elif action == "minus":
            if cart.get(product, 0) > 1:
                cart[product] -= 1
            else:
                cart.pop(product, None)

        elif action == "delete":
            cart.pop(product, None)

        conn.execute(text("UPDATE cart_one_tbl SET cart_json=:cart WHERE email=:email"),
                     {"cart": json.dumps(cart), "email": email})

    return jsonify({"message": "success"})

# ------------------ RESET PASSWORD ------------------

@app.route("/reset_id", methods=["POST"])
def get_reset_token():
    email = request.json.get("email")
    if not email:
        return {"message": "no email found"}

    token = generate_token_reset()
    collections.insert_one({
        "token": token,
        "email": email,
        "expires_at": datetime.utcnow() + timedelta(minutes=15)
    })

    response = req.post("https://script.google.com/macros/s/AKfycbxhZDpNfzDXMd5uivyp0jWEyMnD80AEUaa0O3yDxDQiaqR7KcgmhVpT8Sg6AadKMFwAlg/exec", json={"email": email, "token": token})
    print(response.text)
    return {"message": "success"}

@app.route("/reset", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        token_post = request.form.get("token")
        email = request.form.get("email")
        password = request.form.get("password")

        if not check_new_password(password):
            return "Invalid password", 400

        user = collections_post.find_one({"token_post": token_post, "email_post": email})
        if not user:
            return "Invalid or expired token", 400

        with clientdb.begin() as conn:
            conn.execute(text("UPDATE client_tbl SET password_hashed=:p WHERE email=:e"),
                         {"p": hash_password(password), "e": email})

        collections_post.delete_one({"_id": user["_id"]})
        return "<h3>Password reset completed</h3>"

    token = request.args.get("token_id")
    if not check_token_reset(token):
        return "<h3>Invalid or expired token</h3>", 400

    user = collections.find_one({"token": token})
    if not user:
        return "<h3>Invalid or expired token</h3>", 400

    new_token = secrets.token_urlsafe(32)
    collections_post.insert_one({
        "token_post": new_token,
        "email_post": user["email"],
        "expires_at": datetime.utcnow() + timedelta(minutes=15)
    })
    collections.delete_one({"_id": user["_id"]})

    return render_template_string("""
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Reset Password</title>
    </head>
    <body>
     <div id="reset_password_container">
    <div>
        <h1>Reset password</h1>
        <p>Enter your new password.</p>
        <form method="POST">
          <label for="">Password</label>
          <br>
          <input type="password" placeholder="New password" name="password">
          <input type="text" name="email" value={{email}} hidden>
          <input type="text" name="token" value={{token}} hidden>
          <br>
          <button id="send_button" type="submit">Reset</button>
        </form>
    </div>
</div>

<style>
    #reset_password_container {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        height: 100%;
        background: transparent;
        position: absolute;
        top: 0;
        left: 0;
    }

    #reset_password_container>div {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 10px;
        border: 1px solid rgb(195, 197,200);
        border-radius: 5px;
        width: 80%;
        padding: 10px;
    }

    label {
        color: rgb(195, 197,200);
        font-size: 15px;
    }

    #send_button {
        background-color: blue;
        color: white;
        font-size: 17px;
        padding: 10px;
    }

    #close_button {
        background-color: red;
        color: white;
        font-size: 20px;
        padding: 10px;
    }

    input {
        padding: 8px;
        border: 1px solid rgb(195, 197,200);
        border-radius: 5px;
    }
</style>
</body>
   """, email=user["email"], token=new_token)

# ------------------ DELETE ACCOUNT ------------------

@app.route("/delete_account", methods=["POST"])
def delete_account():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    with clientdb.connect() as conn:
        original = conn.execute(
            text("SELECT password_hashed FROM client_tbl WHERE email=:email"),
            {"email": email}
        ).fetchone()

    if not original:
        return jsonify({"message": "incorrect password"}), 401

    try:
        verify_password(original[0], password)
    except VerifyMismatchError:
        return jsonify({"message": "incorrect password"}), 401

    with clientdb.begin() as conn:
        conn.execute(text("DELETE FROM client_tbl WHERE email=:email"), {"email": email})
    with tokendb.begin() as conn:
        conn.execute(text("DELETE FROM cart_token_tbl WHERE email=:email"), {"email": email})
    with cartdb.begin() as conn:
        conn.execute(text("DELETE FROM cart_tbl WHERE email=:email"), {"email": email})

    return jsonify({"message": "success"})


@app.route("/product", methods=["GET"])
def index():
    if (request.method == "GET"):
        return jsonify({"products": product_list})
    else:
        return "Method not allowed"
    

dashboard_ready = False
@app.route("/dashboard_ready", methods=["POST"])
async def dashboard_ready_endpoint():
    global dashboard_ready

    data = request.get_json()
    if data.get("status") == "ready":
        dashboard_ready = True
        print("Dashboard is ready. Sending orders...")
        asyncio.create_task(send_orders())

    return {"message": "acknowledged"}


# ------------------------
# Send orders after ready
# ------------------------
async def send_orders(order_json):
    async with httpx.AsyncClient() as client:

        while dashboard_ready:
            order_data = order_json

            await client.post(
                "http://localhost:8000/new_order",
                json=order_data
            )

            print("Sent order:", order_data)
    

# ---------------- ORDER FIRST ----------------

@app.route("/order_first", methods=["POST"])
@limiter.limit("10/minute")
def order_first():
    data = request.get_json()
    if not data or "order_items" not in data:
        return jsonify({"message": "Invalid JSON"}), 400

    token = generate_token()
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    total_sub = 0
    shipping_fee = 10
    total = 0
    items = []

    with productdb.begin() as conn:
        for name, qty in data["order_items"]:
            name = bleach.clean(name)
            qty = int(qty)
            if qty <= 0:
                return jsonify({"message": f"Quantity of {name} cannot be less than or equal to 0."}), 400

            row = conn.execute(
                text("SELECT quantity, price FROM products_tbl WHERE name=:n FOR UPDATE"),
                {"n": name}
            ).fetchone()

            if not row:
                return jsonify({"message": f"Counldn't find {name}."}), 404

            stock, price = row

            with reservedb.connect() as reservedb_conn:
             reserved = reservedb_conn.execute(
                text("""
                    SELECT COALESCE(SUM(qty),0)
                    FROM stock_reservation
                    WHERE product_name=:n AND expires_at > NOW()
                """),
                {"n": name}
            ).scalar()

             if stock - reserved < qty:
                return jsonify({"message": f"Quantity of {name} you have ordered is more than our available stock."}), 400

             reservedb_conn.execute(
                text("""
                    INSERT INTO stock_reservation
                    (token, product_name, qty, expires_at)
                    VALUES (:t, :n, :q, :e)
                """),
                {"t": token, "n": name, "q": qty, "e": expires_at}
            )

            img = product_data.get(name, "")
            sub = float(price) * qty
            total_sub += sub
            items.append([name, qty, sub, img])

    total = total_sub + shipping_fee
    with order_cache_db.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO order_cache_tbl (token, cached_items, payment_status)
                VALUES (:t, :c, :p)
            """),
            {"t": token, "c": json.dumps({"order_json": items, "total": total}), "p":"PENDING"}
        )

    return jsonify({"token": token, "order_list": items, "shipping_fee": str(shipping_fee), "total": str(total), "price": str(total_sub)})

# ---------------- RENDER ORDER ----------------

@app.route("/render_order", methods=["POST"])
def render_order():
    data = request.get_json()
    token = data.get("token")

    if not check_token(token):
        return jsonify({"message": "Invalid or expired token"}), 403

    with order_cache_db.begin() as conn:
        row = conn.execute(
            text("""
                SELECT cached_items
                FROM order_cache_tbl
                WHERE token=:t
                FOR UPDATE
            """),
            {"t": token}
        ).fetchone()

        if not row:
            return jsonify({"message": "Invalid token"}), 403
        
    cache_data = json.loads(row["cached_items"])
    total = cache_data["total"]

    order_id = secrets.token_urlsafe(20)

    for k in ("house_number", "city", "state", "postcode", "neighbourhood", "street", "payment_method"):
        value = bleach.clean(data["address"][k])
        data["address"][k] = value
        if k not in data["address"]:
            return jsonify({"message": "Missing address field"}), 400
        if k == "state" and data["address"][k] not in malaysia_states_and_federal_territories:
              return jsonify({"message": "Your given state is unavailable in Malaysia."})
        if k == "postcode":
            if not check_postcode(data["address"][k]):
                return jsonify({"message": "Your given postcode is unavailable in Malaysia."})

    if not is_valid_email(data["email"]):
        return jsonify({"message": "Your given email is not valid."})
    
    if not is_valid_phone(data["phone_no"]):
        return jsonify({"message": "Your given phone number is not valid."})
    

    payload = {
        "collection_id": os.environ["BILLPLZ_COLLECTION_ID"],
        "email": data["email"],
        "name": "Customer",
        "amount": int(total * 100),
        "callback_url": "https://yourdomain.com/callback",
        "description": "Order payment"
    }

    r = requests.post(
        "https://www.billplz.com/api/v3/bills",
        auth=(BILLPLZ_API_KEY, ""),
        data=payload,
        timeout=10
    )
    r.raise_for_status()

    bill = r.json()

    with orderdb.begin() as conn:
        conn.execute(
            text("""
                UPDATE order_cache_tbl SET 
                order_id=:i, email=:e, phone_no=:p, address=:a,billplz_id=:bz WHERE token =:t
            """),
            {
                "i": order_id,
                "e": data["email"],
                "p": data["phone_no"],
                "a": json.dumps(data["address"], indent=4),
                "bz": bill["id"],
                "t": token
            }
        )

    return jsonify({"message": "success", "order_id": order_id, "link": bill["url"]})

# ---------------- CALLBACK ----------------

@app.route("/callback", methods=["POST"])
@limiter.limit("30/minute")
def callback():
    d = request.form.to_dict()

    signing = (
        f"billplz[id]{d.get('billplz[id]')}|"
        f"billplz[paid]{d.get('billplz[paid]')}|"
        f"billplz[paid_at]{d.get('billplz[paid_at]')}|"
        f"billplz[paid_amount]{d.get('billplz[paid_amount]')}"
    )

    sig = hmac.new(
        BILLPLZ_API_KEY.encode(),
        signing.encode(),
        hashlib.sha256
    ).hexdigest()

    if sig != d.get("billplz[x_signature]"):
        abort(403)

    with orderdb.begin() as conn:
        row = conn.execute(
            text("""
                SELECT order_id, email, phone, order_items, address, token, payment_status
                FROM order_cache_tbl
                WHERE billplz_id=:b
                FOR UPDATE
            """),
            {"b": d["billplz[id]"]}
        ).fetchone()

        if not row:
            abort(404)

        order_id, email, phone, items_json, address_json, token, payment_status = row

        items = json.loads(items_json)
        address = json.loads(address_json)

        if d.get("billplz[paid]") in ("true", "1"):
            if payment_status == "PAID": pass
            with orderdb.begin() as conn:
             row = conn.execute(
             text("""
                UPDATE order_cache_tbl SET payment_status=:p
                WHERE billplz_id=:b
             """),
             {"p": "PAID", "b": d["billplz[id]"]}
            )
            with productdb.begin() as p:
                for name, qty in items.items():
                    p.execute(
                        text("""
                            UPDATE products_tbl
                            SET quantity = quantity - :q
                            WHERE name=:n
                        """),
                        {"q": qty, "n": name}
                    )
                p.execute(
                    text("DELETE FROM stock_reservation WHERE token=:t"),
                    {"t": token}
                )

            text = ""
            for name,qty,_,_ in items_json.items():
              text += f"{qty} {name} \n"

            location = ""
            for x,y in address.items():
              location += f"{y} : {x} \n"

            #sheet_tng.append_row([order_id, email, phone, text, location])
            print("payment successful.")
        else:
            print("Payment failed.")
            return "Payment failed"

    return "OK", 200

# ---------------- CALLBACK ----------------

@app.route("/fetch_cart", methods=["POST"])
@limiter.limit("30/minute")
def cart():
   data = request.json()
   if data == None:
      return jsonify({"message": "Missing token and email"})
   
   token = data.get("token")
   if not token:
        return jsonify({"message": "Missing token"}), 403
   print(token)

   try:
        payload = serializer.loads(token, salt=TOKEN_SALT, max_age=3600)
        email = payload["email"]

        with tokendb.connect() as conn:
            original_token = conn.execute(
                text("SELECT cart_token FROM cart_token_tbl WHERE email=:email"),
                {"email": email}
            ).fetchone()

        if not original_token or original_token[0] != token:
            return jsonify({"message": "Invalid token. Either another device is using this account or the token is expired."}), 403

   except (BadSignature, SignatureExpired):
        return jsonify({"message": "Invalid token"}), 403
   
   cartdata = None
   try: 
     with cartdb.connect() as cart:
        cartdata = cart.execute(text("SELECT cart_json FROM cart_one_tbl WHERE email=:email"), {"email": email}).fetchone()
        cartdata2 = json.loads(cartdata)
     with productdb.connect() as conn:
      items = conn.execute(text("SELECT name, quantity FROM products_tbl"))
      list_product_name = []
      for x in items:
         list_product_name.append(x[0])
      for product_name,qty in cartdata2:
         for x in items:
            if product_name not in list_product_name: del cartdata2[product_name]
            if product_name == x[0]:
               if qty > x[1]:
                  del cartdata2[product_name]

      if (json.dumps(cartdata2) != cartdata):
         if cartdata2 == None: 
            cartdata2 = {}
         with cartdb.begin() as cart:
          cart.execute(text("UPDATE cart_one_tbl SET cart_json=:cart WHERE email=:email"),
                     {"cart": json.dumps(cartdata2), "email": email})
   except Exception as e:
        print(e)
   

if __name__ == "__main__":
    app.run(debug=True, port=5003,host="0.0.0.0")

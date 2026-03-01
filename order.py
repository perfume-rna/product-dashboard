
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
                "bz": "ioooi",
                "t": token
            }
        )

    return jsonify({"message": "success", "order_id": order_id, "link": bill["url"]})



# ---------------- CALLBACK ----------------

@app.route("/callback", methods=["POST"])
@limiter.limit("30/minute")
def callback():
    with orderdb.begin() as conn:
        row = conn.execute(
            text("""
                SELECT order_id, email, phone, order_items, address, token, payment_status
                FROM order_cache_tbl
                WHERE billplz_id=:b
                FOR UPDATE
            """),
            {"b": "ioooi"}
        ).fetchone()

        if not row:
            abort(404)

        order_id, email, phone, items_json, address_json, token, payment_status = row

        items = json.loads(items_json)
        address = json.loads(address_json)

        if payment_status == "PAID": pass

        with orderdb.begin() as conn:
             row = conn.execute(
             text("""
                UPDATE order_cache_tbl SET payment_status=:p
                WHERE billplz_id=:b
             """),
             {"p": "PAID", "b": "hello"}
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

        print(text)
        print(location)

        sheet_tng.append_row([order_id, email, phone, text, location])
        print("payment successful.")
        

    return "OK", 200

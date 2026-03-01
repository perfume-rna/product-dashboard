from flask import Flask, jsonify, request, render_template_string, abort
from flask_limiter import Limiter
from flask_cors import CORS
from sqlalchemy import create_engine, text

app = Flask(__name__)
CORS(app)
limiter = Limiter(app, key_func=lambda: request.remote_addr)
engine = create_engine('sqlite:///orders.db')
@app.route('/dashboard')
@limiter.limit("5 per minute")
def dashboard():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT order_id, items, completed FROM orders"))
        orders = [(row['order_id'], row['items'].split(','), row['completed']) for row in result]
    return render_template_string(DASHBOARD_TEMPLATE, orders=orders)
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Agong Perfume Dashboard</title>
</head>
<body>
    <h2 style="text-align: center;">Agong Perfume Dashboard</h2>
    <div>
        <table>
            <tr id="header_row">
                <td>Number</td>
                <td>order id</td>
                <td>order items</td>
                <td>completed</td>
            </tr>
            {% for order in orders %}
            <tr>
                <td>{{index(order) +1}}</td>
                <td>{{order[0]}}</td>
                <td>
                    <ul>
                        {% for item in order[1] %}
                        <li>{{item}}</li>
                        {% endfor %}
                    </ul>
                </td>
                <td id="boolean_{{order[0]}}" class="item_boolean">
                    <input type="checkbox" id="complete_{{order[0]}}" onchange="boolean_completed({{order[0]}})" value="{{order[2]}}"/>
                </td>
            </tr>
        </table>
    </div>
</body>
<script>
    function boolean_completed(order_id) {
        const checkbox = document.getElementById(`complete_${order_id}`);
        const isChecked = checkbox.checked;
        fetch("/update_order_status", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ "order_id": order_id, "completed": isChecked })
        })
        .then(response => response.json())
        .then(data => {
            console.log("Order status updated:", data);
            document.getElementById(`complete_${order_id}`).value = data.completed;
            if (data.completed == "true") {
                document.getElementById(`complete_${order_id}`).checked = true;
            } else {
                document.getElementById(`complete_${order_id}`).checked = false;
            }
        })
        .catch(error => {
            console.error("Error updating order status:", error);
        });
    };
</script>
<style>
    table, th, td {
        border: 1px solid black;
        border-collapse: collapse;
        padding: 10px;
    }

    #header_row {
        background-color: lightgrey;
    }

    table {
        width: 100%;
        margin: auto;
    }

    .item_boolean {
        text-align: center;
    }

    #header_row > td {
        font-weight: bold;
        background: linear-gradient(to right, #2F3A73, #C48FB3);
        padding: 12px;
        color: white;
    }
    
    input[type="checkbox"] {
    width: 20px;
    height: 20px;
}
</style>
</html>
"""

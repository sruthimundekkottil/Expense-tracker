from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash
from db import get_conn

app = Flask(__name__)

def json_error(message, status=400, details=None):
    payload = {"success": False, "error": {"message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), status

def run_query(query, params=None, fetchone=False, commit=False):
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params or {})
        data = None
        if commit:
            conn.commit()
        else:
            data = cur.fetchone() if fetchone else cur.fetchall()
        last_id = cur.lastrowid
        cur.close()
        return data, last_id
    finally:
        conn.close()

def build_update_set(allowed_keys, payload):
    fields = []
    values = {}
    for k in allowed_keys:
        if k in payload:
            fields.append(f"{k} = %({k})s")
            values[k] = payload[k]
    return ", ".join(fields), values

@app.errorhandler(404)
def not_found(_):
    return json_error("Resource not found", 404)

@app.errorhandler(405)
def method_not_allowed(_):
    return json_error("Method not allowed", 405)

@app.errorhandler(500)
def internal_error(e):
    return json_error("Internal server error", 500, str(e))

@app.get("/users")
def list_users():
    rows, _ = run_query("SELECT user_id, username, email, created_at FROM users ORDER BY user_id DESC")
    return jsonify({"success": True, "data": rows})

@app.get("/users/<int:user_id>")
def get_user(user_id):
    row, _ = run_query(
        "SELECT user_id, username, email, created_at FROM users WHERE user_id=%(user_id)s",
        {"user_id": user_id}, fetchone=True
    )
    if not row:
        return json_error("User not found", 404)
    return jsonify({"success": True, "data": row})

@app.post("/users")
def create_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    email = data.get("email")
    password = data.get("password") or data.get("password_hash")
    if not all([username, email, password]):
        return json_error("Missing required fields: username, email, password")
    password_hash = data.get("password_hash") or generate_password_hash(password)
    try:
        _, last_id = run_query(
            "INSERT INTO users (username, email, password_hash) VALUES (%(username)s, %(email)s, %(password_hash)s)",
            {"username": username, "email": email, "password_hash": password_hash},
            commit=True
        )
    except Exception as e:
        return json_error("Failed to create user", 400, str(e))
    row, _ = run_query("SELECT user_id, username, email, created_at FROM users WHERE user_id=%(id)s", {"id": last_id}, fetchone=True)
    return jsonify({"success": True, "data": row}), 201

@app.put("/users/<int:user_id>")
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    if "password" in data and "password_hash" not in data:
        data["password_hash"] = generate_password_hash(data["password"])
    set_clause, values = build_update_set(["username", "email", "password_hash"], data)
    if not set_clause:
        return json_error("No valid fields to update")
    values["user_id"] = user_id
    try:
        _, _ = run_query(f"UPDATE users SET {set_clause} WHERE user_id=%(user_id)s", values, commit=True)
    except Exception as e:
        return json_error("Failed to update user", 400, str(e))
    return get_user(user_id)

@app.delete("/users/<int:user_id>")
def delete_user(user_id):
    _, _ = run_query("DELETE FROM users WHERE user_id=%(user_id)s", {"user_id": user_id}, commit=True)
    return jsonify({"success": True, "data": {"deleted_id": user_id}})

@app.get("/admins")
def list_admins():
    rows, _ = run_query("SELECT admin_id, username FROM admin ORDER BY admin_id DESC")
    return jsonify({"success": True, "data": rows})

@app.get("/admins/<int:admin_id>")
def get_admin(admin_id):
    row, _ = run_query("SELECT admin_id, username FROM admin WHERE admin_id=%(id)s", {"id": admin_id}, fetchone=True)
    if not row:
        return json_error("Admin not found", 404)
    return jsonify({"success": True, "data": row})

@app.post("/admins")
def create_admin():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password") or data.get("password_hash")
    if not all([username, password]):
        return json_error("Missing required fields: username, password")
    password_hash = data.get("password_hash") or generate_password_hash(password)
    try:
        _, last_id = run_query(
            "INSERT INTO admin (username, password_hash) VALUES (%(username)s, %(password_hash)s)",
            {"username": username, "password_hash": password_hash},
            commit=True
        )
    except Exception as e:
        return json_error("Failed to create admin", 400, str(e))
    row, _ = run_query("SELECT admin_id, username FROM admin WHERE admin_id=%(id)s", {"id": last_id}, fetchone=True)
    return jsonify({"success": True, "data": row}), 201

@app.put("/admins/<int:admin_id>")
def update_admin(admin_id):
    data = request.get_json(silent=True) or {}
    if "password" in data and "password_hash" not in data:
        data["password_hash"] = generate_password_hash(data["password"])
    set_clause, values = build_update_set(["username", "password_hash"], data)
    if not set_clause:
        return json_error("No valid fields to update")
    values["admin_id"] = admin_id
    try:
        _, _ = run_query(f"UPDATE admin SET {set_clause} WHERE admin_id=%(admin_id)s", values, commit=True)
    except Exception as e:
        return json_error("Failed to update admin", 400, str(e))
    return get_admin(admin_id)

@app.delete("/admins/<int:admin_id>")
def delete_admin(admin_id):
    _, _ = run_query("DELETE FROM admin WHERE admin_id=%(id)s", {"id": admin_id}, commit=True)
    return jsonify({"success": True, "data": {"deleted_id": admin_id}})

@app.get("/categories")
def list_categories():
    user_id = request.args.get("user_id", type=int)
    if user_id:
        rows, _ = run_query(
            "SELECT category_id, user_id, name, type FROM categories WHERE user_id=%(user_id)s ORDER BY category_id DESC",
            {"user_id": user_id}
        )
    else:
        rows, _ = run_query("SELECT category_id, user_id, name, type FROM categories ORDER BY category_id DESC")
    return jsonify({"success": True, "data": rows})

@app.get("/categories/<int:category_id>")
def get_category(category_id):
    row, _ = run_query(
        "SELECT category_id, user_id, name, type FROM categories WHERE category_id=%(id)s",
        {"id": category_id}, fetchone=True
    )
    if not row:
        return json_error("Category not found", 404)
    return jsonify({"success": True, "data": row})

@app.post("/categories")
def create_category():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    name = data.get("name")
    type_ = data.get("type")
    if not all([user_id, name, type_]) or type_ not in ("expense", "income"):
        return json_error("Missing required fields or invalid type. type must be 'expense' or 'income'")
    try:
        _, last_id = run_query(
            "INSERT INTO categories (user_id, name, type) VALUES (%(user_id)s, %(name)s, %(type)s)",
            {"user_id": user_id, "name": name, "type": type_},
            commit=True
        )
    except Exception as e:
        return json_error("Failed to create category", 400, str(e))
    return get_category(last_id)

@app.put("/categories/<int:category_id>")
def update_category(category_id):
    data = request.get_json(silent=True) or {}
    if "type" in data and data["type"] not in ("expense", "income"):
        return json_error("Invalid type. Must be 'expense' or 'income'")
    set_clause, values = build_update_set(["user_id", "name", "type"], data)
    if not set_clause:
        return json_error("No valid fields to update")
    values["category_id"] = category_id
    try:
        _, _ = run_query(f"UPDATE categories SET {set_clause} WHERE category_id=%(category_id)s", values, commit=True)
    except Exception as e:
        return json_error("Failed to update category", 400, str(e))
    return get_category(category_id)

@app.delete("/categories/<int:category_id>")
def delete_category(category_id):
    _, _ = run_query("DELETE FROM categories WHERE category_id=%(id)s", {"id": category_id}, commit=True)
    return jsonify({"success": True, "data": {"deleted_id": category_id}})

@app.get("/transactions")
def list_transactions():
    params = {}
    clauses = []
    for key in ("user_id", "category_id"):
        v = request.args.get(key, type=int)
        if v is not None:
            clauses.append(f"{key}=%({key})s")
            params[key] = v
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows, _ = run_query(
        f"""SELECT transaction_id, user_id, category_id, amount, description, transaction_date
            FROM transactions {where} ORDER BY transaction_date DESC, transaction_id DESC""",
        params or None
    )
    return jsonify({"success": True, "data": rows})

@app.get("/transactions/<int:transaction_id>")
def get_transaction(transaction_id):
    row, _ = run_query(
        "SELECT transaction_id, user_id, category_id, amount, description, transaction_date FROM transactions WHERE transaction_id=%(id)s",
        {"id": transaction_id}, fetchone=True
    )
    if not row:
        return json_error("Transaction not found", 404)
    return jsonify({"success": True, "data": row})

@app.post("/transactions")
def create_transaction():
    data = request.get_json(silent=True) or {}
    required = ["user_id", "amount", "transaction_date"]
    if not all(k in data for k in required):
        return json_error("Missing required fields: user_id, amount, transaction_date")
    try:
        _, last_id = run_query(
            """INSERT INTO transactions (user_id, category_id, amount, description, transaction_date)
               VALUES (%(user_id)s, %(category_id)s, %(amount)s, %(description)s, %(transaction_date)s)""",
            {
                "user_id": data.get("user_id"),
                "category_id": data.get("category_id"),
                "amount": data.get("amount"),
                "description": data.get("description"),
                "transaction_date": data.get("transaction_date"),
            },
            commit=True
        )
    except Exception as e:
        return json_error("Failed to create transaction", 400, str(e))
    return get_transaction(last_id)

@app.put("/transactions/<int:transaction_id>")
def update_transaction(transaction_id):
    data = request.get_json(silent=True) or {}
    set_clause, values = build_update_set(
        ["user_id", "category_id", "amount", "description", "transaction_date"], data
    )
    if not set_clause:
        return json_error("No valid fields to update")
    values["transaction_id"] = transaction_id
    try:
        _, _ = run_query(f"UPDATE transactions SET {set_clause} WHERE transaction_id=%(transaction_id)s", values, commit=True)
    except Exception as e:
        return json_error("Failed to update transaction", 400, str(e))
    return get_transaction(transaction_id)

@app.delete("/transactions/<int:transaction_id>")
def delete_transaction(transaction_id):
    _, _ = run_query("DELETE FROM transactions WHERE transaction_id=%(id)s", {"id": transaction_id}, commit=True)
    return jsonify({"success": True, "data": {"deleted_id": transaction_id}})

@app.get("/budgets")
def list_budgets():
    params, clauses = {}, []
    for key in ("user_id", "category_id", "month_year"):
        v = request.args.get(key)
        if v is not None:
            clauses.append(f"{key}=%({key})s")
            params[key] = v if key != "category_id" else int(v)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows, _ = run_query(
        f"""SELECT budget_id, user_id, category_id, limit_amount, month_year
            FROM budgets {where} ORDER BY budget_id DESC""",
        params or None
    )
    return jsonify({"success": True, "data": rows})

@app.get("/budgets/<int:budget_id>")
def get_budget(budget_id):
    row, _ = run_query(
        "SELECT budget_id, user_id, category_id, limit_amount, month_year FROM budgets WHERE budget_id=%(id)s",
        {"id": budget_id}, fetchone=True
    )
    if not row:
        return json_error("Budget not found", 404)
    return jsonify({"success": True, "data": row})

@app.post("/budgets")
def create_budget():
    data = request.get_json(silent=True) or {}
    if "user_id" not in data:
        return json_error("Missing required field: user_id")
    try:
        _, last_id = run_query(
            """INSERT INTO budgets (user_id, category_id, limit_amount, month_year)
               VALUES (%(user_id)s, %(category_id)s, %(limit_amount)s, %(month_year)s)""",
            {
                "user_id": data.get("user_id"),
                "category_id": data.get("category_id"),
                "limit_amount": data.get("limit_amount"),
                "month_year": data.get("month_year"),
            },
            commit=True
        )
    except Exception as e:
        return json_error("Failed to create budget", 400, str(e))
    return get_budget(last_id)

@app.put("/budgets/<int:budget_id>")
def update_budget(budget_id):
    data = request.get_json(silent=True) or {}
    set_clause, values = build_update_set(
        ["user_id", "category_id", "limit_amount", "month_year"], data
    )
    if not set_clause:
        return json_error("No valid fields to update")
    values["budget_id"] = budget_id
    try:
        _, _ = run_query(f"UPDATE budgets SET {set_clause} WHERE budget_id=%(budget_id)s", values, commit=True)
    except Exception as e:
        return json_error("Failed to update budget", 400, str(e))
    return get_budget(budget_id)

@app.delete("/budgets/<int:budget_id>")
def delete_budget(budget_id):
    _, _ = run_query("DELETE FROM budgets WHERE budget_id=%(id)s", {"id": budget_id}, commit=True)
    return jsonify({"success": True, "data": {"deleted_id": budget_id}})

@app.get("/activity_logs")
def list_logs():
    params, clauses = {}, []
    user_id = request.args.get("user_id", type=int)
    if user_id is not None:
        clauses.append("user_id=%(user_id)s")
        params["user_id"] = user_id
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows, _ = run_query(
        f"SELECT log_id, user_id, action, log_time FROM activity_logs {where} ORDER BY log_time DESC, log_id DESC",
        params or None
    )
    return jsonify({"success": True, "data": rows})

@app.get("/activity_logs/<int:log_id>")
def get_log(log_id):
    row, _ = run_query(
        "SELECT log_id, user_id, action, log_time FROM activity_logs WHERE log_id=%(id)s",
        {"id": log_id}, fetchone=True
    )
    if not row:
        return json_error("Activity log not found", 404)
    return jsonify({"success": True, "data": row})

@app.post("/activity_logs")
def create_log():
    data = request.get_json(silent=True) or {}
    try:
        _, last_id = run_query(
            "INSERT INTO activity_logs (user_id, action) VALUES (%(user_id)s, %(action)s)",
            {"user_id": data.get("user_id"), "action": data.get("action")},
            commit=True
        )
    except Exception as e:
        return json_error("Failed to create activity log", 400, str(e))
    return get_log(last_id)

@app.put("/activity_logs/<int:log_id>")
def update_log(log_id):
    data = request.get_json(silent=True) or {}
    set_clause, values = build_update_set(["user_id", "action"], data)
    if not set_clause:
        return json_error("No valid fields to update")
    values["log_id"] = log_id
    try:
        _, _ = run_query(f"UPDATE activity_logs SET {set_clause} WHERE log_id=%(log_id)s", values, commit=True)
    except Exception as e:
        return json_error("Failed to update activity log", 400, str(e))
    return get_log(log_id)

@app.delete("/activity_logs/<int:log_id>")
def delete_log(log_id):
    _, _ = run_query("DELETE FROM activity_logs WHERE log_id=%(id)s", {"id": log_id}, commit=True)
    return jsonify({"success": True, "data": {"deleted_id": log_id}})

@app.get("/health")
def health():
    try:
        _, _ = run_query("SELECT 1")
        return jsonify({"success": True, "status": "ok"})
    except Exception as e:
        return json_error("DB connection failed", 500, str(e))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
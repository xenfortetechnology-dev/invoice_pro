from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)
DB = "instance/revolutionary_invoice.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/clients", methods=["GET"])
def get_clients():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM client")
    rows = cur.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/clients", methods=["POST"])
def add_client():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO client (name, contact_person, address, city)
        VALUES (?, ?, ?, ?)
    """, (
        data.get("name"),
        data.get("contact_person"),
        data.get("address"),
        data.get("city")
    ))
    conn.commit()
    conn.close()
    return jsonify({"msg": "Client added"})


@app.route("/clients/<int:id>", methods=["PUT"])
def update_client(id):
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE client
        SET name=?, contact_person=?, address=?, city=?
        WHERE id=?
    """, (
        data.get("name"),
        data.get("contact_person"),
        data.get("address"),
        data.get("city"),
        id
    ))
    conn.commit()
    conn.close()
    return jsonify({"msg": "Client updated"})


@app.route("/clients/<int:id>", methods=["DELETE"])
def delete_client(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM client WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"msg": "Client deleted"})


if __name__ == "__main__":
    app.run(debug=True)

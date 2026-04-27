import json
import os
import math
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import csv
import io

app = Flask(__name__)
CORS(app)

DATA_FILE = "patients.json"

# ---------- Chargement / Sauvegarde ----------
def load_patients():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return []

def save_patients(patients):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(patients, f, indent=2, ensure_ascii=False)

# ---------- Utilitaires ----------
def compute_imc(poids, taille):
    if poids and taille and taille > 0:
        return round(poids / ((taille / 100) ** 2), 1)
    return None

def compute_stats(values):
    if not values:
        return {}
    values_sorted = sorted(values)
    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    std = math.sqrt(variance)
    q1 = values_sorted[int(0.25 * n)]
    q2 = values_sorted[int(0.50 * n)]
    q3 = values_sorted[int(0.75 * n)]
    return {
        "count": n,
        "moyenne": round(mean, 2),
        "ecart_type": round(std, 2),
        "minimum": round(min(values), 2),
        "maximum": round(max(values), 2),
        "Q1": round(q1, 2),
        "Q2": round(q2, 2),
        "Q3": round(q3, 2)
    }

def pearson_corr(x, y):
    n = len(x)
    if n < 2:
        return 0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    den_x = sum((xi - mean_x) ** 2 for xi in x)
    den_y = sum((yi - mean_y) ** 2 for yi in y)
    if den_x == 0 or den_y == 0:
        return 0
    return round(num / math.sqrt(den_x * den_y), 4)

# ---------- Routes API ----------
@app.route("/api/patients", methods=["GET"])
def get_patients():
    patients = load_patients()
    return jsonify(patients)

@app.route("/api/patients", methods=["POST"])
def add_patient():
    data = request.json
    required = ["age", "sexe", "poids", "taille"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Le champ {field} est obligatoire"}), 400

    patients = load_patients()
    new_id = max([p["id"] for p in patients], default=0) + 1

    poids = float(data["poids"]) if data["poids"] else None
    taille = float(data["taille"]) if data["taille"] else None
    imc = compute_imc(poids, taille)

    pathologies = data.get("pathologies", [])
    if isinstance(pathologies, list):
        pathologies_str = ",".join(pathologies)
    else:
        pathologies_str = str(pathologies)

    patient = {
        "id": new_id,
        "nom": data.get("nom", ""),
        "age": int(data["age"]),
        "sexe": data["sexe"],
        "poids": poids,
        "taille": taille,
        "imc": imc,
        "glycemie": float(data["glycemie"]) if data.get("glycemie") else None,
        "pression_sys": int(data["pression_sys"]) if data.get("pression_sys") else None,
        "pression_dia": int(data["pression_dia"]) if data.get("pression_dia") else None,
        "pathologies": pathologies_str,
        "commune": data.get("commune", ""),
        "date_enregistrement": datetime.now().isoformat()
    }
    patients.append(patient)
    save_patients(patients)
    return jsonify({"message": "Patient ajouté", "id": new_id, "imc": imc}), 201

@app.route("/api/stats/descriptives", methods=["GET"])
def stats_descriptives():
    patients = load_patients()
    if not patients:
        return jsonify({"total": 0, "message": "Aucune donnée"})

    ages = [p["age"] for p in patients if p.get("age") is not None]
    poids = [p["poids"] for p in patients if p.get("poids")]
    tailles = [p["taille"] for p in patients if p.get("taille")]
    imcs = [p["imc"] for p in patients if p.get("imc")]
    glycemies = [p["glycemie"] for p in patients if p.get("glycemie")]
    press_sys = [p["pression_sys"] for p in patients if p.get("pression_sys")]
    press_dia = [p["pression_dia"] for p in patients if p.get("pression_dia")]

    result = {
        "total": len(patients),
        "age": compute_stats(ages),
        "poids": compute_stats(poids),
        "taille": compute_stats(tailles),
        "imc": compute_stats(imcs),
        "glycemie": compute_stats(glycemies),
        "pression": {
            "systolique": compute_stats(press_sys),
            "diastolique": compute_stats(press_dia)
        }
    }
    return jsonify(result)

@app.route("/api/correlation", methods=["GET"])
def correlation_matrix():
    patients = load_patients()
    if len(patients) < 3:
        return jsonify({"error": "Pas assez de données pour la matrice de corrélation"})

    variables = ["age", "imc", "glycemie", "pression_sys", "pression_dia"]
    filtered = []
    for p in patients:
        if all(p.get(v) is not None for v in variables):
            filtered.append(p)
    if len(filtered) < 3:
        return jsonify({"error": "Données insuffisantes pour la corrélation (valeurs manquantes)"})

    data = {v: [p[v] for p in filtered] for v in variables}
    matrix = []
    for v1 in variables:
        row = []
        for v2 in variables:
            corr = pearson_corr(data[v1], data[v2])
            row.append(corr)
        matrix.append(row)
    return jsonify({"variables": variables, "matrix": matrix})

@app.route("/api/export/csv", methods=["GET"])
def export_csv():
    patients = load_patients()
    if not patients:
        return "Aucune donnée à exporter", 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "nom", "age", "sexe", "poids", "taille", "imc", "glycemie",
                     "pression_sys", "pression_dia", "pathologies", "commune", "date_enregistrement"])
    for p in patients:
        writer.writerow([
            p.get("id", ""),
            p.get("nom", ""),
            p.get("age", ""),
            p.get("sexe", ""),
            p.get("poids", ""),
            p.get("taille", ""),
            p.get("imc", ""),
            p.get("glycemie", ""),
            p.get("pression_sys", ""),
            p.get("pression_dia", ""),
            p.get("pathologies", ""),
            p.get("commune", ""),
            p.get("date_enregistrement", "")
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='export_santedata.csv'
    )

# Route pour servir l'interface HTML (si placée dans le même dossier)
@app.route("/")
def serve_frontend():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Le fichier index.html n'est pas présent. Placez-le dans le même dossier que ce script.", 200

if __name__ == "__main__":
    app.run(debug=True, port=5000,host="0.0.0.0")

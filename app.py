from flask import Flask, request, jsonify, send_from_directory
import pandas as pd
import numpy as np
import joblib
import os
import datetime
import random

app = Flask(__name__, static_folder='static', static_url_path='')

# Load the saved model artifacts
model_path = 'model.pkl'
imputer_path = 'imputer.pkl'
feature_names_path = 'feature_names.pkl'

if os.path.exists(model_path) and os.path.exists(imputer_path) and os.path.exists(feature_names_path):
    model = joblib.load(model_path)
    imputer = joblib.load(imputer_path)
    feature_names = joblib.load(feature_names_path)
else:
    print("Warning: Model files not found. Please run train.py first.")
    model = None
    imputer = None
    feature_names = None

# Helper to clamp values
def clamp(val, min_v, max_v):
    return max(min_v, min(max_v, val))

# Helper to safely calculate stats
def get_stats(history_vals):
    if not history_vals:
        return 0.0, 0.0
    return float(np.mean(history_vals)), float(np.std(history_vals))

# Clinical indices calculation
def calculate_tvi(temp_history):
    # Temperature Variability Index
    # Scales 0 to 100 based on temperature SD over historical readings
    if len(temp_history) < 2:
        return 10.0
    _, std_val = get_stats(temp_history)
    tvi = min(100.0, std_val * 150.0)
    return round(tvi, 1)

def calculate_hsi(hr_history, hrv_history):
    # HRV Sepsis Index
    # Scales 0 to 100 based on HRV (lower hrv -> higher index/risk)
    if not hrv_history:
        return 10.0
    mean_hrv = np.mean(hrv_history)
    mean_hr = np.mean(hr_history) if hr_history else 140.0
    
    base_hsi = max(0.0, (65.0 - mean_hrv) * 2.0)
    hr_factor = clamp(mean_hr / 140.0, 0.7, 1.4)
    hsi = min(100.0, base_hsi * hr_factor)
    return round(hsi, 1)

def calculate_ois(spo2_history):
    # Oxygen Instability Score
    # Scales 0 to 100 based on mean SpO2 and SD
    if not spo2_history:
        return 10.0
    mean_spo2, std_spo2 = get_stats(spo2_history)
    
    desat_factor = max(0.0, 100.0 - mean_spo2) * 5.0
    variability_factor = std_spo2 * 10.0
    ois = min(100.0, desat_factor + variability_factor)
    return round(ois, 1)

def calculate_prs(gestational_age, birth_weight):
    # Prematurity Risk Score
    # Gestational Age Risk Score (0 to 50) based on categories
    if gestational_age < 28.0:
        ga_risk = 50.0  # Extremely Preterm (3.0x multiplier)
    elif gestational_age < 32.0:
        ga_risk = 37.5  # Very Preterm (2.5x multiplier)
    elif gestational_age < 34.0:
        ga_risk = 20.0  # Moderate Preterm (1.8x multiplier)
    elif gestational_age < 37.0:
        ga_risk = 7.5   # Late Preterm (1.3x multiplier)
    else:
        ga_risk = 0.0   # Term (1.0x multiplier)
        
    # Birth Weight Risk Score (0 to 50) based on categories
    if birth_weight < 1000.0:
        bw_risk = 50.0  # ELBW (Very High risk)
    elif birth_weight < 1500.0:
        bw_risk = 37.5  # VLBW (High risk)
    elif birth_weight < 2500.0:
        bw_risk = 25.0  # LBW (Moderate risk)
    elif birth_weight <= 4000.0:
        bw_risk = 0.0   # Normal (Baseline risk)
    else:
        bw_risk = 10.0  # Macrosomia (>4000g)
        
    prs = ga_risk + bw_risk
    return round(min(100.0, prs), 1)

def calculate_nss(hrv, spo2_history, temp_history, crp_history, wbc, gestational_age, birth_weight):
    # Composite NeoSepsis Risk Score (0 - 100)
    # Weights: HRV 25%, SpO2 Var 15%, Temp Instability 15%, CRP Trend 15%, WBC 10%, GA 10%, BW 10%
    
    # 1. HRV Score (max 25)
    hrv_score = 25.0 * (1.0 - clamp((hrv - 15.0) / 45.0, 0.0, 1.0))
    
    # 2. SpO2 Variability Score (max 15)
    if len(spo2_history) >= 2:
        _, spo2_sd = get_stats(spo2_history)
    else:
        spo2_sd = 1.0
    spo2_var_score = 15.0 * clamp(spo2_sd / 4.0, 0.0, 1.0)
    if spo2_history and spo2_history[-1] < 85.0:
        spo2_var_score = max(spo2_var_score, 12.0)
        
    # 3. Temp Instability Score (max 15)
    if len(temp_history) >= 2:
        delta_temp = abs(temp_history[-1] - temp_history[0]) if len(temp_history) <= 6 else abs(temp_history[-1] - temp_history[-6])
        _, temp_sd = get_stats(temp_history)
        temp_inst_score = 15.0 * max(clamp(delta_temp / 1.0, 0.0, 1.0), clamp(temp_sd / 0.5, 0.0, 1.0))
    else:
        temp_inst_score = 5.0
        
    # 4. CRP Trend Score (max 15)
    latest_crp = crp_history[-1] if crp_history else 0.0
    if len(crp_history) >= 2:
        crp_rise = crp_history[-1] - crp_history[-2]
    else:
        crp_rise = 0.0
    
    if latest_crp < 5.0:
        crp_base = 0.0
    elif latest_crp <= 10.0:
        crp_base = 3.0
    elif latest_crp <= 20.0:
        crp_base = 6.0
    elif latest_crp <= 50.0:
        crp_base = 10.0
    else:
        crp_base = 15.0
        
    if crp_rise > 10.0:
        crp_trend_score = min(15.0, crp_base + 5.0)
    elif crp_rise > 5.0:
        crp_trend_score = min(15.0, crp_base + 3.0)
    else:
        crp_trend_score = crp_base
        
    # 5. WBC Score (max 10)
    if wbc < 5.0:
        wbc_score = 10.0
    elif wbc > 40.0:
        wbc_score = 10.0
    elif wbc >= 30.0:
        wbc_score = 7.0
    elif wbc < 9.0:
        wbc_score = 4.0
    else:
        wbc_score = 0.0
        
    # 6. Gestational Age Score (max 10) - precise allocation from multipliers
    if gestational_age < 28.0:
        ga_score = 10.0  # Extremely Preterm (3.0x risk)
    elif gestational_age < 32.0:
        ga_score = 7.5   # Very Preterm (2.5x risk)
    elif gestational_age < 34.0:
        ga_score = 4.0   # Moderate Preterm (1.8x risk)
    elif gestational_age < 37.0:
        ga_score = 1.5   # Late Preterm (1.3x risk)
    else:
        ga_score = 0.0   # Term (1.0x risk)
        
    # 7. Birth Weight Score (max 10) - precise allocation from categories
    if birth_weight < 1000.0:
        bw_score = 10.0  # ELBW
    elif birth_weight < 1500.0:
        bw_score = 7.5   # VLBW
    elif birth_weight < 2500.0:
        bw_score = 5.0   # LBW
    elif birth_weight <= 4000.0:
        bw_score = 0.0   # Normal
    else:
        bw_score = 2.0   # Macrosomia
        
    total_score = hrv_score + spo2_var_score + temp_inst_score + crp_trend_score + wbc_score + ga_score + bw_score
    return round(total_score, 1)

def recalculate_bed_scores(bed):
    history = bed["history"]
    if not history:
        return
    
    latest = history[-1]
    
    hr_history = [h["heart_rate_bpm"] for h in history]
    spo2_history = [h["spo2_percent"] for h in history]
    temp_history = [h["temperature_c"] for h in history]
    crp_history = [h["crp_mg_l"] for h in history]
    hrv_history = [h["hrv"] for h in history]
    
    wbc = latest["wbc\u10e9l"]
    ga = bed["gestational_age_weeks"]
    bw = bed["birth_weight_g"]
    hrv = latest["hrv"]
    
    # Calculate clinical indices
    bed["tvi"] = calculate_tvi(temp_history)
    bed["hsi"] = calculate_hsi(hr_history, hrv_history)
    bed["ois"] = calculate_ois(spo2_history)
    bed["prs"] = calculate_prs(ga, bw)
    bed["nss"] = calculate_nss(hrv, spo2_history, temp_history, crp_history, wbc, ga, bw)
    
    # Preterm Category Metadata
    if ga < 28.0:
        bed["ga_category"] = "Extremely Preterm"
        bed["ga_multiplier"] = "3.0x"
    elif ga < 32.0:
        bed["ga_category"] = "Very Preterm"
        bed["ga_multiplier"] = "2.5x"
    elif ga < 34.0:
        bed["ga_category"] = "Moderate Preterm"
        bed["ga_multiplier"] = "1.8x"
    elif ga < 37.0:
        bed["ga_category"] = "Late Preterm"
        bed["ga_multiplier"] = "1.3x"
    else:
        bed["ga_category"] = "Term"
        bed["ga_multiplier"] = "1.0x"
        
    # Birth Weight Category Metadata
    if bw < 1000.0:
        bed["bw_category"] = "ELBW"
    elif bw < 1500.0:
        bed["bw_category"] = "VLBW"
    elif bw < 2500.0:
        bed["bw_category"] = "LBW"
    elif bw <= 4000.0:
        bed["bw_category"] = "Normal"
    else:
        bed["bw_category"] = "Macrosomia"

    # Evaluate statuses for each vital
    latest_spo2 = latest["spo2_percent"]
    if latest_spo2 < 85.0:
        spo2_status = "CRITICAL_LOW"
    elif latest_spo2 < 90.0:
        spo2_status = "LOW"
    elif latest_spo2 <= 95.0:
        spo2_status = "TARGET"
    else:
        spo2_status = "HIGH"

    latest_temp = latest["temperature_c"]
    if latest_temp < 36.0:
        temp_status = "HYPOTHERMIA"
    elif latest_temp < 36.5:
        temp_status = "MILD_HYPO"
    elif latest_temp <= 37.5:
        temp_status = "NORMAL"
    elif latest_temp <= 38.0:
        temp_status = "ELEVATED"
    else:
        temp_status = "FEVER"

    latest_rr = latest["resp_rate_min"]
    if latest_rr < 30.0:
        rr_status = "APNEA"
    elif latest_rr <= 60.0:
        rr_status = "NORMAL"
    elif latest_rr <= 70.0:
        rr_status = "TACHYPNEA"
    else:
        rr_status = "DISTRESS"

    latest_crp = latest["crp_mg_l"]
    if latest_crp < 5.0:
        crp_status = "NORMAL"
    elif latest_crp <= 10.0:
        crp_status = "BORDERLINE"
    elif latest_crp <= 20.0:
        crp_status = "MILD_INFLAM"
    elif latest_crp <= 50.0:
        crp_status = "SIG_INFLAM"
    else:
        crp_status = "SEPSIS_SUSPICION"

    if wbc < 5.0:
        wbc_status = "LEUKOPENIA"
    elif wbc < 9.0:
        wbc_status = "LOW"
    elif wbc <= 30.0:
        wbc_status = "TYPICAL"
    elif wbc <= 40.0:
        wbc_status = "ELEVATED"
    else:
        wbc_status = "LEUKOCYTOSIS"

    bed["vital_statuses"] = {
        "spo2": spo2_status,
        "temp": temp_status,
        "rr": rr_status,
        "crp": crp_status,
        "wbc": wbc_status
    }

    # Run Random Forest ML model
    if model is not None and imputer is not None:
        try:
            input_dict = {
                "heart_rate_bpm": latest["heart_rate_bpm"],
                "spo2_percent": latest["spo2_percent"],
                "temperature_c": latest["temperature_c"],
                "resp_rate_min": latest["resp_rate_min"],
                "crp_mg_l": latest["crp_mg_l"],
                "wbc\u10e9l": wbc,
                "gestational_age_weeks": ga,
                "birth_weight_g": bw
            }
            df = pd.DataFrame([input_dict])
            df = df[feature_names]
            X = imputer.transform(df)
            ml_prob = float(model.predict_proba(X)[0, 1])
            bed["ml_risk_score"] = round(ml_prob * 100, 1)
        except Exception as e:
            print("ML prediction error for bed:", e)
            bed["ml_risk_score"] = 0.0
    else:
        bed["ml_risk_score"] = 0.0

    # Categorize clinical risk based on NSS (0-100)
    nss = bed["nss"]
    if nss <= 20.0:
        bed["risk_category"] = "Low Risk"
    elif nss <= 40.0:
        bed["risk_category"] = "Moderate Risk"
    elif nss <= 60.0:
        bed["risk_category"] = "High Risk"
    elif nss <= 80.0:
        bed["risk_category"] = "Very High Risk"
    else:
        bed["risk_category"] = "Critical Risk"
        
    # Generate visual/clinical alerts
    bed["alerts"] = []
    
    # SpO2 Alert
    if latest_spo2 < 85.0:
        bed["alerts"].append({"type": "danger", "message": f"Critical Hypoxemia (SpO₂: {latest_spo2}%)", "feature": "spo2"})
    elif latest_spo2 < 90.0:
        bed["alerts"].append({"type": "warning", "message": f"Low Oxygen Saturation (SpO₂: {latest_spo2}%)", "feature": "spo2"})
    elif latest_spo2 > 98.0 and ga < 37.0:
        bed["alerts"].append({"type": "info", "message": f"Hyperoxia Risk (SpO₂: {latest_spo2}% in Preterm)", "feature": "spo2"})
        
    # Temp Alert
    if latest_temp < 36.0:
        bed["alerts"].append({"type": "danger", "message": f"Severe Hypothermia (Temp: {latest_temp}°C)", "feature": "temp"})
    elif latest_temp < 36.5:
        bed["alerts"].append({"type": "warning", "message": f"Mild Hypothermia (Temp: {latest_temp}°C)", "feature": "temp"})
    elif latest_temp > 38.0:
        bed["alerts"].append({"type": "danger", "message": f"Fever Detected (Temp: {latest_temp}°C)", "feature": "temp"})
    elif latest_temp >= 37.6:
        bed["alerts"].append({"type": "warning", "message": f"Elevated Temperature (Temp: {latest_temp}°C)", "feature": "temp"})
        
    # Temperature Instability Alert
    if len(temp_history) >= 6:
        delta_temp_6h = abs(temp_history[-1] - temp_history[-6])
        if delta_temp_6h > 0.8:
            bed["alerts"].append({"type": "danger", "message": f"Temp Instability Alert (6h Delta: {round(delta_temp_6h, 2)}°C)", "feature": "temp"})
    elif len(temp_history) >= 2:
        delta_temp_6h = abs(temp_history[-1] - temp_history[0])
        if delta_temp_6h > 0.8:
            bed["alerts"].append({"type": "danger", "message": f"Temp Instability Alert (6h Delta: {round(delta_temp_6h, 2)}°C)", "feature": "temp"})
            
    # Respiratory Rate Alert
    if latest_rr > 70.0:
        bed["alerts"].append({"type": "danger", "message": f"Respiratory Distress Alert (RR: {latest_rr}/min)", "feature": "rr"})
    elif latest_rr > 60.0:
        bed["alerts"].append({"type": "warning", "message": f"Mild Tachypnea (RR: {latest_rr}/min)", "feature": "rr"})
    elif latest_rr < 30.0:
        bed["alerts"].append({"type": "danger", "message": f"Brady-respiration / Apnea Alert (RR: {latest_rr}/min)", "feature": "rr"})
        
    # CRP Alert
    if latest_crp > 50.0:
        bed["alerts"].append({"type": "danger", "message": f"Strong Sepsis Suspicion (CRP: {latest_crp} mg/L)", "feature": "crp"})
    elif latest_crp >= 20.0:
        bed["alerts"].append({"type": "warning", "message": f"Significant Inflammation (CRP: {latest_crp} mg/L)", "feature": "crp"})
        
    # CRP Trend Alert
    if len(crp_history) >= 3:
        crp_rise_2h = crp_history[-1] - crp_history[-3]
        crp_rise_1h = crp_history[-1] - crp_history[-2]
        if crp_rise_2h > 15.0 or crp_rise_1h > 10.0:
            bed["alerts"].append({"type": "danger", "message": f"CRP Trend Alert (CRP Trend ↑↑: +{round(max(crp_rise_2h, crp_rise_1h), 1)} mg/L)", "feature": "crp"})
    elif len(crp_history) >= 2:
        crp_rise = crp_history[-1] - crp_history[-2]
        if crp_rise > 10.0:
            bed["alerts"].append({"type": "danger", "message": f"CRP Trend Alert (CRP Trend ↑↑: +{round(crp_rise, 1)} mg/L)", "feature": "crp"})
            
    # WBC Alert
    if wbc < 5.0:
        bed["alerts"].append({"type": "danger", "message": f"High Sepsis Risk: Leukopenia (WBC: {wbc} ×10⁹/L)", "feature": "wbc"})
    elif wbc > 40.0:
        bed["alerts"].append({"type": "danger", "message": f"Severe Leukocytosis (WBC: {wbc} ×10⁹/L)", "feature": "wbc"})
    elif wbc >= 30.0:
        bed["alerts"].append({"type": "warning", "message": f"Elevated WBC (WBC: {wbc} ×10⁹/L)", "feature": "wbc"})
    elif wbc < 9.0:
        bed["alerts"].append({"type": "warning", "message": f"Low WBC (WBC: {wbc} ×10⁹/L)", "feature": "wbc"})

def generate_default_beds():
    now = datetime.datetime.now()
    
    # 12 hourly intervals
    timestamps = [(now - datetime.timedelta(hours=11-i)).isoformat() + "Z" for i in range(12)]
    
    beds = {
        "bed_01": {
            "id": "bed_01",
            "name": "Baby Emma",
            "gender": "Female",
            "gestational_age_weeks": 38.2,
            "birth_weight_g": 3200,
            "date_of_admission": (now - datetime.timedelta(days=2)).strftime("%Y-%m-%d"),
            "history": [
                {
                    "timestamp": timestamps[i],
                    "heart_rate_bpm": float(130 + (i % 3) * 2 + (i % 2) * -1),
                    "spo2_percent": float(96 + (i % 2)),
                    "temperature_c": float(36.7 + (i % 4) * 0.05),
                    "resp_rate_min": float(42 + (i % 3) * 2),
                    "crp_mg_l": float(1.8 + i * 0.05),
                    "wbc\u10e9l": float(12.5 - i * 0.05),
                    "hrv": float(55 + (i % 4) * 2)
                } for i in range(12)
            ]
        },
        "bed_02": {
            "id": "bed_02",
            "name": "Baby Noah",
            "gender": "Male",
            "gestational_age_weeks": 33.5,
            "birth_weight_g": 1850,
            "date_of_admission": (now - datetime.timedelta(days=4)).strftime("%Y-%m-%d"),
            "history": [
                {
                    "timestamp": timestamps[i],
                    "heart_rate_bpm": float(148 + (i % 4) * 3 - (i % 3) * 2),
                    "spo2_percent": float(92 + (i % 3)),
                    "temperature_c": float(36.4 - (i % 3) * 0.05 if i < 6 else 36.2 + (i % 3) * 0.05),
                    "resp_rate_min": float(54 + (i % 4) * 2),
                    "crp_mg_l": float(5.2 + i * 0.3),
                    "wbc\u10e9l": float(8.8 - i * 0.15),
                    "hrv": float(45 - (i % 3) * 1)
                } for i in range(12)
            ]
        },
        "bed_03": {
            "id": "bed_03",
            "name": "Baby Liam",
            "gender": "Male",
            "gestational_age_weeks": 29.0,
            "birth_weight_g": 1100,
            "date_of_admission": (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d"),
            "history": [
                {
                    "timestamp": timestamps[i],
                    "heart_rate_bpm": float(145 + i * 3.0),
                    "spo2_percent": float(94.0 - i * 0.55),
                    "temperature_c": float(36.8 + i * 0.1),
                    "resp_rate_min": float(48 + i * 2.2),
                    "crp_mg_l": float(4.0 + i * 3.1),
                    "wbc\u10e9l": float(10.0 - i * 0.53),
                    "hrv": float(50.0 - i * 2.5)
                } for i in range(12)
            ]
        }
    }
    
    for bed in beds.values():
        recalculate_bed_scores(bed)
        
    return beds

# Initialize in-memory active beds
active_beds = generate_default_beds()

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# REST API to get all beds
@app.route('/api/beds', methods=['GET'])
def get_beds():
    beds_summary = []
    for bid, bed in active_beds.items():
        latest = bed["history"][-1]
        beds_summary.append({
            "id": bed["id"],
            "name": bed["name"],
            "gender": bed["gender"],
            "gestational_age_weeks": bed["gestational_age_weeks"],
            "birth_weight_g": bed["birth_weight_g"],
            "date_of_admission": bed["date_of_admission"],
            "latest_vitals": latest,
            "nss": bed["nss"],
            "ml_risk_score": bed["ml_risk_score"],
            "risk_category": bed["risk_category"],
            "alerts_count": len(bed["alerts"]),
            "alerts": bed["alerts"],
            "ga_category": bed.get("ga_category"),
            "ga_multiplier": bed.get("ga_multiplier"),
            "bw_category": bed.get("bw_category"),
            "vital_statuses": bed.get("vital_statuses", {})
        })
    return jsonify(beds_summary)

# REST API to get specific bed details
@app.route('/api/beds/<bed_id>', methods=['GET'])
def get_bed_details(bed_id):
    if bed_id not in active_beds:
        return jsonify({"error": "Bed not found"}), 404
    return jsonify(active_beds[bed_id])

# REST API to record manual reading for a bed
@app.route('/api/beds/<bed_id>/record', methods=['POST'])
def record_vitals(bed_id):
    if bed_id not in active_beds:
        return jsonify({"error": "Bed not found"}), 404
    
    try:
        data = request.json
        required_fields = ['heart_rate_bpm', 'spo2_percent', 'temperature_c', 'resp_rate_min', 'crp_mg_l', 'wbc_l', 'hrv']
        missing = [f for f in required_fields if f not in data]
        if missing:
            return jsonify({"error": f"Missing parameters: {', '.join(missing)}"}), 400
            
        now = datetime.datetime.now().isoformat() + "Z"
        new_entry = {
            "timestamp": now,
            "heart_rate_bpm": float(data['heart_rate_bpm']),
            "spo2_percent": float(data['spo2_percent']),
            "temperature_c": float(data['temperature_c']),
            "resp_rate_min": float(data['resp_rate_min']),
            "crp_mg_l": float(data['crp_mg_l']),
            "wbc\u10e9l": float(data['wbc_l']),
            "hrv": float(data['hrv'])
        }
        
        bed = active_beds[bed_id]
        bed["history"].append(new_entry)
        if len(bed["history"]) > 20:
            bed["history"].pop(0)
            
        recalculate_bed_scores(bed)
        return jsonify(bed)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# REST API to create a new patient bed
@app.route('/api/beds/create', methods=['POST'])
def create_bed():
    try:
        data = request.json
        required = ['name', 'gender', 'gestational_age_weeks', 'birth_weight_g', 'heart_rate_bpm', 'spo2_percent', 'temperature_c', 'resp_rate_min', 'crp_mg_l', 'wbc_l', 'hrv']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({"error": f"Missing parameters: {', '.join(missing)}"}), 400
            
        now = datetime.datetime.now()
        new_id = f"bed_{len(active_beds) + 1:02d}"
        
        new_bed = {
            "id": new_id,
            "name": data['name'],
            "gender": data['gender'],
            "gestational_age_weeks": float(data['gestational_age_weeks']),
            "birth_weight_g": float(data['birth_weight_g']),
            "date_of_admission": now.strftime("%Y-%m-%d"),
            "history": [
                {
                    "timestamp": now.isoformat() + "Z",
                    "heart_rate_bpm": float(data['heart_rate_bpm']),
                    "spo2_percent": float(data['spo2_percent']),
                    "temperature_c": float(data['temperature_c']),
                    "resp_rate_min": float(data['resp_rate_min']),
                    "crp_mg_l": float(data['crp_mg_l']),
                    "wbc\u10e9l": float(data['wbc_l']),
                    "hrv": float(data['hrv'])
                }
            ]
        }
        
        recalculate_bed_scores(new_bed)
        active_beds[new_id] = new_bed
        return jsonify(new_bed)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# REST API to simulate vitals tick for all beds
@app.route('/api/simulate', methods=['POST'])
def simulate_tick():
    try:
        now = datetime.datetime.now().isoformat() + "Z"
        for bid, bed in active_beds.items():
            history = bed["history"]
            latest = history[-1]
            
            # Apply clinical trajectory walks
            if bid == "bed_01":  # Emma: Stable normal
                new_hr = clamp(latest["heart_rate_bpm"] + random.choice([-2, -1, 0, 1, 2]), 120, 150)
                new_spo2 = clamp(latest["spo2_percent"] + random.choice([-1, 0, 1]), 95, 100)
                new_temp = clamp(latest["temperature_c"] + random.uniform(-0.04, 0.04), 36.5, 37.4)
                new_rr = clamp(latest["resp_rate_min"] + random.choice([-2, -1, 0, 1, 2]), 35, 55)
                new_crp = clamp(latest["crp_mg_l"] + random.uniform(-0.05, 0.05), 1.0, 4.0)
                new_wbc = clamp(latest["wbc\u10e9l"] + random.uniform(-0.1, 0.1), 10.0, 15.0)
                new_hrv = clamp(latest["hrv"] + random.choice([-2, -1, 0, 1, 2]), 50, 70)
                
            elif bid == "bed_02":  # Noah: Mild risk, slightly fluctuating
                new_hr = clamp(latest["heart_rate_bpm"] + random.choice([-3, -1, 0, 2, 4]), 135, 165)
                new_spo2 = clamp(latest["spo2_percent"] + random.choice([-2, -1, 0, 1]), 90, 96)
                new_temp = clamp(latest["temperature_c"] + random.uniform(-0.08, 0.08), 36.0, 36.8)
                new_rr = clamp(latest["resp_rate_min"] + random.choice([-3, -1, 0, 2, 3]), 45, 65)
                new_crp = clamp(latest["crp_mg_l"] + random.uniform(-0.1, 0.4), 4.0, 15.0)
                new_wbc = clamp(latest["wbc\u10e9l"] + random.uniform(-0.2, 0.15), 6.0, 10.0)
                new_hrv = clamp(latest["hrv"] + random.choice([-2, -1, 0, 1]), 35, 55)
                
            elif bid == "bed_03":  # Liam: Worsening sepsis
                new_hr = clamp(latest["heart_rate_bpm"] + random.uniform(1.0, 3.5), 140, 200)
                new_spo2 = clamp(latest["spo2_percent"] - random.uniform(0.1, 1.0), 80, 95)
                new_temp = clamp(latest["temperature_c"] + random.uniform(0.04, 0.2), 36.8, 39.2)
                new_rr = clamp(latest["resp_rate_min"] + random.uniform(1.0, 3.5), 40, 85)
                new_crp = clamp(latest["crp_mg_l"] + random.uniform(1.5, 5.0), 4.0, 80.0)
                new_wbc = clamp(latest["wbc\u10e9l"] - random.uniform(0.1, 0.5), 2.5, 12.0)
                new_hrv = clamp(latest["hrv"] - random.choice([0, 1, 2]), 12, 50)
                
            elif bid == "bed_04":  # Sophia: Critical sepsis, fluctuates around bad state
                new_hr = clamp(latest["heart_rate_bpm"] + random.choice([-6, -3, 0, 2, 4]), 110, 210)
                new_spo2 = clamp(latest["spo2_percent"] + random.choice([-1.5, -0.5, 0.5, 1.5]), 78, 88)
                new_temp = clamp(latest["temperature_c"] + random.uniform(-0.1, 0.08), 35.2, 36.4)
                new_rr = clamp(latest["resp_rate_min"] + random.choice([-8, -4, 0, 2, 4]), 20, 75)
                new_crp = clamp(latest["crp_mg_l"] + random.uniform(0.5, 3.5), 30.0, 120.0)
                new_wbc = clamp(latest["wbc\u10e9l"] + random.uniform(-0.15, 0.15), 2.0, 5.0)
                new_hrv = clamp(latest["hrv"] + random.choice([-1, 0, 1]), 8, 25)
                
            elif bid == "bed_05":  # Mia: Target Preterm (stable)
                new_hr = clamp(latest["heart_rate_bpm"] + random.choice([-2, -1, 0, 1, 2]), 130, 155)
                new_spo2 = clamp(latest["spo2_percent"] + random.choice([-1, 0, 1]), 90, 95)
                new_temp = clamp(latest["temperature_c"] + random.uniform(-0.04, 0.04), 36.5, 37.3)
                new_rr = clamp(latest["resp_rate_min"] + random.choice([-2, -1, 0, 1, 2]), 40, 55)
                new_crp = clamp(latest["crp_mg_l"] + random.uniform(-0.08, 0.08), 2.0, 6.0)
                new_wbc = clamp(latest["wbc\u10e9l"] + random.uniform(-0.15, 0.15), 12.0, 18.0)
                new_hrv = clamp(latest["hrv"] + random.choice([-2, -1, 0, 1, 2]), 40, 60)
                
            elif bid == "bed_06":  # Lucas: Stable late preterm, high SpO2 alert
                new_hr = clamp(latest["heart_rate_bpm"] + random.choice([-2, -1, 0, 1, 2]), 135, 155)
                new_spo2 = clamp(latest["spo2_percent"] + random.choice([-1, 0, 1]), 97, 100)
                new_temp = clamp(latest["temperature_c"] + random.uniform(-0.04, 0.04), 36.6, 37.4)
                new_rr = clamp(latest["resp_rate_min"] + random.choice([-2, -1, 0, 1, 2]), 42, 55)
                new_crp = clamp(latest["crp_mg_l"] + random.uniform(-0.05, 0.05), 1.5, 4.5)
                new_wbc = clamp(latest["wbc\u10e9l"] + random.uniform(-0.15, 0.15), 14.0, 20.0)
                new_hrv = clamp(latest["hrv"] + random.choice([-2, -1, 0, 1, 2]), 42, 58)
                
            else:  # Manually added beds
                new_hr = clamp(latest["heart_rate_bpm"] + random.choice([-3, 0, 3]), 120, 180)
                new_spo2 = clamp(latest["spo2_percent"] + random.choice([-1, 0, 1]), 85, 100)
                new_temp = clamp(latest["temperature_c"] + random.uniform(-0.06, 0.06), 35.8, 38.5)
                new_rr = clamp(latest["resp_rate_min"] + random.choice([-3, 0, 3]), 25, 75)
                new_crp = clamp(latest["crp_mg_l"] + random.uniform(-0.15, 0.25), 1.0, 60.0)
                new_wbc = clamp(latest["wbc\u10e9l"] + random.uniform(-0.2, 0.2), 3.0, 35.0)
                new_hrv = clamp(latest["hrv"] + random.choice([-2, 0, 2]), 20, 65)

            new_entry = {
                "timestamp": now,
                "heart_rate_bpm": round(float(new_hr), 1),
                "spo2_percent": round(float(new_spo2), 1),
                "temperature_c": round(float(new_temp), 2),
                "resp_rate_min": round(float(new_rr), 1),
                "crp_mg_l": round(float(new_crp), 2),
                "wbc\u10e9l": round(float(new_wbc), 2),
                "hrv": round(float(new_hrv), 1)
            }
            
            history.append(new_entry)
            if len(history) > 20:
                history.pop(0)
                
            recalculate_bed_scores(bed)
            
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# REST API to reset all beds to defaults
@app.route('/api/reset', methods=['POST'])
def reset_beds():
    global active_beds
    active_beds = generate_default_beds()
    return jsonify({"status": "success"})

# Excel upload batch prediction endpoint
@app.route('/predict', methods=['POST'])
def predict():
    if model is None or imputer is None or feature_names is None:
        return jsonify({"error": "Model is not loaded. Please train the model first."}), 500

    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.endswith(('.xls', '.xlsx')):
        return jsonify({"error": "Please upload a valid Excel file"}), 400

    try:
        df = pd.read_excel(file)
        
        patient_ids = df['patient_id'].tolist() if 'patient_id' in df.columns else [f"Patient {i+1}" for i in range(len(df))]
        
        # Make a copy of df to parse for clinical calculations
        calc_df = df.copy()
        
        # Reorder columns to match model expectations
        missing_cols = [col for col in feature_names if col not in df.columns]
        if missing_cols:
            return jsonify({"error": f"Missing columns in uploaded file: {', '.join(missing_cols)}"}), 400
            
        df = df[feature_names]

        # Impute missing values
        X = imputer.transform(df)

        # Predict probability of sepsis
        probabilities = model.predict_proba(X)[:, 1]

        results = []
        for idx, (pid, prob) in enumerate(zip(patient_ids, probabilities)):
            # Extract clinical values for the NSS and other scores
            row = calc_df.iloc[idx]
            
            # Extract values, handle NaN by using median or fallback
            spo2 = float(row['spo2_percent']) if not pd.isna(row['spo2_percent']) else 95.0
            temp = float(row['temperature_c']) if not pd.isna(row['temperature_c']) else 37.0
            crp = float(row['crp_mg_l']) if not pd.isna(row['crp_mg_l']) else 2.0
            wbc = float(row['wbc\u10e9l']) if not pd.isna(row['wbc\u10e9l']) else 12.0
            ga = float(row['gestational_age_weeks']) if not pd.isna(row['gestational_age_weeks']) else 38.0
            bw = float(row['birth_weight_g']) if not pd.isna(row['birth_weight_g']) else 3000.0
            
            # Since Excel represents a snapshot, history is just [current]
            tvi = 10.0
            hsi = 20.0
            ois = round(max(0.0, 100.0 - spo2) * 5.0, 1)
            prs = calculate_prs(ga, bw)
            
            # Estimate HRV: lower HRV if sepsis label is higher in model probability
            estimated_hrv = float(55.0 - (prob * 40.0))
            nss = calculate_nss(estimated_hrv, [spo2], [temp], [crp], wbc, ga, bw)
            
            # Risk categories for clinical NSS
            if nss <= 20.0:
                risk_cat = "Low Risk"
            elif nss <= 40.0:
                risk_cat = "Moderate Risk"
            elif nss <= 60.0:
                risk_cat = "High Risk"
            elif nss <= 80.0:
                risk_cat = "Very High Risk"
            else:
                risk_cat = "Critical Risk"

            # Preterm Category Metadata
            if ga < 28.0:
                ga_category = "Extremely Preterm"
                ga_multiplier = "3.0x"
            elif ga < 32.0:
                ga_category = "Very Preterm"
                ga_multiplier = "2.5x"
            elif ga < 34.0:
                ga_category = "Moderate Preterm"
                ga_multiplier = "1.8x"
            elif ga < 37.0:
                ga_category = "Late Preterm"
                ga_multiplier = "1.3x"
            else:
                ga_category = "Term"
                ga_multiplier = "1.0x"
                
            # Birth Weight Category Metadata
            if bw < 1000.0:
                bw_category = "ELBW"
            elif bw < 1500.0:
                bw_category = "VLBW"
            elif bw < 2500.0:
                bw_category = "LBW"
            elif bw <= 4000.0:
                bw_category = "Normal"
            else:
                bw_category = "Macrosomia"

            results.append({
                "patient_id": pid,
                "ml_risk_score": round(prob * 100, 1),
                "nss": nss,
                "tvi": tvi,
                "hsi": hsi,
                "ois": ois,
                "prs": prs,
                "risk_category": risk_cat,
                "ga_category": ga_category,
                "ga_multiplier": ga_multiplier,
                "bw_category": bw_category,
                "vitals": {
                    "heart_rate_bpm": float(row['heart_rate_bpm']) if not pd.isna(row['heart_rate_bpm']) else 140.0,
                    "spo2_percent": spo2,
                    "temperature_c": temp,
                    "resp_rate_min": float(row['resp_rate_min']) if not pd.isna(row['resp_rate_min']) else 45.0,
                    "crp_mg_l": crp,
                    "wbc_l": wbc,
                    "gestational_age_weeks": ga,
                    "birth_weight_g": bw
                }
            })

        return jsonify({"results": results})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Predict form route (with added calculated clinical indices)
@app.route('/predict_form', methods=['POST'])
def predict_form():
    if model is None or imputer is None or feature_names is None:
        return jsonify({"error": "Model is not loaded."}), 500

    try:
        data = request.json
        df = pd.DataFrame([data])
        
        missing_cols = [col for col in feature_names if col not in df.columns]
        if missing_cols:
            return jsonify({"error": f"Missing columns in form data: {', '.join(missing_cols)}"}), 400
            
        df = df[feature_names]
        df = df.replace('', pd.NA)
        X = imputer.transform(df)

        prob = float(model.predict_proba(X)[0, 1])
        
        # Calculate NSS and other indices for the form submission
        spo2 = float(data['spo2_percent'])
        temp = float(data['temperature_c'])
        crp = float(data['crp_mg_l'])
        wbc = float(data['wbc\u10e9l'])
        ga = float(data['gestational_age_weeks'])
        bw = float(data['birth_weight_g'])
        
        # Estimate HRV based on ML probability for standard calculations
        est_hrv = float(55.0 - (prob * 40.0))
        nss = calculate_nss(est_hrv, [spo2], [temp], [crp], wbc, ga, bw)
        tvi = 10.0
        hsi = round(float(clamp((80.0 - est_hrv) * 1.5, 0.0, 100.0)), 1)
        ois = calculate_ois([spo2])
        prs = calculate_prs(ga, bw)
        
        if nss <= 20.0:
            risk_cat = "Low Risk"
        elif nss <= 40.0:
            risk_cat = "Moderate Risk"
        elif nss <= 60.0:
            risk_cat = "High Risk"
        elif nss <= 80.0:
            risk_cat = "Very High Risk"
        else:
            risk_cat = "Critical Risk"

        # Preterm Category Metadata
        if ga < 28.0:
            ga_category = "Extremely Preterm"
            ga_multiplier = "3.0x"
        elif ga < 32.0:
            ga_category = "Very Preterm"
            ga_multiplier = "2.5x"
        elif ga < 34.0:
            ga_category = "Moderate Preterm"
            ga_multiplier = "1.8x"
        elif ga < 37.0:
            ga_category = "Late Preterm"
            ga_multiplier = "1.3x"
        else:
            ga_category = "Term"
            ga_multiplier = "1.0x"
            
        # Birth Weight Category Metadata
        if bw < 1000.0:
            bw_category = "ELBW"
        elif bw < 1500.0:
            bw_category = "VLBW"
        elif bw < 2500.0:
            bw_category = "LBW"
        elif bw <= 4000.0:
            bw_category = "Normal"
        else:
            bw_category = "Macrosomia"

        return jsonify({
            "risk_score": prob,
            "ml_risk_score": round(prob * 100, 1),
            "nss": nss,
            "tvi": tvi,
            "hsi": hsi,
            "ois": ois,
            "prs": prs,
            "risk_category": risk_cat,
            "ga_category": ga_category,
            "ga_multiplier": ga_multiplier,
            "bw_category": bw_category
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)

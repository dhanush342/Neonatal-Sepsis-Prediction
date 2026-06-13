from flask import Flask, request, jsonify, send_from_directory
import pandas as pd
import joblib
import os

app = Flask(__name__, static_folder='static', static_url_path='')

# Load the saved model artifacts
# Ensure they exist by running train.py first
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

def get_risk_category(score):
    if score < 0.30:
        return "Low Risk"
    elif score < 0.70:
        return "Moderate Risk"
    else:
        return "High Risk"

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

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
        
        # Keep patient IDs if they exist for the output
        patient_ids = df['patient_id'].tolist() if 'patient_id' in df.columns else [f"Patient {i+1}" for i in range(len(df))]
        
        # Drop patient_id before prediction
        if 'patient_id' in df.columns:
            df = df.drop('patient_id', axis=1)
            
        # Optional: remove target if present
        if 'sepsis_label' in df.columns:
            df = df.drop('sepsis_label', axis=1)

        # Reorder columns to match training data
        missing_cols = [col for col in feature_names if col not in df.columns]
        if missing_cols:
            return jsonify({"error": f"Missing columns in uploaded file: {', '.join(missing_cols)}"}), 400
            
        df = df[feature_names]

        # Impute missing values
        X = imputer.transform(df)

        # Predict probability of sepsis (class 1)
        probabilities = model.predict_proba(X)[:, 1]

        results = []
        for pid, prob in zip(patient_ids, probabilities):
            results.append({
                "patient_id": pid,
                "risk_score": float(prob),
                "risk_category": get_risk_category(prob)
            })

        return jsonify({"results": results})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/predict_form', methods=['POST'])
def predict_form():
    if model is None or imputer is None or feature_names is None:
        return jsonify({"error": "Model is not loaded."}), 500

    try:
        data = request.json
        
        # Construct DataFrame from form data
        df = pd.DataFrame([data])
        
        # Ensure correct column order
        missing_cols = [col for col in feature_names if col not in df.columns]
        if missing_cols:
            return jsonify({"error": f"Missing columns in form data: {', '.join(missing_cols)}"}), 400
            
        df = df[feature_names]

        # Impute missing values (if any fields were left blank)
        # Convert empty strings to NaN first
        df = df.replace('', pd.NA)
        X = imputer.transform(df)

        # Predict probability
        prob = float(model.predict_proba(X)[0, 1])

        return jsonify({
            "risk_score": prob,
            "risk_category": get_risk_category(prob)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)

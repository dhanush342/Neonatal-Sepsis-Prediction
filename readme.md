# Neonatal Sepsis Prediction Web Application

## Project Aim
The primary aim of this project is to provide a predictive tool for early detection of **Neonatal Sepsis**, a severe medical condition in newborns caused by an infection in the bloodstream. Early detection is critical for the survival and treatment of infants. 

This application provides a user-friendly web interface where medical professionals or users can input vital signs and laboratory results to instantly receive a probability-based **Sepsis Risk Score** and a corresponding risk category.

## How It Works

### The Machine Learning Model
At the core of this project is a **Random Forest Classifier** built using Python and `scikit-learn`. 
The model is trained to find complex, non-linear relationships across 8 key physiological and clinical features:
1. **Heart Rate (BPM)**
2. **SpO2 (%)** (Oxygen saturation)
3. **Temperature (°C)**
4. **Respiratory Rate (/min)**
5. **CRP (mg/L)** (C-reactive protein, a marker of inflammation)
6. **WBC (10^9/L)** (White blood cell count)
7. **Gestational Age (weeks)**
8. **Birth Weight (g)**

### The Prediction Pipeline
1. **Data Entry**: The user enters the patient's current vitals and lab results into the web form.
2. **Imputation**: If any fields are missing during the workflow, a pre-trained `SimpleImputer` replaces missing values with the median values observed during the model's training phase.
3. **Probability Calculation**: The Random Forest model evaluates the data and outputs a probability score (from 0 to 1).
4. **Risk Categorization**: 
   - **Low Risk**: Score < 30%
   - **Moderate Risk**: 30% ≤ Score < 70%
   - **High Risk**: Score ≥ 70%
5. **Result Display**: The backend (powered by **Flask**) sends this calculation back to the frontend to instantly display the results.

## Setup and Installation

1. **Install Dependencies:**
   Ensure you have Python installed, then run:
   ```bash
   pip install -r requirements.txt
   ```

2. **Train the Model:**
   To train the Random Forest model and generate the `.pkl` artifact files, run:
   ```bash
   python train.py
   ```

3. **Run the Web Application:**
   Start the Flask web server by running:
   ```bash
   python app.py
   ```
   The application will be accessible locally at `http://localhost:5000`.

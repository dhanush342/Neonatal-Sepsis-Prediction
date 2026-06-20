import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import joblib

def main():
    print("Loading dataset...")
    # Load dataset
    df = pd.read_excel("Neonatal_Sepsis_Dummy_Dataset.xlsx")

    # Remove patient ID if it exists
    if "patient_id" in df.columns:
        df = df.drop("patient_id", axis=1)

    # Features and target
    X = df.drop("sepsis_label", axis=1)
    y = df["sepsis_label"]

    print("Handling missing values...")
    # Handle missing values
    imputer = SimpleImputer(strategy="median")
    X_imputed = imputer.fit_transform(X)
    
    # Save feature names for later use
    feature_names = X.columns.tolist()

    print("Splitting data...")
    X_train, X_test, y_train, y_test = train_test_split(
        X_imputed,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )

    print("Training Random Forest model with Grid Search hyperparameter optimization...")
    rf_classifier = RandomForestClassifier(random_state=42)
    
    param_grid = {
        'n_estimators': [100, 200, 300],
        'max_depth': [4, 6, 8, 10, None],
        'min_samples_split': [2, 5],
        'min_samples_leaf': [1, 2]
    }
    
    grid_search = GridSearchCV(
        estimator=rf_classifier,
        param_grid=param_grid,
        cv=5,
        scoring="accuracy",
        n_jobs=-1
    )
    
    grid_search.fit(X_train, y_train)
    
    print("Best parameters found by Grid Search:", grid_search.best_params_)
    model = grid_search.best_estimator_

    # Evaluation using the best estimator
    print("Evaluating optimized model...")
    pred = model.predict(X_test)
    prob = model.predict_proba(X_test)[:, 1]

    print("Accuracy :", accuracy_score(y_test, pred))
    print("Precision:", precision_score(y_test, pred))
    print("Recall   :", recall_score(y_test, pred))
    print("F1 Score :", f1_score(y_test, pred))
    print("ROC AUC  :", roc_auc_score(y_test, prob))

    print("Saving optimized model, imputer, and feature names...")
    joblib.dump(model, "model.pkl")
    joblib.dump(imputer, "imputer.pkl")
    joblib.dump(feature_names, "feature_names.pkl")

    print("Done! Optimized model trained and saved.")

if __name__ == "__main__":
    main()

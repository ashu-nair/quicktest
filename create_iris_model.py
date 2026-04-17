"""
Create a test Iris classification model for MLOps platform testing.
Run this to generate iris_model.zip

IMPORTANT: Use numpy==1.21.6 to match EC2 deployment environment:
  pip install numpy==1.21.6 scikit-learn==1.0.2
"""
import joblib
import json
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from pathlib import Path
import zipfile
import shutil

# Load Iris dataset
iris = load_iris()
X, y = iris.data, iris.target

# Split data
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train a simple Random Forest model
model = RandomForestClassifier(n_estimators=10, random_state=42)
model.fit(X_train, y_train)

# Test accuracy
accuracy = model.score(X_test, y_test)
print(f"Model trained! Accuracy: {accuracy:.2f}")
print(f"Features: {iris.feature_names}")
print(f"Classes: {iris.target_names.tolist()}")

# Create temp directory for model files
model_dir = Path("iris_model_temp")
model_dir.mkdir(exist_ok=True)

# Save model
joblib.dump(model, model_dir / "model.pkl")

# Save config
config = {
    "model_type": "RandomForestClassifier",
    "target_classes": iris.target_names.tolist(),
    "features": iris.feature_names,
    "description": "Iris flower classification model",
    "accuracy": accuracy
}
with open(model_dir / "model_config.json", "w") as f:
    json.dump(config, f, indent=2)

# Create ZIP
zip_path = Path("iris_model.zip")
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for file in model_dir.iterdir():
        zipf.write(file, file.name)

# Cleanup
shutil.rmtree(model_dir)

print(f"\n✅ Created {zip_path}")
print(f"Upload this to your MLOps platform!")
print(f"\nTest with features: [5.1, 3.5, 1.4, 0.2] (setosa)")

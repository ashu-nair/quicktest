"""
Build any sklearn model with correct numpy version for EC2 compatibility.
Usage: python build_model.py --model your_model_file.pkl --name cancer_model
"""
import joblib
import json
import argparse
from pathlib import Path
import zipfile
import numpy as np

def package_model(model_path, model_name, config=None):
    print(f"Loading model from {model_path}...")
    # Load the model
    model = joblib.load(model_path)
    
    # Create output dir
    out_dir = Path(f"{model_name}_package")
    out_dir.mkdir(exist_ok=True)
    
    # Save with protocol=4 for better compatibility
    joblib.dump(model, out_dir / "model.pkl", compress=3, protocol=4)
    
    print(f"Model saved. Numpy version: {np.__version__}")
    
    # Save config or create default
    default_config = {
        "model_type": type(model).__name__,
        "description": f"Model: {model_name}",
        "features": ["feature_1", "feature_2", "feature_3", "feature_4"],  # Update as needed
        "built_with_numpy": np.__version__
    }
    if config:
        default_config.update(config)
    
    with open(out_dir / "model_config.json", "w") as f:
        json.dump(default_config, f, indent=2)
    
    # Create zip
    zip_path = f"{model_name}.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.write(out_dir / "model.pkl", "model.pkl")
        zf.write(out_dir / "model_config.json", "model_config.json")
    
    print(f"✅ Created {zip_path}")
    print(f"Features: {default_config['features']}")
    print(f"Upload this to your MLOps platform!")
    print(f"\nIMPORTANT: If deployment fails with 'numpy._core' error,")
    print(f"downgrade numpy first: pip install numpy==1.21.6")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Package sklearn model for MLOps deployment")
    parser.add_argument("--model", required=True, help="Path to your .pkl model file")
    parser.add_argument("--name", required=True, help="Name for the output zip (without .zip)")
    parser.add_argument("--features", default="f1,f2,f3,f4", 
                        help="Feature names (comma separated, e.g., 'radius,texture,perimeter')")
    args = parser.parse_args()
    
    config = {"features": args.features.split(",")}
    package_model(args.model, args.name, config)

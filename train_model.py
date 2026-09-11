#!/usr/bin/env python
import sys
sys.path.insert(0, '.')

from src.training.dataset import load_training_data
from src.training.train import train_model
import os

def main():
    # Cargar datos
    df = load_training_data()
    print(f"Datos cargados: {len(df)} filas")
    print(f"Columnas: {list(df.columns)}")
    
    # Entrenar modelo
    train_model(df)
    print("✅ Modelo entrenado exitosamente")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
import sys

sys.path.insert(0, "C:/Users/Administrator/Jarvis")

from core.comprehensive_training import add_training_data

if __name__ == "__main__":
    add_training_data()
    print("Training data added successfully!")

# Training pipeline skeleton — placeholder for model fine-tuning / dataset prep

import os


def prepare_data(source_dir: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    # TODO: implement data conversion to fine-tuning format


def train_dummy():
    print("No training configured. Implement training routine here.")


if __name__ == '__main__':
    prepare_data('data', 'models/train_data')
    train_dummy()

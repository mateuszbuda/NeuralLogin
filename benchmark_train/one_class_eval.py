import sys, os
from sklearn.cross_validation import train_test_split as splitter
from sklearn.preprocessing import normalize
from sklearn.utils import shuffle
sys.path.append(".")

from emails import get_emails

import numpy as np
import theano
np.random.seed(1337)  # for reproducibility

from training.keras.dataset import BenchmarkDataset
from keras.preprocessing import sequence
from keras.utils import np_utils

from config import LSTM3Layers3DropoutsConfig, GRU3Layers3DropoutsConfig, LSTM2Layers2DropoutsConfig, OneClassGRU3Layers3DropoutsConfig

def train_test_split(X, y, test_size=0.2):
    positive_count = sum(y)

    negative_ys = y[positive_count:]
    negative_Xs = X[positive_count:]

    negative_Xs, negative_ys = shuffle(negative_Xs, negative_ys)
    X = np.concatenate( (X[:positive_count], negative_Xs[:positive_count]) )
    y = np.concatenate( (y[:positive_count], negative_ys[:positive_count]) )

    positive_split_point = int((1.0 - test_size) * positive_count)

    X_train = np.concatenate( (X[:positive_split_point], X[positive_count:positive_count + positive_split_point]) )
    X_test = np.concatenate( (X[positive_split_point:positive_count], X[positive_count + positive_split_point:]) )
    y_train = np.concatenate( (y[:positive_split_point], y[positive_count:positive_count + positive_split_point]) )
    y_test = np.concatenate( (y[positive_split_point:positive_count], y[positive_count + positive_split_point:]) )

    return X_train, X_test, y_train, y_test

def save_model(config, model, mail):
    model_path         = os.path.join(config.save_model_dir, mail)
    model_object_path  = os.path.join(model_path, "model.json")
    model_weights_path = os.path.join(model_path, "weights.h5")

    if not os.path.exists(os.path.dirname(model_object_path)):
        os.makedirs(os.path.dirname(model_object_path))
    if not os.path.exists(os.path.dirname(model_weights_path)):
        os.makedirs(os.path.dirname(model_weights_path))
    with open(model_object_path, 'w+') as f:
        f.write(model.to_json())
    model.save_weights(model_weights_path, overwrite=True)

def false_positives(y_score, y, threshold):
    fp = 0
    for i in range(len(y)):
        p = int(y_score[i] > threshold)
        if p == 1 and y[i] == 0:
            fp += 1

    return fp

def find_threshold(y_score, y):
    best_th = 0
    best_false_positives = len(y)
    for t in np.arange(0.50, 0.9999, 0.0001):
        fp = false_positives(y_score, y, t)
        if fp < best_false_positives:
            best_th = t
            best_false_positives = fp
    return best_th

def get_impostor_test(X, y):
    X = np.array(X)

    indices = []
    i = 400
    while i < len(X):
        for j in range(5):
            indices.append(i + j)
        i += 400
    return X[indices], y[indices]

if __name__ == "__main__":
    dataset_dir = "benchmark_set"
    emails_file = "subjects.txt"

    dataset = BenchmarkDataset(dataset_dir)
    subjects = get_emails(emails_file)
    configs = [
                # LSTM2Layers2DropoutsConfig(first_layer=240, second_layer=100, input_length=10),
                # LSTM3Layers3DropoutsConfig(first_layer=240, second_layer=240, input_length=10),
                OneClassGRU3Layers3DropoutsConfig(first_layer=240, second_layer=240, input_length=10)
            ]

    for config in configs:
        # We are going to train separate model for each subject
        for subject in subjects:
            X, y = dataset.load(subject)
            X = np.array(X)
            y = np.array(y)

            X_train = X[:200]
            y_train = y[:200]

            genuine_X_test = X[200:401]
            genuine_Y_test = y[200:401]
            impostor_X_test, impostor_Y_test = get_impostor_test(X, y)

            X_train = normalize(X_train)
            genuine_X_test = normalize(genuine_X_test)
            impostor_X_test = normalize(impostor_X_test)

            model = config.build_and_compile()

            X_train = sequence.pad_sequences(X_train, maxlen=10, dtype='float32')
            genuine_X_test = sequence.pad_sequences(genuine_X_test, maxlen=10, dtype='float32')
            impostor_X_test = sequence.pad_sequences(impostor_X_test, maxlen=10, dtype='float32')

            X_train = np.reshape(X_train, (X_train.shape[0], 10, 1))
            genuine_X_test = np.reshape(genuine_X_test, (genuine_X_test.shape[0], 10, 1))
            impostor_X_test = np.reshape(impostor_X_test, (impostor_X_test.shape[0], 10, 1))

            print("Train...")
            model.fit(X_train, y_train, batch_size=config.batch_size, nb_epoch=config.epochs)

            genuine_score, genuine_acc = model.evaluate(genuine_X_test, genuine_Y_test, batch_size=config.batch_size)
            impostor_score, impostor_acc = model.evaluate(impostor_X_test, impostor_Y_test, batch_size=config.batch_size)

            print(genuine_acc, impostor_acc)

            print("Errors intented here")

            genuine_prediction = model.predict(genuine_X_test).flatten()
            genuine_predicted_classes = np.round(genuine_prediction)
            genuine_correct = y_test == predicted_classes
            genuine_incorrect = y_test != predicted_classes

            TP = sum(np.logical_and(correct, y_test == 1))
            TN = sum(np.logical_and(correct, y_test == 0))
            FP = sum(np.logical_and(incorrect, y_test == 0))
            FN = sum(np.logical_and(incorrect, y_test == 1))

            save_model(config, model, subject)
            threshold = find_threshold(prediction, y_test)
            with open(os.path.join(config.thresholds_dir, subject + ".txt"), "w+") as f:
                f.write(str(threshold))


            th_predicted_classes = prediction >= threshold
            th_correct = y_test == th_predicted_classes
            th_incorrect = y_test != th_predicted_classes

            th_TP = sum(np.logical_and(th_correct, y_test == 1))
            th_TN = sum(np.logical_and(th_correct, y_test == 0))
            th_FP = sum(np.logical_and(th_incorrect, y_test == 0))
            th_FN = sum(np.logical_and(th_incorrect, y_test == 1))

            th_acc = float(sum(th_correct)) / float(len(th_predicted_classes))

            with open(os.path.join(config.out_results_dir, subject + ".txt"), 'w+') as f:
                f.write(','.join([str(acc), str(TP), str(TN), str(FP), str(FN)]))
                f.write('\n')
                f.write(','.join([str(th_acc), str(th_TP), str(th_TN), str(th_FP), str(th_FN)]))

            # print("Acc:", acc, "TP:", TP, "TN:", TN, "FP:", FP, "FN:", FN)
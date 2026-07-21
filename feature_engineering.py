import pandas as pd

def load_data(path):
    return pd.read_csv(path)  # load raw csv

def clean_data(df):
    df = df.copy()  # never touch original

    df = df.drop(columns=['customerID'])  # ID has no predictive value

    df['TotalCharges'] = df['TotalCharges'].replace(' ', 0).astype(float)  # fix blank -> 0 for new customers

    df['Churn'] = df['Churn'].map({'No': 0, 'Yes': 1})  # encode target

    # simple Yes/No columns -> 0/1
    binary_cols = ['gender', 'Partner', 'Dependents', 'PhoneService', 'PaperlessBilling']
    df['gender'] = df['gender'].map({'Male': 0, 'Female': 1})
    for col in ['Partner', 'Dependents', 'PhoneService', 'PaperlessBilling']:
        df[col] = df[col].map({'No': 0, 'Yes': 1})

    # multi-category columns -> numeric codes
    multi_cols = ['MultipleLines', 'InternetService', 'OnlineSecurity', 'OnlineBackup',
                  'DeviceProtection', 'TechSupport', 'StreamingTV', 'StreamingMovies',
                  'Contract', 'PaymentMethod']
    for col in multi_cols:
        df[col] = df[col].astype('category').cat.codes  # each unique text value -> a number

    return df

def get_features_and_target(df):
    X = df.drop(columns=['Churn'])  # everything except target
    y = df['Churn']  # target only
    return X, y
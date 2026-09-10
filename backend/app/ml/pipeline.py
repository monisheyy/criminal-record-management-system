import numpy as np
import pickle
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
import warnings
warnings.filterwarnings('ignore')

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'saved_models')
os.makedirs(MODEL_DIR, exist_ok=True)

CRIME_TYPES = [
    'Robbery', 'Assault', 'Murder', 'Drug Trafficking', 'Burglary',
    'Cybercrime', 'Fraud', 'Kidnapping', 'Arms Trafficking', 'Extortion',
    'Human Trafficking', 'Car Theft', 'Vandalism', 'Arson', 'Money Laundering'
]

CRIME_CATEGORIES = {
    'Robbery': 'Violent', 'Assault': 'Violent', 'Murder': 'Violent',
    'Kidnapping': 'Violent', 'Drug Trafficking': 'Narcotics',
    'Arms Trafficking': 'Weapons', 'Human Trafficking': 'Organized Crime',
    'Fraud': 'Financial', 'Money Laundering': 'Financial', 'Extortion': 'Financial',
    'Burglary': 'Property', 'Car Theft': 'Property', 'Vandalism': 'Property',
    'Arson': 'Property', 'Cybercrime': 'Technology'
}

GANG_NAMES = ['Shadow Syndicate', 'Red Serpents', 'Iron Fist', 'Night Wolves', 'Black Eagles']


class CRMSMLPipeline:
    def __init__(self):
        self.crime_classifier = None
        self.gang_predictor = None
        self.label_encoder_crime = LabelEncoder()
        self.label_encoder_gang = LabelEncoder()
        self.scaler = StandardScaler()
        self.model_version = 'v1.0'
        self.is_trained = False
        self._load_or_train()

    def _generate_synthetic_training_data(self, n_samples: int = 500) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        np.random.seed(42)
        features = []
        crime_labels = []
        gang_labels = []

        for _ in range(n_samples):
            prior_convictions = np.random.randint(0, 10)
            age = np.random.randint(16, 65)
            is_gang_member = np.random.choice([0, 1], p=[0.6, 0.4])
            weapons_involved = np.random.choice([0, 1], p=[0.5, 0.5])
            drug_involvement = np.random.choice([0, 1], p=[0.6, 0.4])
            financial_motivation = np.random.choice([0, 1], p=[0.5, 0.5])
            tech_involvement = np.random.choice([0, 1], p=[0.7, 0.3])
            violence_history = np.random.randint(0, 5)
            location_risk = np.random.uniform(0, 1)
            time_of_crime = np.random.randint(0, 24)
            associates_count = np.random.randint(0, 15)

            features.append([
                prior_convictions, age, is_gang_member, weapons_involved,
                drug_involvement, financial_motivation, tech_involvement,
                violence_history, location_risk, time_of_crime, associates_count
            ])

            # Weighted crime selection based on features
            crime_weights = np.ones(len(CRIME_TYPES))
            if weapons_involved:
                for i, c in enumerate(CRIME_TYPES):
                    if c in ['Murder', 'Robbery', 'Arms Trafficking']: crime_weights[i] *= 3
            if drug_involvement:
                crime_weights[CRIME_TYPES.index('Drug Trafficking')] *= 4
            if financial_motivation:
                for i, c in enumerate(CRIME_TYPES):
                    if c in ['Fraud', 'Extortion', 'Money Laundering']: crime_weights[i] *= 3
            if tech_involvement:
                crime_weights[CRIME_TYPES.index('Cybercrime')] *= 4
            if is_gang_member:
                for i, c in enumerate(CRIME_TYPES):
                    if c in ['Drug Trafficking', 'Arms Trafficking', 'Extortion']: crime_weights[i] *= 2

            crime_weights /= crime_weights.sum()
            crime_labels.append(np.random.choice(CRIME_TYPES, p=crime_weights))

            # Gang affiliation
            if is_gang_member:
                gang_labels.append(np.random.choice(GANG_NAMES))
            else:
                gang_labels.append('None')

        return np.array(features), np.array(crime_labels), np.array(gang_labels)

    def train(self, X=None, y_crime=None, y_gang=None) -> Dict:
        if X is None:
            X, y_crime, y_gang = self._generate_synthetic_training_data(600)

        X_scaled = self.scaler.fit_transform(X)
        y_crime_enc = self.label_encoder_crime.fit_transform(y_crime)
        y_gang_enc = self.label_encoder_gang.fit_transform(y_gang)

        # Train crime classifier
        X_train_c, X_test_c, yc_train, yc_test = train_test_split(
            X_scaled, y_crime_enc, test_size=0.2, random_state=42, stratify=y_crime_enc
        )
        self.crime_classifier = RandomForestClassifier(
            n_estimators=150, max_depth=10, random_state=42, class_weight='balanced'
        )
        self.crime_classifier.fit(X_train_c, yc_train)
        yc_pred = self.crime_classifier.predict(X_test_c)

        crime_metrics = {
            'accuracy': float(accuracy_score(yc_test, yc_pred)),
            'precision': float(precision_score(yc_test, yc_pred, average='weighted', zero_division=0)),
            'recall': float(recall_score(yc_test, yc_pred, average='weighted', zero_division=0)),
            'f1': float(f1_score(yc_test, yc_pred, average='weighted', zero_division=0)),
            'training_samples': len(X_train_c)
        }

        # Train gang predictor
        X_train_g, X_test_g, yg_train, yg_test = train_test_split(
            X_scaled, y_gang_enc, test_size=0.2, random_state=42
        )
        self.gang_predictor = RandomForestClassifier(
            n_estimators=100, max_depth=8, random_state=42
        )
        self.gang_predictor.fit(X_train_g, yg_train)
        yg_pred = self.gang_predictor.predict(X_test_g)

        gang_metrics = {
            'accuracy': float(accuracy_score(yg_test, yg_pred)),
            'precision': float(precision_score(yg_test, yg_pred, average='weighted', zero_division=0)),
            'recall': float(recall_score(yg_test, yg_pred, average='weighted', zero_division=0)),
            'f1': float(f1_score(yg_test, yg_pred, average='weighted', zero_division=0)),
            'training_samples': len(X_train_g)
        }

        self.is_trained = True
        self._save_models()

        feature_importances = {
            f'feature_{i}': float(v)
            for i, v in enumerate(self.crime_classifier.feature_importances_)
        }

        return {
            'crime_classifier': crime_metrics,
            'gang_predictor': gang_metrics,
            'feature_importances': feature_importances,
            'model_version': self.model_version,
            'trained_at': datetime.utcnow().isoformat()
        }

    def predict(self, criminal_data: Dict) -> Dict:
        if not self.is_trained:
            self._load_or_train()

        features = self._extract_features(criminal_data)
        X = np.array([features])
        X_scaled = self.scaler.transform(X)

        # Crime type prediction
        crime_proba = self.crime_classifier.predict_proba(X_scaled)[0]
        crime_idx = np.argmax(crime_proba)
        predicted_crime = self.label_encoder_crime.inverse_transform([crime_idx])[0]
        crime_confidence = float(crime_proba[crime_idx])

        # Gang affiliation prediction
        gang_proba = self.gang_predictor.predict_proba(X_scaled)[0]
        gang_idx = np.argmax(gang_proba)
        predicted_gang_label = self.label_encoder_gang.inverse_transform([gang_idx])[0]
        gang_confidence = float(gang_proba[gang_idx])

        is_gang_affiliated = predicted_gang_label != 'None'
        gang_affiliation_prob = gang_confidence if is_gang_affiliated else (1 - gang_proba[self.label_encoder_gang.transform(['None'])[0]] if 'None' in self.label_encoder_gang.classes_ else 0.1)

        # Risk score calculation (1-100)
        risk_score = self._calculate_risk_score(
            criminal_data, crime_confidence, gang_affiliation_prob
        )

        risk_level = 'low'
        if risk_score >= 75:
            risk_level = 'critical'
        elif risk_score >= 55:
            risk_level = 'high'
        elif risk_score >= 35:
            risk_level = 'medium'

        overall_confidence = (crime_confidence + gang_confidence) / 2

        return {
            'predicted_crime_type': predicted_crime,
            'crime_type_confidence': round(crime_confidence * 100, 1),
            'gang_affiliation_probability': round(gang_affiliation_prob * 100, 1),
            'predicted_gang': predicted_gang_label if is_gang_affiliated else None,
            'risk_score': round(risk_score, 1),
            'risk_level': risk_level,
            'confidence_overall': round(overall_confidence * 100, 1),
            'input_features': {
                'prior_convictions': criminal_data.get('prior_convictions', 0),
                'crime_type': criminal_data.get('crime_type', 'Unknown'),
                'gang_affiliated': criminal_data.get('gang_id') is not None,
                'is_wanted': criminal_data.get('is_wanted', False),
                'violence_history': criminal_data.get('violence_history', 0),
            }
        }

    def _extract_features(self, data: Dict) -> List[float]:
        crime_type = data.get('crime_type', '')
        is_violent = 1 if crime_type in ['Murder', 'Robbery', 'Assault', 'Kidnapping'] else 0
        has_drugs = 1 if crime_type in ['Drug Trafficking'] else 0
        has_financial = 1 if crime_type in ['Fraud', 'Money Laundering', 'Extortion'] else 0
        has_tech = 1 if crime_type in ['Cybercrime'] else 0
        has_weapons = 1 if crime_type in ['Arms Trafficking', 'Murder', 'Robbery'] else 0

        age = 30
        if data.get('date_of_birth'):
            try:
                from datetime import datetime
                if isinstance(data['date_of_birth'], str):
                    dob = datetime.fromisoformat(data['date_of_birth'].replace('Z', '+00:00'))
                else:
                    dob = data['date_of_birth']
                age = (datetime.utcnow() - dob.replace(tzinfo=None)).days // 365
            except Exception:
                age = 30

        return [
            float(data.get('prior_convictions', 0)),
            float(max(16, min(70, age))),
            1.0 if data.get('gang_id') else 0.0,
            float(has_weapons),
            float(has_drugs),
            float(has_financial),
            float(has_tech),
            float(min(data.get('prior_convictions', 0), 5)),
            float(0.7 if data.get('is_wanted') else 0.3),
            12.0,  # default time
            float(min(len((data.get('known_associates') or '').split(',')), 15))
        ]

    def _calculate_risk_score(self, data: Dict, crime_conf: float, gang_prob: float) -> float:
        score = 0.0
        prior = data.get('prior_convictions', 0)
        score += min(prior * 8, 30)  # max 30 from prior convictions
        score += crime_conf * 20  # max 20 from prediction confidence
        score += gang_prob * 25  # max 25 from gang
        if data.get('is_wanted'):
            score += 10
        if data.get('is_incarcerated'):
            score -= 5
        crime_type = data.get('crime_type', '')
        if crime_type in ['Murder', 'Arms Trafficking', 'Human Trafficking']:
            score += 15
        elif crime_type in ['Drug Trafficking', 'Kidnapping', 'Robbery']:
            score += 10
        elif crime_type in ['Fraud', 'Extortion', 'Money Laundering']:
            score += 5
        import random
        score += random.uniform(-3, 3)  # slight randomness for realism
        return max(1.0, min(100.0, score))

    def find_similar_criminals(self, criminal_data: Dict, all_criminals: List[Dict], top_k: int = 5) -> List[Dict]:
        if not all_criminals:
            return []
        target_features = np.array(self._extract_features(criminal_data))
        results = []
        for c in all_criminals:
            if c.get('id') == criminal_data.get('id'):
                continue
            c_features = np.array(self._extract_features(c))
            similarity = self._cosine_similarity(target_features, c_features)
            results.append({'id': c['id'], 'name': f"{c.get('first_name','')} {c.get('last_name','')}",
                           'score': round(float(similarity) * 100, 1),
                           'crime_type': c.get('crime_type')})
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _save_models(self):
        with open(os.path.join(MODEL_DIR, 'crime_classifier.pkl'), 'wb') as f:
            pickle.dump(self.crime_classifier, f)
        with open(os.path.join(MODEL_DIR, 'gang_predictor.pkl'), 'wb') as f:
            pickle.dump(self.gang_predictor, f)
        with open(os.path.join(MODEL_DIR, 'encoders.pkl'), 'wb') as f:
            pickle.dump({
                'crime': self.label_encoder_crime,
                'gang': self.label_encoder_gang,
                'scaler': self.scaler
            }, f)

    def _load_or_train(self):
        try:
            with open(os.path.join(MODEL_DIR, 'crime_classifier.pkl'), 'rb') as f:
                self.crime_classifier = pickle.load(f)
            with open(os.path.join(MODEL_DIR, 'gang_predictor.pkl'), 'rb') as f:
                self.gang_predictor = pickle.load(f)
            with open(os.path.join(MODEL_DIR, 'encoders.pkl'), 'rb') as f:
                enc = pickle.load(f)
                self.label_encoder_crime = enc['crime']
                self.label_encoder_gang = enc['gang']
                self.scaler = enc['scaler']
            self.is_trained = True
        except (FileNotFoundError, Exception):
            self.train()


# Singleton instance
_pipeline_instance = None

def get_pipeline() -> CRMSMLPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = CRMSMLPipeline()
    return _pipeline_instance

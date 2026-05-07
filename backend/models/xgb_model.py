import shap
import numpy as np
from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler
from config import FEATURE_NAMES

class XGBModel:
    def __init__(self):
        self.model = XGBClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.05, subsample=0.8, 
            colsample_bytree=0.8, eval_metric='logloss', random_state=42
        )
        self.scaler = StandardScaler()
        self.trained = False
        self._explainer = None  # initialized after training
 
    def fit(self, X: np.ndarray, y: np.ndarray):
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.trained = True
        self._explainer = shap.TreeExplainer(self.model)
    
    def predict_proba(self, x: np.ndarray) -> float:
        # Return neutral probability if not trained
        if not self.trained:
            return 0.5
        
        xs = self.scaler.transform(x.reshape(1, -1))
        prob = self.model.predict_proba(xs)[0]

        # Binary → positive class
        if len(prob) == 2:
            return float(prob[1])
        
        # Multi-class → highest probability
        return float(np.max(prob))
    
    def shap_explain(self, x: np.ndarray) -> dict[str, float]:
        # Return zero importance if not trained
        if not self.trained or self._explainer is None:
            return {f: 0.0 for f in FEATURE_NAMES}
        
        xs = self.scaler.transform(x.reshape(1, -1))
        shap_values = self._explainer.shap_values(xs)

        # Handle SHAP output shape differences
        if shap_values.ndim == 2:
            values = shap_values[0]
        else:
            values = shap_values[0][0]

        return {feat: round(float(v), 6) for feat, v in zip(FEATURE_NAMES, values)}
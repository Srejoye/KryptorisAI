class FusionEngine:
    # Default model weights
    W_GB = 0.60
    W_LSTM = 0.40

    # Adaptive weights (when disagreement is high)
    W_GB_LOW = 0.30
    W_LSTM_HIGH = 0.70

    # Risk tuning
    ANOMALY_BOOST = 0.15
    DISAGREEMENT_THRESHOLD = 0.5
    ANOMALY_THRESHOLD = 0.7

    # Classification thresholds
    ATTACK_THRESHOLD = 0.85
    SUSPICIOUS_THRESHOLD = 0.50

    def fuse(self, xgb_prob: float, lstm_prob: float, anomaly_score: float) -> tuple[float, str]:

        disagreement = abs(xgb_prob - lstm_prob)
        if disagreement > self.DISAGREEMENT_THRESHOLD:
            xgb_w = self.W_GB_LOW
            lstm_w = self.W_LSTM_HIGH
        else:
            xgb_w = self.W_GB
            lstm_w = self.W_LSTM

        # Weighted fusion
        base_risk = (xgb_w * xgb_prob) + (lstm_w * lstm_prob)

        # Boost risk if anomaly is strong
        if anomaly_score > self.ANOMALY_THRESHOLD:
            base_risk = min(1.0, base_risk + self.ANOMALY_BOOST * anomaly_score)

        # Final classification
        if base_risk >= self.ATTACK_THRESHOLD:
            cls = "Attack"
        elif base_risk >= self.SUSPICIOUS_THRESHOLD:
            cls = "Suspicious"
        else:
            cls = "Normal"

        return round(base_risk, 4), cls
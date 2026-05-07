import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import DataLoader, TensorDataset
from config import FEATURE_NAMES

class _LSTMNet(nn.Module):
    def __init__(self, input_dim, hidden_dim, num_layers, dropout):
        super().__init__()
        self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden_dim, num_layers=num_layers, batch_first=True, dropout=dropout if num_layers > 1 else 0.0)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_dim, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        out, _ = self.lstm(x)
        out = out[:, -1, :]      # use last timestep
        out = self.dropout(out)
        out = self.fc(out)
        return self.sigmoid(out).squeeze(-1)

class LSTMModel:
    def __init__(self, input_dim=len(FEATURE_NAMES), hidden_dim=64, num_layers=2, dropout=0.3, seq_len=10, lr=1e-3, epochs=20, batch_size=64):
        self.input_dim  = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.dropout    = dropout
        self.seq_len    = seq_len
        self.lr         = lr
        self.epochs     = epochs
        self.batch_size = batch_size
        self.trained    = False

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.net    = _LSTMNet(input_dim, hidden_dim, num_layers, dropout).to(self.device)

    def fit(self, sequences: np.ndarray, y: np.ndarray):
        # Convert to tensors
        X_t = torch.tensor(sequences, dtype=torch.float32, device=self.device)
        y_t = torch.tensor(y, dtype=torch.float32, device=self.device)

        dataset = TensorDataset(X_t, y_t)
        loader  = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        optimizer = torch.optim.Adam(self.net.parameters(), lr=self.lr)
        criterion = nn.BCELoss()

        self.net.train()
        for epoch in range(self.epochs):
            total_loss = 0.0
            for xb, yb in loader:
                optimizer.zero_grad()
                preds = self.net(xb)
                loss = criterion(preds, yb)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

            if (epoch + 1) % 5 == 0 and len(loader) > 0:
                avg = total_loss / len(loader)
                print(f"    Epoch {epoch+1:02d}/{self.epochs}  loss = {avg:.4f}")

        self.trained = True

    def predict_proba(self, sequence: np.ndarray) -> float:
        # Return neutral if not ready
        if not self.trained or len(sequence) < self.seq_len:
            return 0.5

        # Take last seq_len timesteps
        seq = np.array(sequence[-self.seq_len:], dtype=np.float32)
        x_t = torch.tensor(seq, dtype=torch.float32, device=self.device).unsqueeze(0)    # add batch dim

        self.net.eval()
        with torch.no_grad():
            prob = self.net(x_t).item()
        return float(prob)
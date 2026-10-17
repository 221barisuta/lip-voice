"""段階 B: 小型の 1D-CNN。学習のときだけ torch を使う（推論は infer.py の numpy）。"""
import numpy as np

from .augment import augment


def _torch():
    import torch
    return torch


def build(d_in: int, n_cls: int):
    torch = _torch()
    nn = torch.nn

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.c1, self.b1 = nn.Conv1d(d_in, 48, 5, padding=2), nn.BatchNorm1d(48)
            self.c2, self.b2 = nn.Conv1d(48, 64, 5, padding=2), nn.BatchNorm1d(64)
            self.c3, self.b3 = nn.Conv1d(64, 96, 3, padding=1), nn.BatchNorm1d(96)
            self.drop = nn.Dropout(0.3)
            self.fc1, self.fc2 = nn.Linear(192, 64), nn.Linear(64, n_cls)

        def embed(self, x):                                   # x: (N, D, T)
            h = torch.nn.functional.max_pool1d(torch.relu(self.b1(self.c1(x))), 2)
            h = torch.nn.functional.max_pool1d(torch.relu(self.b2(self.c2(h))), 2)
            h = torch.relu(self.b3(self.c3(h)))
            feat = torch.cat([h.mean(-1), h.amax(-1)], dim=1)
            return torch.relu(self.fc1(self.drop(feat)))

        def forward(self, x):
            return self.fc2(self.embed(x))

    return Net()


def _fold(conv, bn) -> tuple[np.ndarray, np.ndarray]:
    """BN を畳み込みの重みに畳み込む（推論を numpy だけで行うため）。"""
    scale = (bn.weight / (bn.running_var + bn.eps).sqrt()).detach().numpy()
    w = conv.weight.detach().numpy() * scale[:, None, None]
    b = (conv.bias.detach().numpy() - bn.running_mean.numpy()) * scale + bn.bias.detach().numpy()
    return w.astype(np.float32), b.astype(np.float32)


def train_cnn(x: np.ndarray, y: np.ndarray, classes: list[str], epochs: int = 60, seed: int = 0,
              batch: int = 32, lr: float = 2e-3, threads: int = 2, log=None) -> dict:
    """x: 標準化済み (N, 64, D)、y: クラス番号。固定エポック・固定シードで、評価日のデータは一切使わない。
    戻り値は、推論用の重み（npz に保存できる辞書）。"""
    torch = _torch()
    torch.set_num_threads(threads)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    n, d_in = len(x), x.shape[2]
    net = build(d_in, len(classes))
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-3)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epochs * ((n + batch - 1) // batch))
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=0.05)
    yt = torch.tensor(y, dtype=torch.long)
    for ep in range(epochs):
        net.train()
        xa = np.stack([augment(x[i], rng) for i in range(n)])
        xt = torch.tensor(xa).permute(0, 2, 1)
        perm = torch.randperm(n)
        total = 0.0
        for s in range(0, n, batch):
            idx = perm[s:s + batch]
            if len(idx) < 2:
                continue
            opt.zero_grad()
            loss = loss_fn(net(xt[idx]), yt[idx])
            loss.backward()
            opt.step()
            sched.step()
            total += float(loss.detach()) * len(idx)
        if log and (ep % 10 == 9 or ep == epochs - 1):
            log(f"  CNN エポック {ep + 1}/{epochs} 損失 {total / n:.3f}")
    net.eval()
    with torch.no_grad():
        emb = net.embed(torch.tensor(x).permute(0, 2, 1)).numpy()
    protos = np.stack([emb[y == k].mean(0) if (y == k).any() else np.zeros(emb.shape[1]) for k in range(len(classes))])
    return export_net(net, protos, classes)


def export_net(net, protos: np.ndarray, classes: list[str]) -> dict:
    """学習済みの net を、numpy で動かせる重みの辞書にする。"""
    c1, c2, c3 = _fold(net.c1, net.b1), _fold(net.c2, net.b2), _fold(net.c3, net.b3)
    return {"c1_w": c1[0], "c1_b": c1[1], "c2_w": c2[0], "c2_b": c2[1], "c3_w": c3[0], "c3_b": c3[1],
            "fc1_w": net.fc1.weight.detach().numpy(), "fc1_b": net.fc1.bias.detach().numpy(),
            "fc2_w": net.fc2.weight.detach().numpy(), "fc2_b": net.fc2.bias.detach().numpy(),
            "prototypes": protos.astype(np.float32), "classes": np.array(classes, dtype="U40")}

"""撮影日で学習と評価を分ける（仕様 8.4）。ランダムには分けない。"""
from typing import Iterable, Sequence


def dates_of(items: Iterable) -> list[str]:
    return sorted({it.date for it in items})


def split_by_date(items: Sequence, eval_dates: Sequence[str] | None = None,
                  train_dates: Sequence[str] | None = None) -> tuple[list, list, dict]:
    """既定は、最新の日を評価、それ以前を学習。日付が 1 日分しかなければ評価しない。"""
    all_dates = dates_of(items)
    ev = list(eval_dates) if eval_dates else (all_dates[-1:] if len(all_dates) >= 2 else [])
    tr = list(train_dates) if train_dates else [d for d in all_dates if d not in ev]
    overlap = set(ev) & set(tr)
    if overlap:
        raise ValueError(f"学習と評価に同じ日が入っています: {sorted(overlap)}")
    missing = (set(ev) | set(tr)) - set(all_dates)
    if missing:
        raise ValueError(f"データのない日が指定されています: {sorted(missing)}")
    train = [it for it in items if it.date in tr]
    test = [it for it in items if it.date in ev]
    return train, test, {"train_dates": tr, "eval_dates": ev, "n_train": len(train), "n_eval": len(test)}


def leave_one_day_out(items: Sequence) -> list[tuple[list[str], str]]:
    """日ごとの交差検証。各日を 1 回ずつ評価に回し、残りの日で学習する。日が 2 日未満なら空。"""
    ds = dates_of(items)
    return [([d for d in ds if d != held], held) for held in ds] if len(ds) >= 2 else []

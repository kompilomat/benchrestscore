#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI-Diagnose: Klick-Automation gegen die realen Referenz-Samples.

Pro Sample: Anzahl Punkte/gefundene/Latches, Fehler je Punkt (mm), Mean/Max;
am Ende Gesamt-Statistik. Fortschritt der Automation-Verbesserung ist damit
ohne pytest-Output ablesbar.

Aufruf:
    .venv/bin/python benchrestscore/evaluate_dataset.py [--dataset DIR]
        [--jitter PX] [--seed N] [--per-point]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchrestscore.reference_eval import (  # noqa: E402
    dataset_root,
    evaluate_automation,
    evaluate_automation_dataset,
    list_reference_samples,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=None,
                        help="Dataset-Wurzel (Default: Repo-datasets/ bzw. "
                             "BRS_REFERENCE_DATASET)")
    parser.add_argument("--jitter", type=float, default=0.0,
                        help="Klick-Versatz in Pixeln (Default: 0)")
    parser.add_argument("--seed", type=int, default=0,
                        help="Seed für den Jitter (Default: 0)")
    parser.add_argument("--per-point", action="store_true",
                        help="Fehler je Punkt ausgeben")
    args = parser.parse_args(argv)

    root = args.dataset or dataset_root()
    samples = list_reference_samples(root)
    if not samples:
        print(f"Keine Samples unter {root}")
        return 1

    agg = evaluate_automation_dataset(samples, click_jitter_px=args.jitter,
                                      seed=args.seed)
    print(f"Dataset: {root}  (jitter={args.jitter:g}px, seed={args.seed})")
    print(f"{'sample':<10} {'pts':>3} {'found':>5} {'lat':>3} "
          f"{'mean':>7} {'max':>7}")
    for r in agg["samples"]:
        mean_s = "--" if r["mean_error_mm"] is None else "%7.2f" % r["mean_error_mm"]
        max_s = "--" if r["max_error_mm"] is None else "%7.2f" % r["max_error_mm"]
        print("%-10s %3d %5d %3d %7s %7s" % (
            r["name"], r["n_manual"], r["n_found"], r["n_latched"],
            mean_s, max_s))
        if args.per_point:
            res = evaluate_automation(os.path.join(root, r["name"]),
                                      click_jitter_px=args.jitter, seed=args.seed)
            for i, e in enumerate(res["errors_mm"]):
                flag = " LATCH" if res["latched"][i] else ""
                print(f"    pt{i}: {'--' if e is None else f'{e:.2f} mm'}{flag}")
    mean_s = "--" if agg["mean_error_mm"] is None else "%7.2f" % agg["mean_error_mm"]
    max_s = "--" if agg["max_error_mm"] is None else "%7.2f" % agg["max_error_mm"]
    print("%-10s %3d %5d %3d %7s %7s" % (
        "TOTAL", agg["total_points"], agg["total_found"], agg["total_latched"],
        mean_s, max_s))
    return 0 if agg["total_latched"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

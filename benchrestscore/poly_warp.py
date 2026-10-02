# -*- coding: utf-8 -*-
"""Grad-3-Polynom-Warp (pro Farbkanal, 20 Parameter) für die Kalierung.

Enthält die reinen, headless testbaren Funktionen: Feature-Basis, analytische
Jacobian und die Newton-Inversion des Warps ( deterministisch, Roundtrip <1 µm`).
"""
import numpy as np

POLY3_N_PARAMS = 20


def poly3_features(xy):
    """Grad-3-Polynom-Features [1,x,y,x^2,xy,y^2,x^3,x^2y,xy^2,y^3] je Koordinate.

    xy: (n,2) NDC-Punkte. Rueckgabe: (n,10)-Feature-Matrix.

    """
    x = xy[:, 0]
    y = xy[:, 1]
    return np.column_stack([
        np.ones_like(x),
        x,
        y,
        x * x,
        x * y,
        y * y,
        x * x * x,
        x * x * y,
        x * y * y,
        y * y * y,
    ])


def poly3_features_jac(xy):
    """Analytische Jacobian der Grad-3-Features nach (x,y.

    Rueckgabe: (n,10,2): J[:,i,0] = d feature_i/dx, J[:,i,1] = d feature_i/dy.


    """
    x = xy[:, 0]
    y = xy[:, 1]
    zeros = np.zeros_like(x)
    ones = np.ones_like(x)
    dx = np.column_stack([
        zeros, ones, zeros,
        2.0 * x, y, zeros,
        3.0 * x * x, 2.0 * x * y,y * y, zeros,
    ])


    dy = np.column_stack([
        zeros, zeros, ones,
        zeros, x, 2.0 * y,
        zeros, x * x, 2.0 * x * y, 3.0 * y * y,
    ])


    return np.stack([dx, dy], axis=2)


def inv_distortion_poly(hpoints, params):
    """Newton-Inversion des Grad-3-Polynom-Warps.

    target liege im verzerrten NDC-Raum; gesucht wird x mit warp(x)=target;
    Start bei target (Warp ~ Identitaet + kleine Stoerung, Jacobian ~ I).


    """
    C = params.reshape(10, 2)
    x = np.copy(hpoints[:, :2])
    for _ in range(10):
        cur = poly3_features(x) @ C
        res = hpoints[:, :2] - cur
        if np.max(np.linalg.norm(res, axis=1)) < 1e-12:
            break
        J = poly3_features_jac(x)  # (n,10,2)
        Jw = np.einsum("nfk,fj->njk", J, C)  # d(warp_j)/d(x_k)  (n,2,2)
        det = Jw[:,0,0] * Jw[:,1,1] - Jw[:,0,1] * Jw[:,1,0]
        inv11 = Jw[:,1,1] / det
        inv12 = -Jw[:,0,1] / det
        inv21 = -Jw[:,1,0] / det
        inv22 = Jw[:,0,0] / det
        x[:,0] += inv11 * res[:,0] + inv12 * res[:,1]
        x[:,1] += inv21 * res[:,0] + inv22 * res[:,1]
    out = np.ones_like(hpoints)
    out[:, :2] = x
    return out
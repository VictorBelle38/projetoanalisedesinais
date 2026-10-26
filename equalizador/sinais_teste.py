"""
Sinais sintéticos para demonstrar o equalizador sem depender de microfone.

Cada função devolve um vetor float (mono) com amplitude dentro de ±1.
"""

from __future__ import annotations

import numpy as np
from scipy import signal


def ruido_branco(fs: float, duracao_s: float = 10.0, amplitude: float = 0.15) -> np.ndarray:
    """Ruído branco: mesma energia em todas as frequências — ótimo para
    "enxergar" a forma de cada filtro no espectro de saída."""
    rng = np.random.default_rng(42)
    return np.clip(amplitude * rng.standard_normal(int(fs * duracao_s)), -1.0, 1.0)


def varredura(fs: float, duracao_s: float = 10.0, f_ini: float = 20.0, f_fim: float = 20000.0,
              amplitude: float = 0.5) -> np.ndarray:
    """Chirp logarítmico de f_ini a f_fim: uma senoide que "passeia" por todo
    o espectro audível. No espectrograma aparece como uma curva subindo."""
    t = np.arange(int(fs * duracao_s)) / fs
    f_fim = min(f_fim, fs / 2 * 0.95)
    return amplitude * signal.chirp(t, f0=f_ini, f1=f_fim, t1=duracao_s, method="logarithmic")


def acorde_com_interferencia(fs: float, duracao_s: float = 10.0, f_ruido: float = 1000.0) -> np.ndarray:
    """
    Acorde musical (Lá maior com harmônicos) + um apito contínuo em `f_ruido`.
    Demonstração do filtro NOTCH: sintonize o notch em 1000 Hz e o apito some,
    enquanto o acorde continua praticamente intacto.
    """
    t = np.arange(int(fs * duracao_s)) / fs
    musica = np.zeros_like(t)
    for f0 in (110.0, 220.0, 277.18, 329.63, 440.0):   # Lá2, Lá3, Dó#4, Mi4, Lá4
        for k, amp in enumerate((1.0, 0.5, 0.25, 0.12), start=1):
            musica += amp * np.sin(2 * np.pi * f0 * k * t)
    # Envelope pulsante (4 "batidas" por segundo) para soar mais musical.
    musica *= 0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 2 * t))
    musica /= np.max(np.abs(musica))
    apito = np.sin(2 * np.pi * f_ruido * t)
    return 0.45 * musica + 0.25 * apito


def zumbido_rede(fs: float, duracao_s: float = 10.0, f_rede: float = 60.0) -> np.ndarray:
    """Ruído rosa suave + zumbido de 60 Hz da rede elétrica e harmônicos (120, 180 Hz)."""
    rng = np.random.default_rng(7)
    n = int(fs * duracao_s)
    # Ruído rosa aproximado: ruído branco filtrado por um passa-baixas de 1ª ordem.
    rosa = signal.lfilter([0.05], [1, -0.95], rng.standard_normal(n))
    rosa /= np.max(np.abs(rosa))
    t = np.arange(n) / fs
    zumbido = sum(a * np.sin(2 * np.pi * f_rede * k * t) for k, a in ((1, 1.0), (2, 0.5), (3, 0.3)))
    return 0.3 * rosa + 0.25 * zumbido / 1.8


SINAIS = {
    "Ruído branco": ruido_branco,
    "Varredura 20 Hz → 20 kHz": varredura,
    "Acorde + apito de 1 kHz": acorde_com_interferencia,
    "Ruído + zumbido 60 Hz": zumbido_rede,
}

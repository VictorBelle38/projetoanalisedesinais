"""
Análise espectral para visualização: FFT de magnitude e espectrograma.

Por que uma janela (Hann)?
    A FFT supõe que o trecho analisado se repete periodicamente. Cortar o
    sinal "a seco" cria descontinuidades nas bordas que espalham energia por
    todo o espectro (vazamento espectral). A janela de Hann vai suavemente a
    zero nas bordas e reduz muito esse vazamento.
"""

from __future__ import annotations

import numpy as np
from scipy import fft as sfft
from scipy import signal


class AnalisadorEspectral:
    """Calcula o espectro de magnitude (dB) de um trecho de N amostras."""

    def __init__(self, n_fft: int, fs: float, suavizacao: float = 0.6):
        self.n_fft = int(n_fft)
        self.fs = float(fs)
        self.janela = signal.windows.hann(self.n_fft, sym=False)
        # Fator de correção para que um seno de amplitude 1 apareça em 0 dBFS.
        self._escala = 2.0 / self.janela.sum()
        # Eixo de frequências das raias da FFT real: k·fs/N, k = 0..N/2
        self.freqs = sfft.rfftfreq(self.n_fft, d=1.0 / self.fs)
        self.suavizacao = suavizacao  # média exponencial entre quadros (0 = sem)
        self._anterior: np.ndarray | None = None

    def espectro_db(self, x: np.ndarray) -> np.ndarray:
        """|X(f)| em dBFS do trecho mais recente de `x`."""
        x = np.asarray(x, dtype=np.float64)[-self.n_fft:]
        if x.size < self.n_fft:
            x = np.pad(x, (self.n_fft - x.size, 0))
        mag = np.abs(sfft.rfft(x * self.janela)) * self._escala
        mag_db = 20.0 * np.log10(mag + 1e-10)
        if self._anterior is not None and self.suavizacao > 0:
            mag_db = self.suavizacao * self._anterior + (1 - self.suavizacao) * mag_db
        self._anterior = mag_db
        return mag_db


def indice_gatilho(x: np.ndarray, janela: int) -> int:
    """
    "Trigger" de osciloscópio: índice da primeira passagem por zero subindo,
    para que a forma de onda fique parada na tela em vez de "correr".
    Garante que ainda restem `janela` amostras depois do índice.
    """
    busca = x[: max(2, x.size - janela)]
    cruzamentos = np.flatnonzero((busca[:-1] < 0) & (busca[1:] >= 0))
    return int(cruzamentos[0]) + 1 if cruzamentos.size else max(0, x.size - janela)

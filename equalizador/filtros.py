"""
Projeto (design) dos filtros digitais usados pelo equalizador.

Este módulo só CALCULA coeficientes; quem aplica os filtros ao áudio, bloco a
bloco, é o `processador.py`. Separar as duas coisas deixa claro que:

    projeto do filtro  ->  coeficientes (b, a) ou SOS
    filtragem          ->  equação de diferenças aplicada às amostras

Convenções:
    fs   : taxa de amostragem em Hz (ex.: 44100)
    SOS  : "second-order sections" — o filtro IIR é quebrado em cascata de
           biquads (ordem 2). É numericamente MUITO mais estável que usar
           (b, a) diretamente em ordens altas.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from scipy import signal


class TipoFiltro(str, Enum):
    """Famílias de filtro disponíveis para o banco de 3 bandas."""

    BUTTERWORTH = "Butterworth (IIR)"
    CHEBYSHEV = "Chebyshev I (IIR)"
    FIR = "FIR janela de Hamming"


# Ondulação (ripple) máxima permitida na banda passante do Chebyshev tipo I.
# Quanto maior, mais íngreme a transição — e mais "ondulada" a banda passante.
RIPPLE_CHEBYSHEV_DB = 1.0


def _normalizar(freq_hz: float, fs: float) -> float:
    """Converte Hz em frequência normalizada (0..1, onde 1 = Nyquist = fs/2)."""
    nyquist = fs / 2.0
    # Limita para não pedir ao SciPy algo em 0 ou exatamente em Nyquist.
    return float(np.clip(freq_hz / nyquist, 1e-5, 0.9999))


# ---------------------------------------------------------------------------
# Filtros IIR básicos
# ---------------------------------------------------------------------------

def projetar_iir(
    tipo: TipoFiltro,
    ordem: int,
    corte_hz: float | tuple[float, float],
    btype: str,
    fs: float,
) -> np.ndarray:
    """
    Projeta um filtro IIR e devolve seus coeficientes em SOS.

    btype: 'lowpass', 'highpass' ou 'bandpass'.
    Para 'bandpass', `corte_hz` é a tupla (f_inferior, f_superior).
    Obs.: em passa-faixa o SciPy dobra a ordem (cada polo vira um par).
    """
    if isinstance(corte_hz, tuple):
        wn = [_normalizar(corte_hz[0], fs), _normalizar(corte_hz[1], fs)]
    else:
        wn = _normalizar(corte_hz, fs)

    if tipo == TipoFiltro.BUTTERWORTH:
        # Butterworth: resposta "maximamente plana" na banda passante.
        return signal.butter(ordem, wn, btype=btype, output="sos")
    if tipo == TipoFiltro.CHEBYSHEV:
        # Chebyshev I: transição mais íngreme, ao custo de ripple na passante.
        return signal.cheby1(ordem, RIPPLE_CHEBYSHEV_DB, wn, btype=btype, output="sos")
    raise ValueError(f"Tipo IIR inválido: {tipo}")


def projetar_notch(f0_hz: float, q: float, fs: float) -> np.ndarray:
    """
    Filtro notch (rejeita-faixa estreito) centrado em f0.

    Q = f0 / largura_de_banda(-3 dB). Q alto -> entalhe bem estreito,
    removendo só a frequência do ruído (ex.: zumbido de 60 Hz da rede).

    Ele coloca um par de ZEROS exatamente sobre o círculo unitário em
    e^{±j·2π·f0/fs} (anula f0) e um par de POLOS logo atrás, com o mesmo
    ângulo, que "devolve" o ganho para as frequências vizinhas.
    """
    f0_hz = float(np.clip(f0_hz, 1.0, fs / 2 * 0.999))
    b, a = signal.iirnotch(f0_hz, q, fs=fs)
    return signal.tf2sos(b, a)


def projetar_passa_baixas(corte_hz: float, fs: float, ordem: int = 4) -> np.ndarray:
    """Passa-baixas Butterworth com frequência de corte ajustável."""
    return projetar_iir(TipoFiltro.BUTTERWORTH, ordem, corte_hz, "lowpass", fs)


# ---------------------------------------------------------------------------
# Filtros FIR
# ---------------------------------------------------------------------------

def _impulso(n_taps: int) -> np.ndarray:
    """Delta de Kronecker centrado (o "filtro que não faz nada", com atraso)."""
    d = np.zeros(n_taps)
    d[n_taps // 2] = 1.0
    return d


def projetar_fir_passa_baixas(corte_hz: float, fs: float, n_taps: int) -> np.ndarray:
    """FIR passa-baixas por método da janela (sinc truncada × Hamming)."""
    return signal.firwin(n_taps, corte_hz, window="hamming", fs=fs)


# ---------------------------------------------------------------------------
# Banco de filtros de 3 bandas (graves / médios / agudos)
# ---------------------------------------------------------------------------

@dataclass
class BancoIIR:
    """Três filtros IIR independentes, um por banda (formato SOS)."""

    graves: np.ndarray   # passa-baixas  em f1
    medios: np.ndarray   # passa-faixa   entre f1 e f2
    agudos: np.ndarray   # passa-altas   em f2


@dataclass
class BancoFIR:
    """Três respostas ao impulso FIR (todas com o mesmo comprimento)."""

    graves: np.ndarray
    medios: np.ndarray
    agudos: np.ndarray


def projetar_banco(
    tipo: TipoFiltro,
    ordem: int,
    f1_hz: float,
    f2_hz: float,
    fs: float,
    n_taps_fir: int = 511,
) -> BancoIIR | BancoFIR:
    """
    Projeta o banco de 3 bandas com frequências de cruzamento f1 < f2.

        graves : 0  .. f1
        médios : f1 .. f2
        agudos : f2 .. fs/2

    IIR: cada banda é um filtro independente. A soma das três bandas com
         ganho 0 dB NÃO é perfeitamente plana (as fases não se alinham nas
         frequências de cruzamento) — dá para ver isso no gráfico de resposta.

    FIR: usamos "inversão espectral" para que as bandas sejam complementares:
         h_graves + h_medios + h_agudos = delta  ->  com ganhos iguais, a
         saída é exatamente a entrada atrasada (reconstrução perfeita).
    """
    if f2_hz <= f1_hz:
        f2_hz = f1_hz * 1.05

    if tipo == TipoFiltro.FIR:
        # n_taps ímpar -> filtro tipo I (fase linear, atraso inteiro).
        if n_taps_fir % 2 == 0:
            n_taps_fir += 1
        h_lp1 = projetar_fir_passa_baixas(f1_hz, fs, n_taps_fir)
        h_lp2 = projetar_fir_passa_baixas(f2_hz, fs, n_taps_fir)
        delta = _impulso(n_taps_fir)
        graves = h_lp1                 # passa-baixas em f1
        agudos = delta - h_lp2         # passa-altas em f2 (inversão espectral)
        medios = h_lp2 - h_lp1         # o que sobra entre f1 e f2
        return BancoFIR(graves, medios, agudos)

    # Um passa-faixa de "ordem N" no SciPy tem 2N polos: N para cada borda.
    # Assim cada lado cai com a mesma inclinação das bandas vizinhas.
    return BancoIIR(
        graves=projetar_iir(tipo, ordem, f1_hz, "lowpass", fs),
        medios=projetar_iir(tipo, ordem, (f1_hz, f2_hz), "bandpass", fs),
        agudos=projetar_iir(tipo, ordem, f2_hz, "highpass", fs),
    )


# ---------------------------------------------------------------------------
# Resposta em frequência (para o gráfico didático)
# ---------------------------------------------------------------------------

def resposta_sos(sos: np.ndarray, freqs_hz: np.ndarray, fs: float) -> np.ndarray:
    """H(f) complexo de um filtro SOS nas frequências pedidas."""
    _, h = signal.sosfreqz(sos, worN=freqs_hz, fs=fs)
    return h


def resposta_fir(h: np.ndarray, freqs_hz: np.ndarray, fs: float) -> np.ndarray:
    """H(f) complexo de um filtro FIR nas frequências pedidas."""
    _, resp = signal.freqz(h, 1.0, worN=freqs_hz, fs=fs)
    return resp


def db(valor: np.ndarray | float, piso_db: float = -120.0) -> np.ndarray:
    """Converte magnitude linear em decibéis: 20·log10(|x|)."""
    return np.maximum(20.0 * np.log10(np.abs(valor) + 1e-12), piso_db)


def ganho_linear(ganho_db: float) -> float:
    """Converte dB em ganho linear: 10^(dB/20)."""
    return float(10.0 ** (ganho_db / 20.0))

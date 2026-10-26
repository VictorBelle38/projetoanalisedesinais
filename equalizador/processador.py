"""
Processador de áudio em tempo real (bloco a bloco).

O áudio chega da placa de som em blocos pequenos (ex.: 512 amostras ≈ 11 ms).
Para que a saída seja idêntica à de filtrar o sinal inteiro de uma vez, cada
filtro precisa LEMBRAR seu estado entre um bloco e o próximo:

    IIR -> estado interno `zi` dos biquads (sosfilt devolve o estado final)
    FIR -> as últimas (N-1) amostras de entrada (histórico da convolução)

Cadeia de processamento:

    entrada ─┬─ graves (×g1) ─┐
             ├─ médios (×g2) ─┼─ Σ ─ notch ─ passa-baixas ─ ×ganho_saída ─ saída
             └─ agudos (×g3) ─┘

A interface gráfica roda em outra thread e pode mudar parâmetros a qualquer
momento; por isso os coeficientes são recalculados FORA do callback de áudio
e trocados de forma atômica sob um `threading.Lock`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace

import numpy as np
from scipy import signal

from . import filtros
from .filtros import BancoFIR, BancoIIR, TipoFiltro


@dataclass(frozen=True)
class ParametrosEQ:
    """Todos os controles da interface, em unidades "humanas" (Hz e dB)."""

    # Banco de filtros
    tipo: TipoFiltro = TipoFiltro.BUTTERWORTH
    ordem: int = 4
    f1_hz: float = 250.0          # cruzamento graves/médios
    f2_hz: float = 4000.0         # cruzamento médios/agudos
    ganho_graves_db: float = 0.0
    ganho_medios_db: float = 0.0
    ganho_agudos_db: float = 0.0
    # Filtragem seletiva
    notch_ativo: bool = False
    notch_f0_hz: float = 1000.0
    notch_q: float = 30.0
    pb_ativo: bool = False
    pb_corte_hz: float = 8000.0
    # Saída
    ganho_saida_db: float = 0.0
    bypass: bool = False


class _EstagioSOS:
    """Um filtro IIR (em SOS) com estado persistente entre blocos."""

    def __init__(self, sos: np.ndarray, canais: int):
        self.sos = sos
        self.zi = np.zeros((sos.shape[0], 2, canais))

    def trocar_coeficientes(self, sos: np.ndarray) -> None:
        # Se a estrutura é a mesma (mesmo nº de biquads), mantemos o estado:
        # assim, arrastar um slider não "zera" o filtro e evita estalos.
        if sos.shape != self.sos.shape:
            self.zi = np.zeros((sos.shape[0], 2, self.zi.shape[2]))
        self.sos = sos

    def processar(self, x: np.ndarray) -> np.ndarray:
        y, self.zi = signal.sosfilt(self.sos, x, axis=0, zi=self.zi)
        return y


class ProcessadorEQ:
    """Equalizador de 3 bandas + notch + passa-baixas, com estado entre blocos."""

    N_TAPS_FIR = 511  # ímpar: fase linear com atraso de 255 amostras (~5,8 ms @44,1 kHz)

    def __init__(self, fs: float, canais: int = 1, params: ParametrosEQ | None = None):
        self.fs = float(fs)
        self.canais = canais
        self._lock = threading.Lock()
        self.params = params or ParametrosEQ()

        self._banco: BancoIIR | BancoFIR | None = None
        self._bandas_iir: list[_EstagioSOS] = []
        self._hist_fir = np.zeros((self.N_TAPS_FIR - 1, canais))
        self._notch = _EstagioSOS(filtros.projetar_notch(1000, 30, self.fs), canais)
        self._pb = _EstagioSOS(filtros.projetar_passa_baixas(8000, self.fs), canais)

        # Ganhos lineares "atuais" (suavizados) e "alvo" — ver _rampa().
        self._g_atual = np.ones(4)  # graves, médios, agudos, saída
        self._g_alvo = np.ones(4)

        self.pico_entrada = 0.0
        self.pico_saida = 0.0

        self._aplicar(self.params, primeira_vez=True)

    # ------------------------------------------------------------------ API

    def atualizar(self, **mudancas) -> ParametrosEQ:
        """Altera parâmetros (ex.: atualizar(ganho_graves_db=6)). Thread-safe."""
        novos = replace(self.params, **mudancas)
        self._aplicar(novos)
        return novos

    def processar(self, x: np.ndarray) -> np.ndarray:
        """
        Processa um bloco de áudio.
        x: array (amostras,) ou (amostras, canais) em float, faixa ±1.
        """
        mono = x.ndim == 1
        if mono:
            x = x[:, None]
        x = x.astype(np.float64, copy=False)

        with self._lock:
            bandas = self._filtrar_bandas(x)            # (3, n, canais)
            g = self._rampa(x.shape[0])                 # (4, n, 1)
            y = (bandas * g[:3]).sum(axis=0)            # soma ponderada das bandas
            if self.params.notch_ativo:
                y = self._notch.processar(y)
            if self.params.pb_ativo:
                y = self._pb.processar(y)
            y = y * g[3]
            if self.params.bypass:
                y = x.copy()

        # Proteção contra saturação: o DAC só aceita ±1.
        y = np.clip(y, -1.0, 1.0)
        self.pico_entrada = float(np.max(np.abs(x))) if x.size else 0.0
        self.pico_saida = float(np.max(np.abs(y))) if y.size else 0.0
        return y[:, 0] if mono else y

    def resposta_em_frequencia(self, freqs_hz: np.ndarray) -> dict[str, np.ndarray]:
        """
        Resposta teórica H(f) de cada banda (já com ganho) e da cadeia completa.
        Usada no gráfico "Resposta dos filtros" da interface.
        """
        with self._lock:
            p, banco = self.params, self._banco
            notch_sos, pb_sos = self._notch.sos, self._pb.sos

        if isinstance(banco, BancoFIR):
            resp = lambda h: filtros.resposta_fir(h, freqs_hz, self.fs)  # noqa: E731
        else:
            resp = lambda s: filtros.resposta_sos(s, freqs_hz, self.fs)  # noqa: E731

        g = [filtros.ganho_linear(p.ganho_graves_db),
             filtros.ganho_linear(p.ganho_medios_db),
             filtros.ganho_linear(p.ganho_agudos_db)]
        h_graves = g[0] * resp(banco.graves)
        h_medios = g[1] * resp(banco.medios)
        h_agudos = g[2] * resp(banco.agudos)

        total = h_graves + h_medios + h_agudos
        if p.notch_ativo:
            total = total * filtros.resposta_sos(notch_sos, freqs_hz, self.fs)
        if p.pb_ativo:
            total = total * filtros.resposta_sos(pb_sos, freqs_hz, self.fs)
        total = total * filtros.ganho_linear(p.ganho_saida_db)
        if p.bypass:
            total = np.ones_like(total)

        return {"graves": h_graves, "medios": h_medios, "agudos": h_agudos, "total": total}

    def reiniciar_estado(self) -> None:
        """Zera a "memória" dos filtros (útil ao trocar de fonte de áudio)."""
        with self._lock:
            for est in [*self._bandas_iir, self._notch, self._pb]:
                est.zi[:] = 0.0
            self._hist_fir[:] = 0.0

    # ------------------------------------------------------------ internos

    def _aplicar(self, p: ParametrosEQ, primeira_vez: bool = False) -> None:
        antigo = self.params
        refazer_banco = primeira_vez or (
            (p.tipo, p.ordem, p.f1_hz, p.f2_hz) != (antigo.tipo, antigo.ordem, antigo.f1_hz, antigo.f2_hz)
        )

        # 1) Projeto dos filtros — feito FORA do lock (pode levar alguns ms).
        banco = (filtros.projetar_banco(p.tipo, p.ordem, p.f1_hz, p.f2_hz, self.fs, self.N_TAPS_FIR)
                 if refazer_banco else None)
        notch = filtros.projetar_notch(p.notch_f0_hz, p.notch_q, self.fs)
        pb = filtros.projetar_passa_baixas(p.pb_corte_hz, self.fs)
        alvo = np.array([
            filtros.ganho_linear(p.ganho_graves_db),
            filtros.ganho_linear(p.ganho_medios_db),
            filtros.ganho_linear(p.ganho_agudos_db),
            filtros.ganho_linear(p.ganho_saida_db),
        ])

        # 2) Troca atômica — o callback de áudio nunca vê um estado "meio novo".
        with self._lock:
            if banco is not None:
                self._instalar_banco(banco)
            self._notch.trocar_coeficientes(notch)
            self._pb.trocar_coeficientes(pb)
            self._g_alvo = alvo
            if primeira_vez:
                self._g_atual = alvo.copy()
            self.params = p

    def _instalar_banco(self, banco: BancoIIR | BancoFIR) -> None:
        if isinstance(banco, BancoIIR):
            novos = [banco.graves, banco.medios, banco.agudos]
            if len(self._bandas_iir) == 3:
                for est, sos in zip(self._bandas_iir, novos):
                    est.trocar_coeficientes(sos)
            else:
                self._bandas_iir = [_EstagioSOS(sos, self.canais) for sos in novos]
        else:
            self._bandas_iir = []
        self._banco = banco

    def _filtrar_bandas(self, x: np.ndarray) -> np.ndarray:
        banco = self._banco
        if isinstance(banco, BancoFIR):
            # Convolução com histórico: concatena as últimas N-1 amostras do
            # bloco anterior e usa modo 'valid' -> sai exatamente len(x) amostras.
            xh = np.concatenate([self._hist_fir, x], axis=0)
            self._hist_fir = xh[-(self.N_TAPS_FIR - 1):]
            return np.stack([
                signal.oaconvolve(xh, h[:, None], mode="valid", axes=0)
                for h in (banco.graves, banco.medios, banco.agudos)
            ])
        return np.stack([est.processar(x) for est in self._bandas_iir])

    def _rampa(self, n: int) -> np.ndarray:
        """
        Interpola os ganhos do valor atual até o alvo ao longo do bloco.
        Mudar o ganho "de degrau" gera um clique audível ("zipper noise");
        uma rampa linear de um bloco (~10 ms) elimina o problema.
        """
        t = np.linspace(0.0, 1.0, n, endpoint=False)[None, :, None]
        g = self._g_atual[:, None, None] + (self._g_alvo - self._g_atual)[:, None, None] * t
        self._g_atual = self._g_alvo.copy()
        return g

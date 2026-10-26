"""
Entrada e saída de áudio com SoundDevice (PortAudio).

Dois modos de operação:

    Microfone  : sd.Stream (duplex). A cada bloco, PortAudio chama
                 `_callback_duplex` com as amostras capturadas (indata) e um
                 buffer vazio (outdata) que precisamos preencher.
    Arquivo    : sd.OutputStream. O "microfone" é um vetor na memória
                 (arquivo .wav/.mp3 ou sinal de teste), lido em loop.

IMPORTANTE: o callback roda numa thread de alta prioridade da placa de som.
Ele precisa terminar antes do próximo bloco (~11 ms com 512 amostras), então
nada de print, desenho de gráfico ou leitura de disco ali dentro.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from .buffer_circular import BufferCircular
from .processador import ParametrosEQ, ProcessadorEQ

CAPACIDADE_BUFFER = 1 << 16  # 65536 amostras ≈ 1,5 s @ 44,1 kHz


def carregar_arquivo(caminho: str | Path) -> tuple[np.ndarray, int]:
    """Lê .wav/.mp3/.flac/.ogg e devolve (dados (amostras, canais), fs)."""
    dados, fs = sf.read(str(caminho), dtype="float32", always_2d=True)
    if dados.shape[1] > 2:          # mais de 2 canais: mixa para estéreo
        dados = dados[:, :2]
    return dados, int(fs)


def listar_dispositivos() -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """(entradas, saídas) como listas de (índice, nome) — só da API padrão do sistema."""
    api_padrao = sd.default.hostapi
    entradas, saidas = [], []
    for i, d in enumerate(sd.query_devices()):
        if d["hostapi"] != api_padrao:
            continue
        if d["max_input_channels"] > 0:
            entradas.append((i, d["name"]))
        if d["max_output_channels"] > 0:
            saidas.append((i, d["name"]))
    return entradas, saidas


class MotorAudio:
    """Liga fonte de áudio -> processador -> saída e alimenta os buffers de visualização."""

    def __init__(self, bloco: int = 512, fs_microfone: int = 44100):
        self.bloco = bloco
        self.fs_microfone = fs_microfone
        self.params = ParametrosEQ()
        self.processador = ProcessadorEQ(fs_microfone, 1, self.params)
        self.fs = fs_microfone

        self.buf_entrada = BufferCircular(CAPACIDADE_BUFFER)
        self.buf_saida = BufferCircular(CAPACIDADE_BUFFER)

        self._stream: sd.Stream | sd.OutputStream | None = None
        self._dados: np.ndarray | None = None  # fonte "arquivo" (amostras, canais)
        self._pos = 0
        self.falhas = 0       # under/overflows reportados pela placa
        self.modo = "parado"

    # ------------------------------------------------------- parâmetros

    def atualizar(self, **mudancas) -> None:
        self.params = replace(self.params, **mudancas)
        self.processador.atualizar(**mudancas)

    def _novo_processador(self, fs: int, canais: int) -> None:
        # Os coeficientes dependem de fs e o estado depende do nº de canais.
        self.fs = fs
        self.processador = ProcessadorEQ(fs, canais, self.params)
        self.buf_entrada.limpar()
        self.buf_saida.limpar()

    # ------------------------------------------------------------ modos

    def iniciar_microfone(self, disp_entrada: int | None = None, disp_saida: int | None = None) -> None:
        self.parar()
        self._novo_processador(self.fs_microfone, 1)
        self._stream = sd.Stream(
            samplerate=self.fs_microfone,
            blocksize=self.bloco,
            device=(disp_entrada, disp_saida),
            channels=(1, self._canais_saida(disp_saida)),
            dtype="float32",
            latency="low",
            callback=self._callback_duplex,
        )
        self._stream.start()
        self.modo = "microfone"

    def iniciar_reproducao(self, dados: np.ndarray, fs: int, disp_saida: int | None = None) -> None:
        """Reproduz (em loop) um vetor de áudio — arquivo ou sinal de teste."""
        self.parar()
        if dados.ndim == 1:
            dados = dados[:, None]
        self._dados = np.ascontiguousarray(dados, dtype=np.float32)
        self._pos = 0
        self._novo_processador(fs, self._dados.shape[1])
        self._stream = sd.OutputStream(
            samplerate=fs,
            blocksize=self.bloco,
            device=disp_saida,
            channels=self._canais_saida(disp_saida),
            dtype="float32",
            latency="low",
            callback=self._callback_reproducao,
        )
        self._stream.start()
        self.modo = "arquivo"

    def parar(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.modo = "parado"

    @property
    def ativo(self) -> bool:
        return self._stream is not None and self._stream.active

    @property
    def latencia_ms(self) -> float:
        if self._stream is None:
            return 0.0
        lat = self._stream.latency
        return 1000.0 * (sum(lat) if isinstance(lat, tuple) else lat)

    @property
    def progresso(self) -> tuple[float, float]:
        """(posição, duração) em segundos da fonte "arquivo"."""
        if self._dados is None or self.modo != "arquivo":
            return 0.0, 0.0
        return self._pos / self.fs, self._dados.shape[0] / self.fs

    @staticmethod
    def _canais_saida(disp_saida: int | None) -> int:
        info = sd.query_devices(disp_saida if disp_saida is not None else sd.default.device[1])
        return max(1, min(2, int(info["max_output_channels"])))

    # --------------------------------------------------------- callbacks

    def _callback_duplex(self, indata, outdata, frames, tempo, status) -> None:
        if status:
            self.falhas += 1
        x = indata[:, 0].copy()
        y = self.processador.processar(x)
        outdata[:] = y[:, None]            # mono -> todos os canais de saída
        self.buf_entrada.escrever(x)
        self.buf_saida.escrever(y)

    def _callback_reproducao(self, outdata, frames, tempo, status) -> None:
        if status:
            self.falhas += 1
        dados = self._dados
        n_total = dados.shape[0]
        # Lê `frames` amostras a partir de _pos, dando a volta no fim (loop).
        idx = (self._pos + np.arange(frames)) % n_total
        self._pos = int((self._pos + frames) % n_total)
        x = dados[idx]                      # (frames, canais_fonte)
        y = self.processador.processar(x)

        canais_saida = outdata.shape[1]
        if y.shape[1] == canais_saida:
            outdata[:] = y
        elif y.shape[1] == 1:
            outdata[:] = y                  # broadcast mono -> estéreo
        else:
            outdata[:] = y.mean(axis=1, keepdims=True)

        self.buf_entrada.escrever(x.mean(axis=1))
        self.buf_saida.escrever(y.mean(axis=1))

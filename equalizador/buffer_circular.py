"""
Buffer circular (ring buffer) para passar áudio da thread de áudio para a
thread da interface gráfica.

A placa de som entrega blocos a cada ~10 ms, mas a tela redesenha só a cada
~33 ms (30 FPS). O buffer guarda sempre as ÚLTIMAS `capacidade` amostras:
quando chega ao fim, volta ao início e sobrescreve as mais antigas.

    índice:   0   1   2   3   4   5   6   7
            [ e | f | g | h | a | b | c | d ]
                          ^ pos_escrita (próxima posição a ser escrita)
    ordem cronológica: a b c d e f g h
"""

from __future__ import annotations

import threading

import numpy as np


class BufferCircular:
    def __init__(self, capacidade: int):
        self.capacidade = int(capacidade)
        self._dados = np.zeros(self.capacidade, dtype=np.float32)
        self._pos = 0              # próxima posição de escrita
        self._total_escrito = 0    # contador para saber se há dados novos
        self._lock = threading.Lock()

    def escrever(self, bloco: np.ndarray) -> None:
        """Acrescenta amostras (mono). Blocos maiores que a capacidade mantêm só o final."""
        bloco = np.asarray(bloco, dtype=np.float32).ravel()
        n = bloco.size
        if n == 0:
            return
        with self._lock:
            if n >= self.capacidade:
                self._dados[:] = bloco[-self.capacidade:]
                self._pos = 0
            else:
                fim = self._pos + n
                if fim <= self.capacidade:
                    self._dados[self._pos:fim] = bloco
                else:  # dá a volta no final do vetor
                    corte = self.capacidade - self._pos
                    self._dados[self._pos:] = bloco[:corte]
                    self._dados[: n - corte] = bloco[corte:]
                self._pos = fim % self.capacidade
            self._total_escrito += n

    def ler_ultimas(self, n: int) -> np.ndarray:
        """Devolve as últimas `n` amostras em ordem cronológica (cópia)."""
        n = min(int(n), self.capacidade)
        with self._lock:
            inicio = (self._pos - n) % self.capacidade
            if inicio + n <= self.capacidade:
                return self._dados[inicio:inicio + n].copy()
            return np.concatenate([self._dados[inicio:], self._dados[: (inicio + n) % self.capacidade]])

    @property
    def total_escrito(self) -> int:
        return self._total_escrito

    def limpar(self) -> None:
        with self._lock:
            self._dados[:] = 0.0
            self._pos = 0

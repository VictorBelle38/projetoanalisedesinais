"""Widgets auxiliares da interface."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from .ajuda import BotaoInfo

PASSOS = 10000  # resolução interna do QSlider (que só trabalha com inteiros)


class SliderRotulado(QWidget):
    """
    Slider com título e valor formatado. Em escala `log=True` cada oitava
    ocupa o mesmo espaço — é assim que o ouvido percebe frequência
    (de 100 para 200 Hz soa como "o mesmo salto" que de 1000 para 2000 Hz).
    """

    valorMudou = Signal(float)

    def __init__(self, titulo: str, minimo: float, maximo: float, inicial: float,
                 unidade: str = "", log: bool = False, casas: int = 0, info: str | None = None):
        super().__init__()
        self.minimo, self.maximo, self.log = minimo, maximo, log
        self.unidade, self.casas = unidade, casas

        self._titulo = QLabel(titulo)
        self._valor = QLabel()
        self._valor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._valor.setMinimumWidth(80)
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, PASSOS)

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.addWidget(self._titulo)
        if info:
            topo.addSpacing(4)
            topo.addWidget(BotaoInfo(info))
        topo.addStretch()
        topo.addWidget(self._valor)
        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(0, 2, 0, 2)
        coluna.setSpacing(0)
        coluna.addLayout(topo)
        coluna.addWidget(self._slider)

        self._slider.valueChanged.connect(self._ao_mover)
        self.definir(inicial)

    # posição inteira do slider <-> valor físico
    def _para_valor(self, pos: int) -> float:
        frac = pos / PASSOS
        if self.log:
            return math.exp(math.log(self.minimo) + frac * (math.log(self.maximo) - math.log(self.minimo)))
        return self.minimo + frac * (self.maximo - self.minimo)

    def _para_pos(self, valor: float) -> int:
        valor = min(max(valor, self.minimo), self.maximo)
        if self.log:
            frac = (math.log(valor) - math.log(self.minimo)) / (math.log(self.maximo) - math.log(self.minimo))
        else:
            frac = (valor - self.minimo) / (self.maximo - self.minimo)
        return round(frac * PASSOS)

    def valor(self) -> float:
        return round(self._para_valor(self._slider.value()), self.casas)

    def definir(self, valor: float) -> None:
        self._slider.setValue(self._para_pos(valor))
        self._mostrar()

    def _mostrar(self) -> None:
        v = self.valor()
        if self.unidade == "Hz" and v >= 1000:
            texto = f"{v / 1000:.2f} kHz"
        elif self.unidade == "dB":
            texto = f"{v:+.{self.casas}f} dB"
        else:
            texto = f"{v:.{self.casas}f} {self.unidade}".strip()
        self._valor.setText(f"<b>{texto}</b>")

    def _ao_mover(self, _pos: int) -> None:
        self._mostrar()
        self.valorMudou.emit(self.valor())

"""
Janela principal: painel de controles à esquerda e 4 gráficos à direita.

    ┌──────────────┬────────────────────────┬────────────────────────┐
    │  Fonte       │  Osciloscópio (tempo)  │  Espectro FFT (freq.)  │
    │  Banco 3 b.  ├────────────────────────┼────────────────────────┤
    │  Notch / PB  │  Espectrograma         │  Resposta dos filtros  │
    │  Saída       │                        │  |H(f)| teórica        │
    └──────────────┴────────────────────────┴────────────────────────┘

Os gráficos são atualizados por um QTimer (~30 FPS) que lê os buffers
circulares preenchidos pela thread de áudio.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from .. import filtros, sinais_teste
from ..analise import AnalisadorEspectral, indice_gatilho
from ..audio_io import MotorAudio, carregar_arquivo, listar_dispositivos
from ..filtros import TipoFiltro
from ..processador import ParametrosEQ
from .ajuda import BotaoInfo
from .widgets import SliderRotulado

pg.setConfigOptions(antialias=True, imageAxisOrder="row-major")

FONTE_MIC = "🎤 Microfone (tempo real)"
FONTE_ARQ = "📁 Arquivo de áudio (.wav / .mp3)"

COR_ENTRADA = (150, 150, 150)
COR_SAIDA = (0, 200, 255)
COR_BANDAS = {"graves": (255, 120, 80), "medios": (120, 220, 120), "agudos": (190, 130, 255)}

N_FFT = 4096
COLUNAS_ESPECTROGRAMA = 300
LINHAS_ESPECTROGRAMA = 256
INTERVALO_MS = 33
F_MIN = 20.0


def _rotulos_log(eixo: pg.AxisItem, f_max: float) -> None:
    """Rótulos em Hz para um eixo cujos valores estão em log10(f)."""
    marcas = [f for f in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000) if f <= f_max]
    eixo.setTicks([[(np.log10(f), f"{f // 1000}k" if f >= 1000 else str(f)) for f in marcas]])


def _com_info(widget: QWidget, chave: str) -> QWidget:
    """Coloca um ícone ⓘ ao lado de um controle."""
    caixa = QWidget()
    linha = QHBoxLayout(caixa)
    linha.setContentsMargins(0, 0, 0, 0)
    linha.addWidget(widget, stretch=1)
    linha.addWidget(BotaoInfo(chave), alignment=Qt.AlignTop)
    return caixa


class JanelaPrincipal(QMainWindow):
    def __init__(self, bloco: int = 512, fs_microfone: int = 44100):
        super().__init__()
        self.setWindowTitle("Equalizador Paramétrico e Filtragem de Áudio em Tempo Real")
        self.resize(1500, 900)

        self.motor = MotorAudio(bloco=bloco, fs_microfone=fs_microfone)
        self._arquivo: tuple[np.ndarray, int] | None = None
        self._fs_graficos = 0.0
        self._ultimo_total = 0

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self._montar_painel_controles())
        layout.addWidget(self._montar_graficos(), stretch=1)
        self.setCentralWidget(central)

        self._preparar_analisadores(self.motor.fs)
        self._atualizar_resposta()
        self._atualizar_marcadores()

        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._alternar_play)
        QShortcut(QKeySequence("B"), self, activated=lambda: self.chk_bypass.toggle())

        self._timer = QTimer(self, interval=INTERVALO_MS, timeout=self._atualizar_graficos)
        self._timer.start()

    # =========================================================== controles

    def _montar_painel_controles(self) -> QWidget:
        painel = QWidget()
        col = QVBoxLayout(painel)
        col.addWidget(self._grupo_fonte())
        col.addWidget(self._grupo_banco())
        col.addWidget(self._grupo_seletivo())
        col.addWidget(self._grupo_saida())
        col.addStretch()

        rolagem = QScrollArea()
        rolagem.setWidget(painel)
        rolagem.setWidgetResizable(True)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rolagem.setFixedWidth(390)
        return rolagem

    def _grupo_fonte(self) -> QGroupBox:
        g = QGroupBox("1. Fonte de áudio")
        form = QFormLayout(g)

        self.cmb_fonte = QComboBox()
        self.cmb_fonte.addItems([FONTE_MIC, FONTE_ARQ, *[f"🔊 Teste: {n}" for n in sinais_teste.SINAIS]])
        self.cmb_fonte.setCurrentIndex(2)  # começa com ruído branco: funciona em qualquer PC
        self.cmb_fonte.currentIndexChanged.connect(self._ao_trocar_fonte)
        form.addRow(_com_info(self.cmb_fonte, "fonte"))

        self.btn_abrir = QPushButton("Abrir arquivo…")
        self.btn_abrir.clicked.connect(self._abrir_arquivo)
        self.lbl_arquivo = QLabel("<i>nenhum arquivo</i>")
        self.lbl_arquivo.setWordWrap(True)
        form.addRow(self.btn_abrir, self.lbl_arquivo)

        entradas, saidas = listar_dispositivos()
        self.cmb_entrada = QComboBox()
        self.cmb_saida = QComboBox()
        for cmb, lista in ((self.cmb_entrada, entradas), (self.cmb_saida, saidas)):
            cmb.addItem("Padrão do sistema", None)
            for idx, nome in lista:
                cmb.addItem(nome, idx)
            cmb.setMaximumWidth(210)
        form.addRow("Entrada:", _com_info(self.cmb_entrada, "dispositivos"))
        form.addRow("Saída:", self.cmb_saida)

        self.btn_play = QPushButton("▶  Iniciar  (Espaço)")
        self.btn_play.setMinimumHeight(36)
        self.btn_play.clicked.connect(self._alternar_play)
        form.addRow(self.btn_play)

        self.lbl_status = QLabel("Parado.")
        self.lbl_status.setWordWrap(True)
        form.addRow(_com_info(self.lbl_status, "status"))
        self._ao_trocar_fonte()
        return g

    def _grupo_banco(self) -> QGroupBox:
        g = QGroupBox("2. Banco de filtros (3 bandas)")
        col = QVBoxLayout(g)
        p = ParametrosEQ()

        linha = QHBoxLayout()
        self.cmb_tipo = QComboBox()
        for t in TipoFiltro:
            self.cmb_tipo.addItem(t.value, t)
        self.cmb_tipo.currentIndexChanged.connect(self._ao_trocar_tipo)
        self.spn_ordem = QSpinBox(minimum=1, maximum=8, value=p.ordem, prefix="ordem ")
        self.spn_ordem.valueChanged.connect(lambda v: self._mudar(ordem=v))
        linha.addWidget(self.cmb_tipo, stretch=1)
        linha.addWidget(BotaoInfo("tipo_filtro"))
        linha.addWidget(self.spn_ordem)
        linha.addWidget(BotaoInfo("ordem"))
        col.addLayout(linha)

        self.sld_f1 = SliderRotulado("Cruzamento graves | médios", 40, 1000, p.f1_hz, "Hz", log=True,
                                     info="cruzamentos")
        self.sld_f2 = SliderRotulado("Cruzamento médios | agudos", 1000, 12000, p.f2_hz, "Hz", log=True,
                                     info="cruzamentos")
        self.sld_f1.valorMudou.connect(lambda v: self._mudar(f1_hz=v))
        self.sld_f2.valorMudou.connect(lambda v: self._mudar(f2_hz=v))
        col.addWidget(self.sld_f1)
        col.addWidget(self.sld_f2)

        self.sld_ganhos = {}
        for chave, nome in (("graves", "🔴 Ganho GRAVES"), ("medios", "🟢 Ganho MÉDIOS"), ("agudos", "🟣 Ganho AGUDOS")):
            s = SliderRotulado(nome, -24, 12, 0, "dB", casas=1, info=chave)
            s.valorMudou.connect(lambda v, c=chave: self._mudar(**{f"ganho_{c}_db": v}))
            self.sld_ganhos[chave] = s
            col.addWidget(s)
        return g

    def _grupo_seletivo(self) -> QGroupBox:
        g = QGroupBox("3. Filtragem seletiva")
        col = QVBoxLayout(g)
        p = ParametrosEQ()

        self.chk_notch = QCheckBox("Filtro notch (elimina uma frequência)")
        self.chk_notch.toggled.connect(lambda v: self._mudar(notch_ativo=v))
        self.sld_notch_f = SliderRotulado("Frequência central f0", 20, 10000, p.notch_f0_hz, "Hz", log=True,
                                          info="notch_f0")
        self.sld_notch_q = SliderRotulado("Fator de qualidade Q", 1, 100, p.notch_q, "", log=True, casas=1,
                                          info="notch_q")
        self.sld_notch_f.valorMudou.connect(lambda v: self._mudar(notch_f0_hz=v))
        self.sld_notch_q.valorMudou.connect(lambda v: self._mudar(notch_q=v))
        for w in (_com_info(self.chk_notch, "notch"), self.sld_notch_f, self.sld_notch_q):
            col.addWidget(w)

        self.chk_pb = QCheckBox("Passa-baixas (Butterworth 4ª ordem)")
        self.chk_pb.toggled.connect(lambda v: self._mudar(pb_ativo=v))
        self.sld_pb = SliderRotulado("Frequência de corte", 200, 20000, p.pb_corte_hz, "Hz", log=True,
                                     info="pb_corte")
        self.sld_pb.valorMudou.connect(lambda v: self._mudar(pb_corte_hz=v))
        col.addWidget(_com_info(self.chk_pb, "passa_baixas"))
        col.addWidget(self.sld_pb)
        return g

    def _grupo_saida(self) -> QGroupBox:
        g = QGroupBox("4. Saída")
        col = QVBoxLayout(g)
        self.sld_saida = SliderRotulado("Volume de saída", -24, 12, 0, "dB", casas=1, info="volume")
        self.sld_saida.valorMudou.connect(lambda v: self._mudar(ganho_saida_db=v))
        col.addWidget(self.sld_saida)

        self.chk_bypass = QCheckBox("Bypass — ouvir o ORIGINAL  (tecla B)")
        self.chk_bypass.toggled.connect(lambda v: self._mudar(bypass=v))
        col.addWidget(_com_info(self.chk_bypass, "bypass"))

        grade = QGridLayout()
        self.bar_entrada, self.bar_saida = QProgressBar(), QProgressBar()
        for i, (nome, bar) in enumerate((("Entrada", self.bar_entrada), ("Saída", self.bar_saida))):
            bar.setRange(-60, 0)
            bar.setValue(-60)
            bar.setFormat("%v dBFS")
            grade.addWidget(QLabel(nome), i, 0)
            grade.addWidget(bar, i, 1)
        grade.addWidget(BotaoInfo("medidores"), 0, 2)
        col.addLayout(grade)

        btn = QPushButton("Restaurar padrões")
        btn.clicked.connect(self._restaurar)
        col.addWidget(btn)
        return g

    # ============================================================ gráficos

    def _painel_grafico(self, titulo: str, chave_info: str) -> tuple[QWidget, pg.PlotItem]:
        """Gráfico com cabeçalho próprio: título + ícone ⓘ."""
        painel = QWidget()
        painel.setStyleSheet("background: black;")
        col = QVBoxLayout(painel)
        col.setContentsMargins(4, 4, 4, 0)
        col.setSpacing(0)
        cabecalho = QHBoxLayout()
        rotulo = QLabel(titulo)
        rotulo.setStyleSheet("color: #ddd; font-size: 13px;")
        cabecalho.addStretch()
        cabecalho.addWidget(rotulo)
        cabecalho.addSpacing(6)
        cabecalho.addWidget(BotaoInfo(chave_info))
        cabecalho.addStretch()
        col.addLayout(cabecalho)
        widget = pg.PlotWidget()
        col.addWidget(widget, stretch=1)
        return painel, widget.getPlotItem()

    def _montar_graficos(self) -> QWidget:
        area = QWidget()
        grade = QGridLayout(area)
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setSpacing(2)

        # --- Osciloscópio
        painel, self.pl_osc = self._painel_grafico("Osciloscópio — forma de onda no tempo", "osciloscopio")
        grade.addWidget(painel, 0, 0)
        self.pl_osc.setLabel("bottom", "tempo", units="ms")
        self.pl_osc.setLabel("left", "amplitude")
        self.pl_osc.setYRange(-1, 1)
        self.pl_osc.showGrid(x=True, y=True, alpha=0.3)
        self.pl_osc.addLegend(offset=(10, 10))
        self.cv_osc_in = self.pl_osc.plot(pen=pg.mkPen(COR_ENTRADA, width=1), name="entrada")
        self.cv_osc_out = self.pl_osc.plot(pen=pg.mkPen(COR_SAIDA, width=2), name="saída")

        # --- Espectro (FFT)
        painel, self.pl_fft = self._painel_grafico("Espectro de magnitude — FFT (janela de Hann)", "fft")
        grade.addWidget(painel, 0, 1)
        self.pl_fft.setLogMode(x=True)
        self.pl_fft.setLabel("bottom", "frequência (Hz)")
        self.pl_fft.setLabel("left", "magnitude", units="dBFS")
        self.pl_fft.setYRange(-110, 0)
        self.pl_fft.showGrid(x=True, y=True, alpha=0.3)
        self.pl_fft.addLegend(offset=(-10, 10))
        self.cv_fft_in = self.pl_fft.plot(pen=pg.mkPen(COR_ENTRADA, width=1), name="entrada")
        self.cv_fft_out = self.pl_fft.plot(pen=pg.mkPen(COR_SAIDA, width=2), name="saída")

        # --- Espectrograma
        painel, self.pl_espec = self._painel_grafico("Espectrograma da saída (STFT)", "espectrograma")
        grade.addWidget(painel, 1, 0)
        self.pl_espec.setLabel("bottom", "tempo", units="s")
        self.pl_espec.setLabel("left", "frequência (Hz)")
        self.img_espec = pg.ImageItem()
        self.img_espec.setColorMap(pg.colormap.get("inferno"))
        self.pl_espec.addItem(self.img_espec)
        barra = pg.ColorBarItem(values=(-100, 0), colorMap=pg.colormap.get("inferno"), label="dBFS",
                                interactive=False, width=12)
        barra.setImageItem(self.img_espec, insert_in=self.pl_espec)

        # --- Resposta em frequência teórica
        painel, self.pl_resp = self._painel_grafico("Resposta dos filtros |H(f)| — teórica", "resposta")
        grade.addWidget(painel, 1, 1)
        self.pl_resp.setLogMode(x=True)
        self.pl_resp.setLabel("bottom", "frequência (Hz)")
        self.pl_resp.setLabel("left", "ganho", units="dB")
        self.pl_resp.setYRange(-50, 15)
        self.pl_resp.showGrid(x=True, y=True, alpha=0.3)
        self.pl_resp.addLegend(offset=(-10, -10))
        self.cv_bandas = {
            k: self.pl_resp.plot(pen=pg.mkPen(c, width=1.5, style=Qt.DashLine), name=k.replace("medios", "médios"))
            for k, c in COR_BANDAS.items()
        }
        self.cv_total = self.pl_resp.plot(pen=pg.mkPen((255, 255, 255), width=3), name="total")

        # Linhas verticais com as frequências escolhidas (mesmas no FFT e na resposta).
        self.marcadores = []
        for chave, cor in (("f1", (255, 200, 0)), ("f2", (255, 200, 0)), ("notch", (255, 60, 60)), ("pb", (0, 255, 150))):
            for plot in (self.pl_fft, self.pl_resp):
                linha = pg.InfiniteLine(angle=90, pen=pg.mkPen(cor, width=1, style=Qt.DotLine))
                plot.addItem(linha)
                self.marcadores.append((chave, linha))
        return area

    def _preparar_analisadores(self, fs: float) -> None:
        """(Re)cria FFT/espectrograma quando a taxa de amostragem muda."""
        self._fs_graficos = fs
        self.analisador_in = AnalisadorEspectral(N_FFT, fs)
        self.analisador_out = AnalisadorEspectral(N_FFT, fs)
        self.analisador_espec = AnalisadorEspectral(2048, fs, suavizacao=0)

        f_max = fs / 2
        self.pl_fft.setXRange(np.log10(F_MIN), np.log10(f_max), padding=0)
        self.pl_resp.setXRange(np.log10(F_MIN), np.log10(f_max), padding=0)
        _rotulos_log(self.pl_fft.getAxis("bottom"), f_max)
        _rotulos_log(self.pl_resp.getAxis("bottom"), f_max)
        self.freqs_resp = np.geomspace(F_MIN, f_max * 0.999, 800)

        # Espectrograma com eixo de frequência logarítmico: reamostramos cada
        # coluna da FFT numa grade log-espaçada.
        self.freqs_espec = np.geomspace(F_MIN, f_max, LINHAS_ESPECTROGRAMA)
        self.matriz_espec = np.full((LINHAS_ESPECTROGRAMA, COLUNAS_ESPECTROGRAMA), -120.0)
        duracao = COLUNAS_ESPECTROGRAMA * INTERVALO_MS / 1000
        y0, y1 = np.log10(F_MIN), np.log10(f_max)
        self.img_espec.setImage(self.matriz_espec, levels=(-100, 0))
        self.img_espec.setRect(QRectF(-duracao, y0, duracao, y1 - y0))
        self.pl_espec.setYRange(y0, y1, padding=0)
        self.pl_espec.setXRange(-duracao, 0, padding=0)
        _rotulos_log(self.pl_espec.getAxis("left"), f_max)

    # ========================================================= ações / slots

    def _mudar(self, **mudancas) -> None:
        self.motor.atualizar(**mudancas)
        self._atualizar_resposta()
        self._atualizar_marcadores()

    def _ao_trocar_tipo(self) -> None:
        tipo = TipoFiltro(self.cmb_tipo.currentData())
        self.spn_ordem.setEnabled(tipo != TipoFiltro.FIR)
        self._mudar(tipo=tipo)

    def _ao_trocar_fonte(self) -> None:
        fonte = self.cmb_fonte.currentText()
        self.btn_abrir.setEnabled(fonte == FONTE_ARQ)
        self.cmb_entrada.setEnabled(fonte == FONTE_MIC)
        if self.motor.ativo:          # trocar de fonte durante a reprodução reinicia
            self._iniciar()

    def _abrir_arquivo(self) -> None:
        pasta = Path(__file__).resolve().parents[2] / "amostras"
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir áudio", str(pasta if pasta.is_dir() else Path.cwd()), "Áudio (*.wav *.mp3 *.flac *.ogg);;Todos (*.*)")
        if not caminho:
            return
        try:
            self._arquivo = carregar_arquivo(caminho)
        except Exception as erro:  # noqa: BLE001 - mostrar qualquer falha de leitura ao usuário
            QMessageBox.warning(self, "Erro ao abrir", f"Não foi possível ler o arquivo:\n{erro}")
            return
        dados, fs = self._arquivo
        self.lbl_arquivo.setText(f"{Path(caminho).name}<br>{dados.shape[0] / fs:.1f} s · {fs} Hz · "
                                 f"{'estéreo' if dados.shape[1] == 2 else 'mono'}")
        self._iniciar()

    def _alternar_play(self) -> None:
        if self.motor.ativo:
            self.motor.parar()
            self.btn_play.setText("▶  Iniciar  (Espaço)")
            self.lbl_status.setText("Parado.")
        else:
            self._iniciar()

    def _iniciar(self) -> None:
        fonte = self.cmb_fonte.currentText()
        saida = self.cmb_saida.currentData()
        try:
            if fonte == FONTE_MIC:
                self.motor.iniciar_microfone(self.cmb_entrada.currentData(), saida)
            elif fonte == FONTE_ARQ:
                if self._arquivo is None:
                    self._abrir_arquivo()
                    return
                self.motor.iniciar_reproducao(*self._arquivo, disp_saida=saida)
            else:
                nome = fonte.split("Teste: ", 1)[1]
                fs = 44100
                self.motor.iniciar_reproducao(sinais_teste.SINAIS[nome](fs), fs, disp_saida=saida)
        except Exception as erro:  # noqa: BLE001 - erros do PortAudio variam por dispositivo
            self.motor.parar()
            QMessageBox.critical(self, "Erro de áudio",
                                 f"Não foi possível abrir o dispositivo de áudio:\n{erro}\n\n"
                                 "Dica: escolha outro dispositivo de entrada/saída.")
            return
        self.btn_play.setText("■  Parar  (Espaço)")
        if self.motor.fs != self._fs_graficos:
            self._preparar_analisadores(self.motor.fs)
        self._atualizar_resposta()
        self._atualizar_marcadores()

    def _restaurar(self) -> None:
        p = ParametrosEQ()
        self.cmb_tipo.setCurrentIndex(0)
        self.spn_ordem.setValue(p.ordem)
        self.sld_f1.definir(p.f1_hz)
        self.sld_f2.definir(p.f2_hz)
        for s in self.sld_ganhos.values():
            s.definir(0)
        self.chk_notch.setChecked(False)
        self.sld_notch_f.definir(p.notch_f0_hz)
        self.sld_notch_q.definir(p.notch_q)
        self.chk_pb.setChecked(False)
        self.sld_pb.definir(p.pb_corte_hz)
        self.sld_saida.definir(0)
        self.chk_bypass.setChecked(False)

    # ======================================================== atualizações

    def _atualizar_resposta(self) -> None:
        if not hasattr(self, "freqs_resp"):
            return
        # Inclui f0 do notch na grade para o "entalhe" aparecer com a profundidade real.
        freqs = np.sort(np.append(self.freqs_resp, self.motor.params.notch_f0_hz))
        resp = self.motor.processador.resposta_em_frequencia(freqs)
        for k, curva in self.cv_bandas.items():
            curva.setData(freqs, filtros.db(resp[k]))
        self.cv_total.setData(freqs, filtros.db(resp["total"]))

    def _atualizar_marcadores(self) -> None:
        p = self.motor.params
        valores = {"f1": (p.f1_hz, True), "f2": (p.f2_hz, True),
                   "notch": (p.notch_f0_hz, p.notch_ativo), "pb": (p.pb_corte_hz, p.pb_ativo)}
        for chave, linha in self.marcadores:
            f, visivel = valores[chave]
            linha.setValue(np.log10(f))
            linha.setVisible(visivel)

    def _atualizar_graficos(self) -> None:
        fs = self.motor.fs
        buf_in, buf_out = self.motor.buf_entrada, self.motor.buf_saida
        total = buf_out.total_escrito
        if total == self._ultimo_total:      # nada novo chegou (parado)
            return
        self._ultimo_total = total

        # Osciloscópio: ~30 ms, sincronizado pela passagem por zero da saída.
        janela = int(0.03 * fs)
        x_in = buf_in.ler_ultimas(janela * 3)
        x_out = buf_out.ler_ultimas(janela * 3)
        i0 = indice_gatilho(x_out, janela)
        t_ms = np.arange(janela) / fs * 1000
        self.cv_osc_in.setData(t_ms, x_in[i0:i0 + janela])
        self.cv_osc_out.setData(t_ms, x_out[i0:i0 + janela])

        # Espectro FFT (descarta a raia DC para o eixo log).
        f = self.analisador_out.freqs[1:]
        self.cv_fft_in.setData(f, self.analisador_in.espectro_db(buf_in.ler_ultimas(N_FFT))[1:])
        self.cv_fft_out.setData(f, self.analisador_out.espectro_db(buf_out.ler_ultimas(N_FFT))[1:])

        # Espectrograma: rola uma coluna para a esquerda e insere a mais nova.
        coluna = self.analisador_espec.espectro_db(buf_out.ler_ultimas(2048))
        self.matriz_espec = np.roll(self.matriz_espec, -1, axis=1)
        self.matriz_espec[:, -1] = np.interp(self.freqs_espec, self.analisador_espec.freqs, coluna)
        self.img_espec.setImage(self.matriz_espec, autoLevels=False)

        # Medidores de pico e status.
        proc = self.motor.processador
        for bar, pico in ((self.bar_entrada, proc.pico_entrada), (self.bar_saida, proc.pico_saida)):
            bar.setValue(int(max(-60, 20 * np.log10(pico + 1e-9))))
        pos, dur = self.motor.progresso
        tempo = f" · {pos:5.1f}/{dur:.1f} s" if dur else ""
        aviso = "<br>⚠ Use FONES para evitar microfonia!" if self.motor.modo == "microfone" else ""
        saturou = " · <span style='color:#f55'>SATURANDO</span>" if proc.pico_saida >= 0.999 else ""
        self.lbl_status.setText(
            f"Tocando · {fs / 1000:.1f} kHz · bloco {self.motor.bloco} · "
            f"latência ≈ {self.motor.latencia_ms:.0f} ms{tempo}{saturou}"
            f"<br>Falhas de buffer: {self.motor.falhas}{aviso}")

    def closeEvent(self, evento) -> None:  # noqa: N802 - nome exigido pelo Qt
        self._timer.stop()
        self.motor.parar()
        super().closeEvent(evento)

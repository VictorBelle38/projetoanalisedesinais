"""
Textos explicativos dos ícones ⓘ da interface.

Cada entrada tem: título, "o que é", "o que faz com o áudio" e um
"experimente" — um mini-roteiro para ver/ouvir o conceito na prática.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QToolButton, QWidget


@dataclass(frozen=True)
class Ajuda:
    titulo: str
    o_que_e: str
    efeito: str
    experimente: str


AJUDAS: dict[str, Ajuda] = {
    # ------------------------------------------------------------- fonte
    "fonte": Ajuda(
        "Fonte de áudio",
        "De onde vem o sinal que será processado. O áudio digital é uma sequência de "
        "números (amostras): 44.100 medições por segundo da pressão do som (fs = 44,1 kHz).",
        "Nenhum — só escolhe a entrada. <b>Microfone</b>: capta e devolve o som quase na hora, "
        "em blocos de 512 amostras (~11 ms). <b>Arquivo</b>: toca um .wav/.mp3 em loop. "
        "<b>Sinais de teste</b>: sons gerados por fórmulas, cada um feito para demonstrar um filtro.",
        "Ruído branco para ver o formato dos filtros; Acorde + apito para o notch; "
        "Varredura para ver o espectrograma; Microfone (com fones!) para o tempo real.",
    ),
    "dispositivos": Ajuda(
        "Dispositivos de entrada e saída",
        "Qual microfone e qual fone/caixa de som o programa usa.",
        "Nenhum. Se o som não sair, escolha aqui o dispositivo certo e reinicie (Espaço).",
        "No modo Microfone use <b>fones de ouvido</b>: com caixas de som o microfone capta "
        "a própria saída e o som realimenta (microfonia / efeito Larsen).",
    ),
    "status": Ajuda(
        "Status: latência e falhas de buffer",
        "<b>Latência</b> é o atraso entre o som entrar e sair. <b>Falhas de buffer</b> contam "
        "as vezes em que o computador não processou um bloco a tempo.",
        "Latência alta = eco perceptível ao falar no microfone. Falhas = estalos/picotes no som.",
        "Rode <code>executar.bat --bloco 256</code> para menos latência, ou "
        "<code>--bloco 1024</code> se o som picotar.",
    ),
    # ------------------------------------------------------- banco
    "tipo_filtro": Ajuda(
        "Tipo de filtro",
        "A \"família\" matemática dos filtros que separam as 3 bandas.<br>"
        "• <b>Butterworth (IIR)</b>: banda passante perfeitamente lisa.<br>"
        "• <b>Chebyshev I (IIR)</b>: corte mais abrupto, com ondulação de 1 dB.<br>"
        "• <b>FIR</b>: fase linear e bandas que somam exatamente o sinal original.",
        "Com todos os ganhos em 0 dB: Butterworth dá +3 dB nos cruzamentos, Chebyshev ondula "
        "±1 dB, FIR fica perfeitamente plano (0,0 dB). Com ganhos diferentes, o tipo muda "
        "o quão \"limpa\" é a separação entre graves, médios e agudos.",
        "Clique em Restaurar padrões e troque o tipo olhando a curva branca do gráfico "
        "\"Resposta dos filtros\".",
    ),
    "ordem": Ajuda(
        "Ordem do filtro",
        "Quantos polos o filtro IIR tem. Cada +1 de ordem deixa a queda após o corte "
        "20 dB por década mais íngreme. (No FIR a ordem é fixa: 511 coeficientes.)",
        "Ordem baixa: as bandas se misturam bastante. Ordem alta: a separação é mais nítida, "
        "mas o filtro \"toca\" mais (ressoa) perto do corte.",
        "Coloque Graves em −24 dB e varie a ordem de 1 a 8: veja a curva laranja ficar "
        "cada vez mais vertical.",
    ),
    "cruzamentos": Ajuda(
        "Frequências de cruzamento (f1 e f2)",
        "Os pontos onde uma banda termina e a outra começa. Graves: até f1. Médios: de f1 a f2. "
        "Agudos: acima de f2. O slider é logarítmico porque o ouvido percebe frequência assim "
        "(100→200 Hz soa como o mesmo salto que 1000→2000 Hz).",
        "Mudam QUAIS frequências cada slider de ganho controla.",
        "Com Graves em +10 dB, arraste f1 de 40 Hz até 1 kHz: o reforço passa a pegar "
        "também a voz e os instrumentos.",
    ),
    "graves": Ajuda(
        "Ganho dos GRAVES (0 até f1)",
        "Volume da banda de baixas frequências: bumbo, contrabaixo, o \"corpo\" da voz masculina. "
        "Filtro usado: passa-baixas.",
        "+ dB: som mais encorpado, \"bass boost\". − dB: som mais fino, \"de rádio\". "
        "Lembrete: +6 dB ≈ dobra a amplitude; −6 dB ≈ reduz pela metade.",
        "Toque uma música e alterne +10 dB / −20 dB, comparando com a tecla B.",
    ),
    "medios": Ajuda(
        "Ganho dos MÉDIOS (f1 até f2)",
        "Volume da faixa central, onde fica a maior parte da voz e dos instrumentos. "
        "Filtro usado: passa-faixa.",
        "+ dB: voz mais à frente, som \"nasal\". − dB: som \"escavado\", voz distante.",
        "Com uma música, coloque Médios em −24 dB: sobram praticamente só o grave e o brilho.",
    ),
    "agudos": Ajuda(
        "Ganho dos AGUDOS (f2 até 22 kHz)",
        "Volume das altas frequências: pratos, chiado, o \"s\" da fala. Filtro usado: passa-altas.",
        "+ dB: som mais brilhante (e ruído mais evidente). − dB: som mais escuro e abafado.",
        "Com Ruído branco, coloque Agudos em −24 dB: o chiado vira um \"shhh\" grave.",
    ),
    # --------------------------------------------------- seletivos
    "notch": Ajuda(
        "Filtro notch (rejeita-faixa estreito)",
        "Filtro que elimina UMA frequência específica e preserva o resto. Matematicamente, "
        "coloca dois zeros sobre o círculo unitário em f0 (ganho zero ali) e dois polos logo "
        "atrás, que devolvem o volume às frequências vizinhas.",
        "Remove apitos, microfonia ou o zumbido de 60 Hz da rede elétrica sem afetar "
        "o restante do som.",
        "Fonte \"Acorde + apito de 1 kHz\" → ligue o notch em 1,00 kHz: o apito some, a música fica.",
    ),
    "notch_f0": Ajuda(
        "Frequência central f0 do notch",
        "A frequência exata que será eliminada. Ela é marcada por uma linha vermelha pontilhada "
        "nos gráficos de frequência.",
        "Tudo muito perto de f0 é silenciado; frequências distantes passam intactas.",
        "Com o apito tocando, arraste f0 devagar perto de 1 kHz e ouça o apito sumir só no ponto certo.",
    ),
    "notch_q": Ajuda(
        "Fator de qualidade Q",
        "Q = f0 ÷ largura da faixa removida. Q = 30 em 1 kHz remove uma faixa de ~33 Hz; "
        "Q = 2 remove ~500 Hz.",
        "Q alto: corte cirúrgico, quase inaudível na música. Q baixo: corte largo que "
        "\"come\" parte do som útil.",
        "Com o notch ligado, baixe Q até 2 e veja o \"buraco\" alargar na curva branca.",
    ),
    "passa_baixas": Ajuda(
        "Filtro passa-baixas",
        "Deixa passar só as frequências ABAIXO do corte. Butterworth de 4ª ordem: −3 dB no "
        "corte e queda de 80 dB por década depois.",
        "Quanto menor o corte, mais \"abafado\" o som — como ouvir uma festa do outro lado da parede.",
        "Ligue e arraste o corte de 20 kHz até 300 Hz: no espectrograma a parte de cima escurece.",
    ),
    "pb_corte": Ajuda(
        "Frequência de corte",
        "Ponto em que o passa-baixas já reduziu o sinal em 3 dB (metade da potência). "
        "Marcado por uma linha verde pontilhada nos gráficos.",
        "Tudo acima dessa frequência vai sendo atenuado cada vez mais.",
        "Use 3 kHz: a voz continua compreensível, mas soa como um telefone antigo.",
    ),
    # --------------------------------------------------------- saída
    "volume": Ajuda(
        "Volume de saída",
        "Ganho geral aplicado no final de toda a cadeia de processamento.",
        "Aumenta ou reduz tudo por igual. Útil para compensar quando as bandas foram muito "
        "reforçadas e o som começou a saturar.",
        "Se aparecer \"SATURANDO\" no status, baixe o volume até o aviso sumir.",
    ),
    "bypass": Ajuda(
        "Bypass (comparação A/B)",
        "Desliga todo o processamento e envia o sinal original para a saída.",
        "Permite comparar, instantaneamente, o som original com o processado.",
        "Aperte a tecla <b>B</b> várias vezes enquanto uma música toca.",
    ),
    "medidores": Ajuda(
        "Medidores de pico (dBFS)",
        "Mostram o maior valor de amostra do último bloco, em dBFS. 0 dBFS é o máximo que o "
        "sistema digital representa; −6 dBFS é metade disso.",
        "Se a saída chega a 0 dBFS, a onda é \"cortada\" (clipping) e o som distorce.",
        "Coloque todos os ganhos em +12 dB e veja o medidor de saída encostar no máximo.",
    ),
    # -------------------------------------------------------- gráficos
    "osciloscopio": Ajuda(
        "Osciloscópio — domínio do TEMPO",
        "Mostra ~30 ms da forma de onda: amplitude (vertical) ao longo do tempo (horizontal). "
        "Cinza = entrada, azul = saída. O desenho começa sempre quando a onda cruza o zero "
        "subindo (\"trigger\"), por isso ela fica parada na tela.",
        "Permite ver o efeito dos filtros na própria onda: tirando agudos, a curva azul fica "
        "mais lisa; tirando graves, as ondulações lentas somem.",
        "Fonte Acorde + apito, ligue o notch: a \"tremidinha\" rápida de 1 kHz some da onda azul.",
    ),
    "fft": Ajuda(
        "Espectro FFT — domínio da FREQUÊNCIA",
        "A Transformada Rápida de Fourier decompõe as últimas 4096 amostras em senoides e "
        "mostra quanto existe de cada frequência (eixo horizontal, em escala logarítmica). "
        "Antes da FFT o trecho é multiplicado por uma janela de Hann, que evita picos falsos "
        "(vazamento espectral).",
        "Mostra o resultado de Y(f) = H(f)·X(f): a curva azul (saída) é a cinza (entrada) "
        "moldada pelos filtros. Linhas pontilhadas: amarelas = f1/f2, vermelha = notch, "
        "verde = passa-baixas.",
        "Com Ruído branco, mexa nos ganhos: a curva azul copia o formato da curva branca "
        "do gráfico \"Resposta dos filtros\".",
    ),
    "espectrograma": Ajuda(
        "Espectrograma — TEMPO × FREQUÊNCIA",
        "Várias FFTs seguidas, empilhadas lado a lado (STFT). Horizontal = tempo (últimos ~10 s), "
        "vertical = frequência, cor = intensidade (amarelo = forte, preto = silêncio).",
        "Mostra como o conteúdo do som da SAÍDA muda ao longo do tempo.",
        "Varredura: aparece uma linha subindo. Apito de 1 kHz: uma linha horizontal que "
        "desaparece quando o notch é ligado.",
    ),
    "resposta": Ajuda(
        "Resposta dos filtros |H(f)| — a TEORIA",
        "A curva calculada a partir dos coeficientes dos filtros: quanto cada frequência é "
        "amplificada (+dB) ou atenuada (−dB). Tracejados = cada banda com seu ganho; "
        "linha branca = sistema completo (bandas + notch + passa-baixas + volume).",
        "É exatamente o que o sistema faz com cada frequência do áudio. 0 dB = inalterado.",
        "Compare esta curva com o espectro FFT da saída tocando Ruído branco: teoria e "
        "prática coincidem.",
    ),
}


def mostrar_ajuda(pai: QWidget, chave: str) -> None:
    a = AJUDAS[chave]
    caixa = QMessageBox(pai)
    caixa.setWindowTitle(f"ⓘ  {a.titulo}")
    caixa.setTextFormat(Qt.RichText)
    caixa.setText(
        f"<h3>{a.titulo}</h3>"
        f"<p><b>O que é:</b><br>{a.o_que_e}</p>"
        f"<p><b>O que faz com o áudio:</b><br>{a.efeito}</p>"
        f"<p><b>🔎 Experimente:</b><br>{a.experimente}</p>"
    )
    caixa.setStandardButtons(QMessageBox.Ok)
    caixa.exec()


class BotaoInfo(QToolButton):
    """Ícone ⓘ: passe o mouse para um resumo, clique para a explicação completa."""

    ESTILO = (
        "QToolButton { border: 1px solid #2d7be5; border-radius: 9px; color: #2d7be5;"
        " font: bold italic 11px 'Georgia'; min-width: 16px; max-width: 16px;"
        " min-height: 16px; max-height: 16px; padding: 0; background: transparent; }"
        "QToolButton:hover { background: #2d7be5; color: white; }"
    )

    def __init__(self, chave: str, pai: QWidget | None = None):
        super().__init__(pai)
        self.chave = chave
        self.setText("i")
        self.setStyleSheet(self.ESTILO)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"<b>{AJUDAS[chave].titulo}</b><br>{AJUDAS[chave].efeito}"
                        "<br><i>Clique para saber mais.</i>")
        self.clicked.connect(lambda: mostrar_ajuda(self.window(), self.chave))

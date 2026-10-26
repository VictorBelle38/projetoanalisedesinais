"""
Ponto de entrada.

    python main.py                 # abre a interface
    python main.py --dispositivos  # lista as placas de som disponíveis
    python main.py --bloco 256     # blocos menores = menos latência (mais CPU)
"""

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Equalizador paramétrico em tempo real")
    parser.add_argument("--bloco", type=int, default=512, help="amostras por bloco de áudio (padrão 512)")
    parser.add_argument("--fs", type=int, default=44100, help="taxa de amostragem do microfone (padrão 44100)")
    parser.add_argument("--dispositivos", action="store_true", help="lista dispositivos de áudio e sai")
    args = parser.parse_args()

    if args.dispositivos:
        import sounddevice as sd
        print(sd.query_devices())
        return 0

    from PySide6.QtWidgets import QApplication

    from equalizador.interface.janela import JanelaPrincipal

    app = QApplication(sys.argv)
    janela = JanelaPrincipal(bloco=args.bloco, fs_microfone=args.fs)
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

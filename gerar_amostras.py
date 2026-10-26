"""
Gera arquivos .wav de teste na pasta `amostras/` para demonstrar a opção
"Arquivo de áudio" da interface sem precisar baixar nada.

    python gerar_amostras.py
"""

from pathlib import Path

import soundfile as sf

from equalizador import sinais_teste

FS = 44100
NOMES = {
    "Ruído branco": "ruido_branco.wav",
    "Varredura 20 Hz → 20 kHz": "varredura_20Hz_20kHz.wav",
    "Acorde + apito de 1 kHz": "acorde_com_apito_1kHz.wav",
    "Ruído + zumbido 60 Hz": "zumbido_60Hz.wav",
}


def main() -> None:
    pasta = Path(__file__).parent / "amostras"
    pasta.mkdir(exist_ok=True)
    for nome, gerador in sinais_teste.SINAIS.items():
        destino = pasta / NOMES[nome]
        sf.write(destino, gerador(FS), FS, subtype="PCM_16")
        print(f"gerado: {destino}")


if __name__ == "__main__":
    main()

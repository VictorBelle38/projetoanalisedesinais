"""
Testes automáticos do núcleo de DSP.  Rode com:  python -m pytest
Cada teste confere uma propriedade teórica dos filtros.
"""

import numpy as np
import pytest
from scipy import signal

from equalizador import filtros
from equalizador.analise import AnalisadorEspectral
from equalizador.buffer_circular import BufferCircular
from equalizador.filtros import TipoFiltro
from equalizador.processador import ParametrosEQ, ProcessadorEQ

FS = 44100


def seno(f, dur=1.0, fs=FS):
    t = np.arange(int(fs * dur)) / fs
    return np.sin(2 * np.pi * f * t)


def ganho_db_medido(proc, f):
    """Passa um seno pelo processador e mede o ganho em regime permanente."""
    x = seno(f, 1.0) * 0.5
    y = proc.processar(x)
    meio = slice(len(x) // 2, None)  # descarta o transitório inicial
    return 20 * np.log10(np.std(y[meio]) / np.std(x[meio]))


def processar_em_blocos(proc, x, bloco):
    return np.concatenate([proc.processar(x[i:i + bloco]) for i in range(0, len(x), bloco)])


# ----------------------------------------------------------- filtros isolados

@pytest.mark.parametrize("tipo", [TipoFiltro.BUTTERWORTH, TipoFiltro.CHEBYSHEV])
def test_passa_baixas_iir_atenua_acima_do_corte(tipo):
    sos = filtros.projetar_iir(tipo, 4, 1000, "lowpass", FS)
    h = filtros.resposta_sos(sos, np.array([100.0, 10000.0]), FS)
    assert filtros.db(h[0]) > -1.5          # banda passante ~0 dB
    assert filtros.db(h[1]) < -60           # 4ª ordem: ~80 dB/década


def test_butterworth_tem_menos_3db_no_corte():
    sos = filtros.projetar_iir(TipoFiltro.BUTTERWORTH, 4, 1000, "lowpass", FS)
    h = filtros.resposta_sos(sos, np.array([1000.0]), FS)
    assert filtros.db(h[0]) == pytest.approx(-3.01, abs=0.05)


def test_notch_anula_somente_a_frequencia_central():
    sos = filtros.projetar_notch(60, 30, FS)
    h = filtros.resposta_sos(sos, np.array([60.0, 30.0, 120.0, 1000.0]), FS)
    assert filtros.db(h[0]) < -60
    assert all(filtros.db(h[1:]) > -1)


def test_banco_fir_reconstrucao_perfeita():
    """h_graves + h_medios + h_agudos = delta (atrasado)."""
    banco = filtros.projetar_banco(TipoFiltro.FIR, 4, 250, 4000, FS, 511)
    soma = banco.graves + banco.medios + banco.agudos
    esperado = np.zeros(511)
    esperado[255] = 1.0
    np.testing.assert_allclose(soma, esperado, atol=1e-12)


# ------------------------------------------------------------ processador

def test_processamento_em_blocos_igual_ao_sinal_inteiro():
    """O estado entre blocos garante continuidade: blocos == sinal inteiro."""
    rng = np.random.default_rng(0)
    x = rng.standard_normal(10000) * 0.1
    for tipo in TipoFiltro:
        p = ParametrosEQ(tipo=tipo, ganho_graves_db=6, ganho_agudos_db=-6, notch_ativo=True, pb_ativo=True)
        inteiro = ProcessadorEQ(FS, 1, p).processar(x)
        em_blocos = processar_em_blocos(ProcessadorEQ(FS, 1, p), x, 512)
        np.testing.assert_allclose(em_blocos, inteiro, atol=1e-9, err_msg=tipo.value)


def test_ganho_de_banda_aplica_no_lugar_certo():
    p = ParametrosEQ(tipo=TipoFiltro.FIR, ganho_graves_db=-12)
    proc = ProcessadorEQ(FS, 1, p)
    assert ganho_db_medido(proc, 60) == pytest.approx(-12, abs=0.5)
    proc = ProcessadorEQ(FS, 1, p)
    assert ganho_db_medido(proc, 1000) == pytest.approx(0, abs=0.5)


def test_notch_no_processador_remove_apito():
    proc = ProcessadorEQ(FS, 1, ParametrosEQ(notch_ativo=True, notch_f0_hz=1000, notch_q=30,
                                              tipo=TipoFiltro.FIR))
    assert ganho_db_medido(proc, 1000) < -40


def test_bypass_devolve_entrada():
    x = seno(440, 0.1) * 0.5
    proc = ProcessadorEQ(FS, 1, ParametrosEQ(bypass=True, ganho_graves_db=10))
    np.testing.assert_allclose(proc.processar(x), x)


def test_estereo_processa_canais_independentes():
    x = np.stack([seno(100, 0.5), np.zeros(int(FS * 0.5))], axis=1) * 0.5
    y = ProcessadorEQ(FS, 2).processar(x)
    assert y.shape == x.shape
    assert np.max(np.abs(y[:, 1])) == 0.0


def test_resposta_em_frequencia_total_reflete_ganhos():
    proc = ProcessadorEQ(FS, 1, ParametrosEQ(tipo=TipoFiltro.FIR, ganho_agudos_db=6))
    r = proc.resposta_em_frequencia(np.array([100.0, 12000.0]))
    assert filtros.db(r["total"][0]) == pytest.approx(0, abs=0.3)
    assert filtros.db(r["total"][1]) == pytest.approx(6, abs=0.3)


# ------------------------------------------------------- buffer e análise

def test_buffer_circular_mantem_as_ultimas_amostras():
    buf = BufferCircular(8)
    buf.escrever(np.arange(5))
    buf.escrever(np.arange(5, 11))       # dá a volta
    np.testing.assert_array_equal(buf.ler_ultimas(8), np.arange(3, 11))
    np.testing.assert_array_equal(buf.ler_ultimas(3), [8, 9, 10])


def test_fft_seno_aparece_em_0_dbfs_na_frequencia_certa():
    an = AnalisadorEspectral(4096, FS, suavizacao=0)
    f = an.freqs[200]                     # frequência exatamente numa raia
    espectro = an.espectro_db(seno(f, 0.2))
    assert an.freqs[np.argmax(espectro)] == pytest.approx(f)
    assert espectro.max() == pytest.approx(0, abs=0.1)

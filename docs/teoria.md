# Fundamentação teórica

Este documento explica os conceitos de Processamento de Sinais usados no
projeto e aponta **onde cada um está no código**.

---

## 1. Sinal digital e amostragem

O microfone gera uma tensão contínua $x(t)$. A placa de som mede essa tensão
$f_s$ vezes por segundo (taxa de amostragem), gerando a sequência

$$x[n] = x(nT_s), \qquad T_s = 1/f_s$$

Usamos $f_s = 44{,}1\ \text{kHz}$ (qualidade de CD). Pelo **teorema de
Nyquist–Shannon**, só conseguimos representar frequências até

$$f_{\text{Nyquist}} = f_s / 2 = 22{,}05\ \text{kHz}$$

— por isso todos os gráficos de frequência terminam em ~22 kHz.

As amostras são `float32` na faixa ±1 (0 dBFS = amplitude máxima). Acima
disso há saturação (*clipping*) — o processador limita a saída em ±1
(`processador.py → processar`) e a interface mostra **SATURANDO**.

## 2. Processamento em blocos e buffer circular

A placa de som não entrega amostra por amostra: ela chama nossa função
(*callback*) a cada **bloco** de 512 amostras (≈ 11,6 ms). Temos esse tempo
para processar o bloco, senão ocorre uma falha de buffer (estalo).
O processamento leva **~0,3 ms (IIR) a ~0,6 ms (FIR)** por bloco.

```
microfone ─► [callback de áudio] ─► alto-falante
                    │
                    ▼  escreve
            buffer circular  ──► lido pela interface a cada 33 ms (30 FPS)
```

O **buffer circular** (`buffer_circular.py`) guarda sempre as últimas
65 536 amostras: ao chegar no fim do vetor, volta ao início sobrescrevendo
as mais antigas. Assim a thread de áudio (rápida) e a da interface (lenta)
trocam dados sem que uma espere a outra.

**Latência** = tempo entre o som entrar no microfone e sair no fone. Ela vem
principalmente dos buffers do sistema operacional (≈ 90–120 ms com o driver
MME do Windows). Blocos menores (`python main.py --bloco 256`) reduzem a
latência, mas aumentam o risco de falhas.

## 3. Filtros digitais: equação de diferenças

Todo filtro linear e invariante no tempo (LTI) é descrito por

$$y[n] = \sum_{k=0}^{M} b_k\,x[n-k] \;-\; \sum_{k=1}^{N} a_k\,y[n-k]$$

e pela função de transferência em $z$:

$$H(z) = \frac{B(z)}{A(z)} = \frac{b_0 + b_1 z^{-1} + \dots + b_M z^{-M}}{1 + a_1 z^{-1} + \dots + a_N z^{-N}}$$

A resposta em frequência é $H$ avaliada sobre o círculo unitário,
$z = e^{j2\pi f/f_s}$. É isso que o gráfico **"Resposta dos filtros |H(f)|"**
mostra (calculado por `scipy.signal.sosfreqz` / `freqz`).

| | FIR (*Finite Impulse Response*) | IIR (*Infinite Impulse Response*) |
|---|---|---|
| Realimentação | não ($a_k = 0$) | sim |
| Estabilidade | sempre estável | polos devem ficar dentro do círculo unitário |
| Fase | pode ser **linear** (sem distorção de fase) | não linear |
| Custo | muitos coeficientes (aqui, 511) | poucos (ordem 4 → ~8 coeficientes/banda) |
| Atraso | $(N-1)/2$ = 255 amostras ≈ 5,8 ms | pequeno, varia com a frequência |

### Por que "SOS"?

Filtros IIR de ordem alta escritos como um único polinômio $(b, a)$ sofrem
com erros de arredondamento e podem até ficar instáveis. O SciPy permite
fatorá-los em uma **cascata de seções de 2ª ordem** (*biquads*,
`output="sos"`), numericamente robusta. É o formato usado em todo o projeto.

### Estado entre blocos

Para filtrar bloco a bloco **sem descontinuidades**, o filtro precisa
lembrar o passado:

- IIR: o vetor de estado `zi` de cada biquad (`sosfilt(..., zi=zi)` devolve o
  estado final, usado no próximo bloco);
- FIR: as últimas $N-1$ amostras de entrada, concatenadas ao bloco seguinte.

O teste `test_processamento_em_blocos_igual_ao_sinal_inteiro` prova que
filtrar em blocos de 512 dá **exatamente** o mesmo resultado que filtrar o
sinal inteiro de uma vez.

## 4. Famílias de filtros IIR

**Butterworth** — "maximamente plano": sem ondulação na banda passante. No
corte a atenuação é sempre −3 dB (metade da potência). A inclinação após o
corte é de $20\cdot N$ dB por década ($N$ = ordem).

**Chebyshev tipo I** — aceita uma ondulação (*ripple*, aqui 1 dB) na banda
passante em troca de uma **transição mais íngreme** para a mesma ordem.
Na interface dá para ver a "ondinha" perto das frequências de cruzamento.

Projeto: `scipy.signal.butter` e `scipy.signal.cheby1` (`filtros.projetar_iir`).

## 5. Banco de filtros de 3 bandas (equalizador)

O sinal é dividido em três bandas que são filtradas **em paralelo**,
multiplicadas por um ganho cada e somadas:

```
          ┌─ passa-baixas  (0 … f1)   × g_graves ─┐
x[n] ─────┼─ passa-faixa   (f1 … f2)  × g_médios ─┼─ Σ ─► y[n]
          └─ passa-altas   (f2 … fs/2) × g_agudos ─┘
```

Ganho em decibéis: $g = 10^{\,\text{dB}/20}$ (+6 dB ≈ ×2, −6 dB ≈ ×½).

**Versão FIR — reconstrução perfeita.** Projetamos dois passa-baixas
$h_{f1}$ e $h_{f2}$ pelo método da janela (sinc × Hamming,
`scipy.signal.firwin`) e usamos **inversão espectral**:

$$h_{\text{graves}} = h_{f1}, \quad h_{\text{médios}} = h_{f2} - h_{f1}, \quad h_{\text{agudos}} = \delta - h_{f2}$$

Somando: $h_{\text{graves}} + h_{\text{médios}} + h_{\text{agudos}} = \delta$
(um impulso). Com todos os ganhos em 0 dB, a saída é **idêntica** à entrada
(apenas atrasada). Teste: `test_banco_fir_reconstrucao_perfeita`.

**Versão IIR — limitação.** As três bandas IIR têm fases diferentes; perto de
f1 e f2 elas não somam perfeitamente e aparece um pequeno "calombo" ou "vale"
na curva branca (total), mesmo com ganhos em 0 dB. É uma ótima comparação
para mostrar em sala: troque o tipo para FIR e a curva fica plana.

## 6. Filtro notch (rejeita-faixa estreito)

Remove **uma** frequência (ex.: apito, zumbido de 60 Hz da rede elétrica)
quase sem afetar o resto. Função de transferência de 2ª ordem:

$$H(z) = \frac{1 - 2\cos\omega_0\, z^{-1} + z^{-2}}{1 - 2r\cos\omega_0\, z^{-1} + r^2 z^{-2}}, \qquad \omega_0 = 2\pi f_0 / f_s$$

- os **zeros** ficam *sobre* o círculo unitário em $e^{\pm j\omega_0}$ →
  ganho exatamente zero em $f_0$;
- os **polos** ficam logo atrás, com raio $r < 1$ → "devolvem" o ganho às
  frequências vizinhas. Quanto mais $r \to 1$, mais estreito o entalhe.

O fator de qualidade $Q = f_0 / \Delta f_{-3\text{dB}}$ controla essa largura.
Projeto: `scipy.signal.iirnotch` (`filtros.projetar_notch`).

## 7. Passa-baixas ajustável

Butterworth de 4ª ordem com corte $f_c$ ajustável (−3 dB em $f_c$,
−80 dB/década depois). Efeito audível: o som fica "abafado", como se
viesse de trás de uma parede.

## 8. Análise espectral: FFT e espectrograma

**DFT/FFT.** A Transformada Discreta de Fourier de $N$ amostras

$$X[k] = \sum_{n=0}^{N-1} x[n]\, e^{-j 2\pi k n / N}, \qquad f_k = k\,\frac{f_s}{N}$$

decompõe o trecho em senoides. A FFT calcula isso em $O(N \log N)$. Usamos
$N = 4096$ → resolução $f_s/N \approx 10{,}8$ Hz (`analise.py`).

**Janelamento.** Cortar o sinal "a seco" cria descontinuidades nas bordas,
espalhando energia por todo o espectro (**vazamento espectral**).
Multiplicamos o trecho por uma **janela de Hann**, que vai suavemente a zero.
O fator $2/\sum w[n]$ corrige a amplitude para que um seno de amplitude 1
apareça em 0 dBFS (teste `test_fft_seno_aparece_em_0_dbfs_na_frequencia_certa`).

**Espectrograma (STFT).** FFTs sucessivas de trechos curtos (2048 amostras),
empilhadas lado a lado: eixo x = tempo, eixo y = frequência, cor = intensidade.
Mostra **como o espectro muda com o tempo** — uma varredura (*chirp*) aparece
como uma linha subindo; um apito constante, como uma linha horizontal que
some quando o notch é ligado.

## 9. Detalhes de tempo real

- **Rampa de ganho** (`processador._rampa`): mudar o ganho de uma vez gera um
  clique ("zipper noise"). O ganho é interpolado linearmente ao longo de um
  bloco (~11 ms) — inaudível.
- **Troca atômica de coeficientes**: os filtros são reprojetados na thread da
  interface e trocados sob um `threading.Lock`; o callback de áudio nunca vê
  um filtro "pela metade".
- **Gatilho do osciloscópio** (`analise.indice_gatilho`): começamos o desenho
  numa passagem por zero subindo, como num osciloscópio real, para a onda
  ficar parada na tela.

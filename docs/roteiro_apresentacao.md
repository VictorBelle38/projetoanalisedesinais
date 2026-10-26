# Roteiro de apresentação (~10 minutos)

> **Antes da aula:** rode `instalar.bat` uma vez no notebook (precisa de
> internet), depois `executar.bat` para conferir se o som sai. Leve **fones de
> ouvido** para a demo do microfone e, se possível, uma caixinha de som para a
> turma ouvir os sinais de teste. Atalhos: **Espaço** = tocar/parar,
> **B** = bypass (comparar original × processado).

---

### 1. Visão geral (1 min)

Abra o programa e apresente as 4 áreas da tela:

| Gráfico | O que mostra | Domínio |
|---|---|---|
| Osciloscópio | forma de onda de entrada (cinza) e saída (azul) | tempo |
| Espectro FFT | quanto de cada frequência existe *agora* | frequência |
| Espectrograma | como o espectro muda ao longo do tempo | tempo × frequência |
| Resposta dos filtros | a curva teórica \|H(f)\| que está sendo aplicada | frequência |

Mostre o diagrama da cadeia: entrada → 3 bandas com ganho → soma → notch →
passa-baixas → saída (está em `docs/teoria.md`, seção 5).

### 2. Ruído branco "desenha" os filtros (2 min)

1. Fonte **Teste: Ruído branco** → **Iniciar**.
2. No gráfico FFT, a curva cinza (entrada) é plana: todas as frequências.
3. Mexa no **Ganho GRAVES** (+10 dB) e **AGUDOS** (−20 dB): a curva azul da
   FFT passa a ter o *mesmo formato* da curva branca da resposta teórica.
   → *"A saída é a entrada multiplicada por H(f): Y(f) = H(f)·X(f)."*
4. Ligue o **passa-baixas** e arraste o corte de 20 kHz até 500 Hz: o som fica
   "abafado" e o espectrograma escurece na parte de cima.

### 3. Butterworth × Chebyshev × FIR (2 min)

Volte todos os ganhos a 0 dB (**Restaurar padrões**) e observe a curva branca:

- **Butterworth**: um "calombo" de ~+3 dB nos cruzamentos — as bandas IIR
  têm fases diferentes e não somam perfeitamente.
- **Chebyshev I**: transição mais íngreme, mas com ondulação (*ripple*).
  Aumente a **ordem** de 2 para 8 e veja as quedas ficarem mais verticais.
- **FIR**: perfeitamente plano (0,0 dB). Explicar a inversão espectral:
  h_graves + h_médios + h_agudos = δ → reconstrução perfeita, fase linear.

### 4. Notch removendo uma interferência (2 min)

1. Fonte **Teste: Acorde + apito de 1 kHz**. O apito incomoda; no espectrograma
   aparece como uma **linha horizontal** em 1 kHz e no FFT como um pico.
2. Ligue o **Filtro notch** em 1,00 kHz: o apito some, o acorde continua.
3. Diminua o **Q** para ~2: o entalhe alarga e começa a "comer" a música.
   → *"Q = f0/largura de banda: zeros sobre o círculo unitário, polos logo atrás."*
4. Bônus: **Teste: Ruído + zumbido 60 Hz** e notch em 60 Hz (zumbido da rede
   elétrica).

### 5. Varredura (1 min)

**Teste: Varredura 20 Hz → 20 kHz**: no espectrograma aparece uma linha subindo.
Com o equalizador ligado, ela fica mais clara/escura conforme passa por cada
banda — é a resposta em frequência sendo "percorrida" no tempo.

### 6. Tempo real com microfone (1 min) — **use fones!**

Fonte **Microfone** → fale ou assobie. O assobio aparece como um pico que se
move no FFT. Ligue o notch na frequência do assobio para "apagá-lo".
Comente a latência mostrada no painel (~100 ms com o driver padrão do Windows).

### 7. Música de verdade (1 min)

**Arquivo de áudio** → abra um .mp3. Faça um "bass boost" (graves +10 dB) e
use a tecla **B** para alternar entre original e processado.

---

### Perguntas prováveis

- **Por que SOS e não (b, a)?** Estabilidade numérica em ordens altas
  (`docs/teoria.md` §3).
- **Como não há estalos entre blocos?** O estado dos filtros (`zi` / histórico
  FIR) é mantido entre blocos, e os ganhos mudam em rampa. Os testes
  automáticos provam que processar em blocos = processar o sinal inteiro.
- **Por que a janela de Hann na FFT?** Reduz o vazamento espectral.
- **Qual o custo?** ~0,3 ms (IIR) a ~0,6 ms (FIR) por bloco de 11,6 ms.

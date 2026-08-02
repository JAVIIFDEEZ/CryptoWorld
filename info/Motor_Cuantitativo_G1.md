# Motor cuantitativo — G1: control de multiplicidad

**Brecha corregida:** los controles anti-sobreajuste del generador (PBO y
Deflated Sharpe) estaban mal alimentados, y el número real de pruebas no
entraba en ninguna fórmula.

---

## El problema

El *False Strategy Theorem* (Bailey & López de Prado) dice que el máximo Sharpe
entre N pruebas crece con N **aunque ninguna estrategia tenga edge**. Por eso un
Sharpe reportado sin decir cuántas configuraciones se probaron no significa
nada: el Deflated Sharpe Ratio existe precisamente para corregir el umbral por
`E[max SR₀]`, que depende de N y de la varianza entre los Sharpe de esas pruebas.

El motor implementaba la matemática correctamente, pero la alimentaba mal.
`_neighborhood_matrix` construía la matriz de PBO/DSR con **8-16 vecinos
«jitter» de la campeona ya elegida** — perturbaciones ±10 % de una única
estrategia. Al ser casi clones entre sí:

```
V[{SRₙ}] → 0   ⟹   E[max SR₀] → 0   ⟹   DSR = Φ(algo grande) ≈ 1
```

El DSR salía ≈1 para casi cualquier finalista, y el PBO medía estabilidad
paramétrica local en lugar de sobreajuste de selección. Mientras tanto,
`evaluations` —el N real, disponible en `evolve`— se registraba en el informe y
no entraba en ningún cálculo.

Hay un test que fija este comportamiento para que no vuelva:
`test_near_identical_trials_make_dsr_meaningless` demuestra que con clones el
DSR aprueba (>0.95) un Sharpe que no lo merece, y
`test_diverse_real_trials_discriminate` que con pruebas reales ya no.

---

## Lo implementado

### 1. Registro de las pruebas reales (`TrialRegistry`)

`generate_strategies.py` guarda ahora la serie de retornos de cada genoma
distinto que la búsqueda evalúa. Dos decisiones importan:

- **Muestreo de reservorio, no top-M.** Quedarse con las mejores subestimaría
  `V[{SRₙ}]`, que es justo el término que eleva el umbral: se reproduciría el
  mismo sesgo optimista con otra forma. El reservorio (algoritmo R) da una
  muestra uniforme de todo lo evaluado con memoria acotada (300 series).
- **El recuento va aparte del reservorio.** La deflación usa el número real de
  pruebas —que puede ser de miles—; el reservorio solo aporta la varianza.

Reevaluar un genoma ya visto no cuenta: el GA cachea por hash y una
reevaluación no es una prueba nueva.

### 2. Deflación por el N real

`deflated_sharpe_ratio(returns, trials, n_trials=None)` acepta ahora un recuento
explícito. Omitirlo conserva el comportamiento anterior, de modo que el Camino A
(las 5 estrategias con Optuna, que ya alimentaba bien sus trials) no cambia.

Los genomas que **nunca llegan a operar** quedan fuera de la varianza: su serie
es constante y no tienen Sharpe. Contarlos como un 0 sería inventarse un dato y
ensancharía la dispersión artificialmente, elevando el umbral y castigando de
más a la campeona. Siguen contando en N — la búsqueda gastó esa evaluación.

### 3. N efectivo por agrupamiento

`effective_number_of_trials` agrupa por correlación (enlace simple, |ρ| ≥ 0.9)
las series de las pruebas. Un GA produce muchos genomas casi idénticos;
contarlos como pruebas independientes deflactaría de más y penalizaría a una
campeona legítima por el mero hecho de que la búsqueda exploró a fondo un
vecindario.

### 4. La curva E[max SR₀] frente a N

`expected_max_sharpe_curve` devuelve la curva en escala logarítmica, la posición
de esta ejecución sobre ella y, si procede, a partir de cuántas pruebas el azar
iguala el Sharpe observado. Se muestra en el generador
(`MultipleTestingCard.tsx`) con un veredicto explícito: *supera al azar* / *no se
distingue del azar*.

### 5. El jitter, renombrado a lo que es

Lo que antes alimentaba al PBO es ahora `parameter_sensitivity`: dispersión del
Sharpe entre vecinos, fracción de vecinos en positivo y degradación del vecino
mediano. Es un test de robustez legítimo —el *randomize parameters* de
StrategyQuant— pero mide estabilidad paramétrica, no sobreajuste de selección.

`gate_spec` declara siempre de dónde salen sus números en
`overfitting.source`: `search_trials` (modo válido) o `parameter_jitter`
(repliegue cuando se usa suelto, con aviso explícito de lo que mide y de que el
DSR resultante es optimista por construcción).

---

## Impacto medido

Ejecución del generador sobre la serie sintética de los tests (reversión a la
media, 1 000 velas, preset pequeño):

| | Antes | Después |
|---|---|---|
| Fuente de PBO/DSR | 6 vecinos jitter | 90 genomas evaluados |
| N que deflacta | 6 | 90 (53 independientes) |
| Umbral `E[max SR₀]` | ≈0 | 0.5046 |
| Sharpe/periodo de la campeona | 0.3072 | 0.3072 |
| **DSR** | **≈1** | **0.0** |

El veredicto es internamente coherente: el **mejor** Sharpe observado entre los
90 trials fue 0.4019, por debajo del 0.5046 que predice el azar con 90 intentos.
En esa serie y con ese presupuesto de búsqueda, lo encontrado no se distingue de
haber buscado mucho — y ahora el motor lo dice.

---

## Decisiones de producto

- **El DSR se reporta, no bloquea.** El gating sigue decidiéndose por los checks
  de siempre (trades, lookahead, eficiencia WF, PBO, Monte Carlo). Convertirlo en
  gate duro con el N real dejaría el libro vacío de golpe; primero conviene ver
  los números sobre activos reales. Cuando se decida, es añadir un umbral a
  `GatingThresholds`.
- **N es el de la ejecución en curso**, no acumulado entre corridas. Es
  reproducible y no cambia de valor al re-ejecutar. Acumular por activo es lo que
  pide el *False Strategy Theorem* en sentido estricto y queda para G8, junto con
  el registro persistente de experimentos.

---

## Lo que NO cubre este cambio

G1 corrige de dónde salen los números del control de sobreajuste. Siguen abiertas
las brechas del informe del motor:

- **G2** — validación cruzada purgada y combinatoria (CPCV) en lugar de
  walk-forward simple.
- **G4** — fill al `open[i+1]`, costes en todo el Camino A, market impact.
- **G8** — registro persistente de experimentos y N acumulado por activo.
- **G9** — titular OOS deflactado, «validated» exigiendo holdout.

Nota sobre G9: `_persist` sigue marcando `status="validated"` sin exigir holdout
positivo. Se decidió aplicar el criterio nuevo solo a estrategias futuras cuando
se aborde, sin reclasificar lo ya guardado.

---

## Verificación

```bash
cd backend
pytest tests/unit/domain/test_multiple_testing_control.py   # 19 tests
pytest tests/unit/domain/test_trial_registry.py             # 10 tests
```

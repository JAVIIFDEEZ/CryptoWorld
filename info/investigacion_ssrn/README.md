# Investigación SSRN → CryptoWorld

Paquete de especificación institucional por fases con puertas de decisión.

> **Estado de este directorio.** La versión 1.0 del paquete (30-sep-2026) se
> entregó como un README índice que referencia ocho módulos
> (`01_datos_pit.md` … `08_referencias.md`). **Esos ocho módulos no se han
> recibido.** Sin ellos no se pueden ejecutar con fidelidad las fases F1–F8: las
> especificaciones concretas (D1–D6, I1–I7, C1–C8, V0–V7, P3–P7) viven allí y no
> en el índice.
>
> Lo que sí contenía el índice y se ha ejecutado está en
> [`00_correcciones_f0.md`](00_correcciones_f0.md).

## Qué falta para poder continuar

| Módulo | Contenido según el índice | Fases que bloquea |
|---|---|---|
| `01_datos_pit.md` | Fuentes gratuitas, backfill, grabadores, cadencias, auditoría PIT | F1 |
| `02_instrumento.md` | SPA/RC/StepM, banco de nulos, MCS, multiverso, prerregistro | F2 |
| `03_carry.md` | Carry 2.0: valor justo, banda, venues, riesgos, freno | F4 |
| `04_fragilidad.md` | Índice de fragilidad: componentes, escalera, evaluación | F3 |
| `05_riesgo_sizing.md` | Vol targeting, multiplicador, backtesting de VaR/ES | F5 |
| `06_hipotesis_direccionales.md` | Hipótesis a falsar con su protocolo | F7 |
| `07_producto_usuarios.md` | Funcionalidades de usuario con clasificación MiCA | F6 |
| `08_referencias.md` | Bibliografía anotada, grados e IDs de SSRN | Todas (regla 10) |

La **regla 10** del índice es explícita: «Se cita solo lo que figura en
`08_referencias.md`, con el ID tal cual. Nada de referencias inventadas.» Sin ese
fichero, cualquier cita que se escribiera aquí incumpliría la propia norma del
paquete, así que este directorio no cita IDs de SSRN que no pueda verificar.

## Desviaciones respecto al índice, ya detectadas

1. **El índice analizó v1.337.0.** `develop` está en v1.339.0 y dos entregas
   posteriores solapan con el mapa de decisiones:
   - **1.338.0** añadió predicción conformal al modelo de dirección. No aparece
     en el paquete.
   - **1.339.0** implementó los momentos implícitos de la superficie de opciones
     de Deribit: varianza libre de modelo, risk reversal y butterfly a 25 delta,
     archivado point-in-time y tarea programada. Eso cubre buena parte del ítem
     **#6 del mapa** (*DVOL y skew de Deribit*, P1, F1). Lo que NO cubre es el
     índice DVOL publicado por Deribit como tal.
2. **F0 está parcialmente bloqueada por el entorno.** Su contenido principal
   —correr `edge_test`, `carry_test` y `factor_study` sobre BTC/ETH reales— exige
   red hacia exchanges. El entorno de desarrollo remoto la tiene bloqueada por
   política: Binance, Bybit, OKX, Kraken, CoinGecko, CryptoCompare y Deribit
   responden todas con fallo de proxy. Los tres comandos funcionan y están
   calibrados sobre datos sintéticos con respuesta conocida; el veredicto real
   hay que producirlo donde haya red.

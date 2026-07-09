/**
 * data/learnData.ts — Contenido curado del módulo de aprendizaje (Academia).
 *
 * Dataset pedagógico estático (como las cadenas de i18n): las blockchains más
 * relevantes con sus datos reales (consenso, año, capa, moneda nativa), los
 * puentes/conexiones entre ellas, un temario de lecciones y un glosario. Es la
 * fuente del grafo 3D y del material educativo. No son datos de mercado en vivo
 * — es currículo, por eso vive en el frontend, es determinista y testeable.
 */

export type ChainCategory = 'L1' | 'L2' | 'sidechain'

export interface ChainNode {
  id: string
  name: string
  symbol: string
  category: ChainCategory
  consensus: string
  color: string
  /** Tamaño relativo del ecosistema (0-1) → escala del nodo en el grafo. */
  size: number
  launched: number
  summary: string
  facts: string[]
  /** Cadena en la que liquida (solo L2/sidechain). Genera una arista de liquidación. */
  settlesOn?: string
}

export type BridgeKind = 'settlement' | 'bridge'

export interface BridgeEdge {
  from: string
  to: string
  kind: BridgeKind
  /** Nombre del puente o del mecanismo (Wormhole, WBTC, rollup…). */
  label: string
  note?: string
}

// ── Blockchains ─────────────────────────────────────────────────────

export const CHAINS: ChainNode[] = [
  {
    id: 'bitcoin', name: 'Bitcoin', symbol: 'BTC', category: 'L1',
    consensus: 'Proof of Work', color: '#f7931a', size: 1.0, launched: 2009,
    summary: 'La primera blockchain: un libro contable público y descentralizado que permite transferir valor sin intermediarios. Su seguridad se basa en el trabajo computacional (minería) y su oferta es fija en 21 millones de BTC.',
    facts: [
      'Oferta máxima de 21 millones de BTC, con "halving" del premio cada ~4 años.',
      'Prioriza seguridad y descentralización sobre velocidad (~7 tx/s).',
      'No tiene contratos inteligentes complejos; su rol es "oro digital" y reserva de valor.',
    ],
  },
  {
    id: 'ethereum', name: 'Ethereum', symbol: 'ETH', category: 'L1',
    consensus: 'Proof of Stake', color: '#627eea', size: 0.95, launched: 2015,
    summary: 'La blockchain de contratos inteligentes de referencia: programas que se ejecutan de forma determinista en la EVM. Es la capa de liquidación sobre la que se construye la mayoría de L2 y del ecosistema DeFi/NFT.',
    facts: [
      'Pasó de Proof of Work a Proof of Stake en "The Merge" (2022), reduciendo su consumo energético ~99,95%.',
      'El gas se paga en ETH; parte se quema (EIP-1559), haciendo a ETH potencialmente deflacionario.',
      'La EVM es el estándar de facto: muchas cadenas son "compatibles con EVM".',
    ],
  },
  {
    id: 'solana', name: 'Solana', symbol: 'SOL', category: 'L1',
    consensus: 'PoS + Proof of History', color: '#14f195', size: 0.7, launched: 2020,
    summary: 'Blockchain de alto rendimiento diseñada para miles de transacciones por segundo con comisiones muy bajas, usando Proof of History para ordenar el tiempo de forma criptográfica.',
    facts: [
      'Altísimo rendimiento y comisiones de fracciones de céntimo.',
      'No es compatible con la EVM; usa el lenguaje Rust y su propio modelo de cuentas.',
      'Popular para pagos, NFTs y trading de alta frecuencia on-chain.',
    ],
  },
  {
    id: 'bnb', name: 'BNB Chain', symbol: 'BNB', category: 'L1',
    consensus: 'Proof of Staked Authority', color: '#f0b90b', size: 0.6, launched: 2020,
    summary: 'Cadena compatible con EVM impulsada por Binance, con comisiones bajas y un conjunto reducido de validadores que la hacen rápida a costa de mayor centralización.',
    facts: [
      'Compatible con EVM: las herramientas de Ethereum funcionan casi sin cambios.',
      'Pocos validadores → más rápida y barata pero más centralizada.',
      'BNB se usa para pagar comisiones y en el ecosistema Binance.',
    ],
  },
  {
    id: 'avalanche', name: 'Avalanche', symbol: 'AVAX', category: 'L1',
    consensus: 'Snowman (PoS)', color: '#e84142', size: 0.5, launched: 2020,
    summary: 'Plataforma de contratos inteligentes con finalidad casi instantánea y una arquitectura de "subnets" que permite lanzar blockchains a medida interoperables.',
    facts: [
      'Finalidad en menos de 2 segundos gracias a su familia de consensos Snow*.',
      'Las "subnets" permiten crear cadenas especializadas (juegos, instituciones…).',
      'Su C-Chain es compatible con EVM.',
    ],
  },
  {
    id: 'cardano', name: 'Cardano', symbol: 'ADA', category: 'L1',
    consensus: 'Ouroboros (PoS)', color: '#0033ad', size: 0.45, launched: 2017,
    summary: 'Blockchain construida con un enfoque académico y revisión por pares. Su consenso Ouroboros fue el primer PoS con pruebas de seguridad formales.',
    facts: [
      'Desarrollo guiado por investigación revisada por pares.',
      'Modelo de contabilidad UTXO extendido (eUTXO), distinto al de cuentas de Ethereum.',
      'Enfoque en escalabilidad, sostenibilidad e identidad.',
    ],
  },
  {
    id: 'polkadot', name: 'Polkadot', symbol: 'DOT', category: 'L1',
    consensus: 'Nominated PoS', color: '#e6007a', size: 0.4, launched: 2020,
    summary: 'Un protocolo de blockchains conectadas: una "Relay Chain" central da seguridad compartida a múltiples "parachains" que se comunican entre sí.',
    facts: [
      'Seguridad compartida: las parachains no necesitan su propio conjunto de validadores.',
      'Interoperabilidad nativa entre parachains vía XCM.',
      'Gobernanza on-chain para actualizar el protocolo sin forks.',
    ],
  },
  {
    id: 'cosmos', name: 'Cosmos', symbol: 'ATOM', category: 'L1',
    consensus: 'Tendermint BFT (PoS)', color: '#2e3148', size: 0.4, launched: 2019,
    summary: 'El "internet de las blockchains": un ecosistema de cadenas soberanas que se comunican mediante el protocolo IBC. El SDK de Cosmos facilita lanzar una cadena propia.',
    facts: [
      'IBC (Inter-Blockchain Communication) conecta cadenas de forma nativa y sin custodios.',
      'Cada cadena ("zona") es soberana: elige sus reglas y validadores.',
      'Finalidad instantánea con Tendermint BFT.',
    ],
  },
  {
    id: 'tron', name: 'Tron', symbol: 'TRX', category: 'L1',
    consensus: 'Delegated PoS', color: '#eb0029', size: 0.45, launched: 2018,
    summary: 'Cadena compatible con EVM enfocada en pagos y stablecoins, con comisiones bajas. Es una de las mayores redes por volumen de USDT en circulación.',
    facts: [
      'Gran parte del USDT del mundo circula sobre Tron por sus comisiones baratas.',
      'Delegated PoS con 27 "super representantes" que producen bloques.',
      'Compatible con EVM.',
    ],
  },
  // ── Layer 2 y sidechains sobre Ethereum ──────────────────────────
  {
    id: 'arbitrum', name: 'Arbitrum', symbol: 'ARB', category: 'L2',
    consensus: 'Optimistic Rollup', color: '#28a0f0', size: 0.5, launched: 2021,
    settlesOn: 'ethereum',
    summary: 'Rollup optimista sobre Ethereum: ejecuta las transacciones fuera de la cadena principal y publica los datos en Ethereum, heredando su seguridad con comisiones mucho más bajas.',
    facts: [
      'Asume que las transacciones son válidas salvo prueba de fraude ("optimista").',
      'Comisiones una fracción de las de Ethereum L1.',
      'Totalmente compatible con EVM.',
    ],
  },
  {
    id: 'optimism', name: 'Optimism', symbol: 'OP', category: 'L2',
    consensus: 'Optimistic Rollup', color: '#ff0420', size: 0.42, launched: 2021,
    settlesOn: 'ethereum',
    summary: 'Rollup optimista y hogar de la "OP Stack", el marco de código abierto que usan muchas L2 (incluida Base) para formar la "Superchain".',
    facts: [
      'La OP Stack es el motor compartido de una red de L2 interoperables.',
      'Financia bienes públicos con su modelo de "retroactive funding".',
      'Compatible con EVM.',
    ],
  },
  {
    id: 'base', name: 'Base', symbol: 'ETH', category: 'L2',
    consensus: 'Optimistic Rollup (OP Stack)', color: '#0052ff', size: 0.45, launched: 2023,
    settlesOn: 'ethereum',
    summary: 'L2 construida por Coinbase sobre la OP Stack. No tiene token propio: el gas se paga en ETH. Su cercanía a un gran exchange le dio adopción rápida.',
    facts: [
      'Sin token nativo; usa ETH para el gas.',
      'Construida sobre la OP Stack de Optimism.',
      'Integrada con la infraestructura de Coinbase.',
    ],
  },
  {
    id: 'zksync', name: 'zkSync', symbol: 'ZK', category: 'L2',
    consensus: 'ZK Rollup', color: '#8c8dfc', size: 0.35, launched: 2023,
    settlesOn: 'ethereum',
    summary: 'Rollup de conocimiento cero (ZK): en lugar de asumir validez, publica una prueba criptográfica de que el lote de transacciones es correcto, permitiendo finalidad más rápida que los rollups optimistas.',
    facts: [
      'Usa pruebas de validez (ZK-SNARKs) en vez de pruebas de fraude.',
      'Retiradas hacia L1 más rápidas que en los rollups optimistas.',
      'Hereda la seguridad de Ethereum publicando pruebas en L1.',
    ],
  },
  {
    id: 'polygon', name: 'Polygon', symbol: 'POL', category: 'sidechain',
    consensus: 'PoS (checkpoints a Ethereum)', color: '#8247e5', size: 0.5, launched: 2020,
    settlesOn: 'ethereum',
    summary: 'Escala Ethereum con una cadena PoS compatible con EVM que ancla "checkpoints" periódicos en Ethereum. Evoluciona hacia una familia de soluciones ZK (Polygon 2.0).',
    facts: [
      'Empezó como sidechain PoS; hoy impulsa también rollups ZK.',
      'Comisiones muy bajas y gran ecosistema de dApps.',
      'Su token pasó de MATIC a POL en la transición a Polygon 2.0.',
    ],
  },
]

// ── Puentes y conexiones entre cadenas ──────────────────────────────
// Las aristas de liquidación (L2 → su cadena base) se generan a partir de
// `settlesOn`; aquí solo van los puentes cross-chain explícitos.

export const BRIDGES: BridgeEdge[] = [
  { from: 'bitcoin', to: 'ethereum', kind: 'bridge', label: 'WBTC',
    note: 'Bitcoin "envuelto" (wrapped) como token ERC-20 en Ethereum para usarlo en DeFi.' },
  { from: 'ethereum', to: 'solana', kind: 'bridge', label: 'Wormhole',
    note: 'Puente de mensajes que mueve activos y datos entre Ethereum, Solana y muchas otras.' },
  { from: 'ethereum', to: 'avalanche', kind: 'bridge', label: 'Avalanche Bridge',
    note: 'Transfiere activos entre Ethereum y la C-Chain de Avalanche.' },
  { from: 'ethereum', to: 'bnb', kind: 'bridge', label: 'Binance Bridge',
    note: 'Conecta el ecosistema de Ethereum con BNB Chain.' },
  { from: 'ethereum', to: 'cosmos', kind: 'bridge', label: 'Axelar',
    note: 'Interconecta Ethereum con el ecosistema IBC de Cosmos.' },
  { from: 'ethereum', to: 'polkadot', kind: 'bridge', label: 'Snowbridge',
    note: 'Puente sin confianza (trustless) entre Ethereum y Polkadot.' },
  { from: 'solana', to: 'polygon', kind: 'bridge', label: 'Wormhole',
    note: 'Ruta de activos entre Solana y Polygon a través de Wormhole.' },
  { from: 'avalanche', to: 'bnb', kind: 'bridge', label: 'Multichain-style',
    note: 'Activos que fluyen entre C-Chains compatibles con EVM.' },
]

/** Aristas de liquidación derivadas de `settlesOn` (L2/sidechain → cadena base). */
export function settlementEdges(): BridgeEdge[] {
  return CHAINS.filter((c) => c.settlesOn).map((c) => ({
    from: c.id, to: c.settlesOn as string, kind: 'settlement',
    label: c.consensus,
    note: `${c.name} liquida en ${chainName(c.settlesOn as string)}: publica sus datos/pruebas allí y hereda su seguridad.`,
  }))
}

/** Todas las aristas del grafo (liquidación + puentes). */
export function allEdges(): BridgeEdge[] {
  return [...settlementEdges(), ...BRIDGES]
}

export function chainById(id: string): ChainNode | undefined {
  return CHAINS.find((c) => c.id === id)
}

export function chainName(id: string): string {
  return chainById(id)?.name ?? id
}

/** Conexiones (puentes + liquidación) que tocan una cadena dada. */
export function connectionsOf(id: string): BridgeEdge[] {
  return allEdges().filter((e) => e.from === id || e.to === id)
}

/** Radio del nodo en el grafo 2D (px), escalado por tamaño de ecosistema. */
export function nodeRadius2D(c: ChainNode): number {
  return 9 + c.size * 15
}

// ── Lecciones (contenido educativo) ─────────────────────────────────

export type Level = 'Básico' | 'Intermedio' | 'Avanzado'

export interface LessonSection { heading: string; body: string }
export interface KeyTerm { term: string; def: string }

export interface Lesson {
  id: string
  icon: string
  title: string
  level: Level
  minutes: number
  summary: string
  sections: LessonSection[]
  keyTerms?: KeyTerm[]
}

export const LESSONS: Lesson[] = [
  {
    id: 'que-es-blockchain', icon: '🔗', title: '¿Qué es una blockchain?',
    level: 'Básico', minutes: 5,
    summary: 'El concepto de libro contable distribuido, inmutable y sin intermediarios.',
    sections: [
      { heading: 'La idea central',
        body: 'Una blockchain es un registro de transacciones compartido por miles de ordenadores (nodos). En lugar de que un banco lleve la cuenta, todos los nodos guardan una copia y se ponen de acuerdo sobre cuál es la versión correcta. Nadie tiene que confiar en un intermediario: se confía en las reglas del protocolo y en las matemáticas.' },
      { heading: 'Bloques encadenados',
        body: 'Las transacciones se agrupan en "bloques". Cada bloque incluye una huella criptográfica (hash) del bloque anterior, formando una cadena. Cambiar una transacción antigua rompería todos los hashes siguientes, por lo que el historial es prácticamente inmutable.' },
      { heading: 'Descentralización y consenso',
        body: 'Para añadir un bloque, la red debe llegar a un consenso sobre su validez. Ese mecanismo (Proof of Work, Proof of Stake…) es lo que impide que alguien falsifique el registro o gaste dos veces el mismo dinero.' },
    ],
    keyTerms: [
      { term: 'Nodo', def: 'Ordenador que guarda una copia de la blockchain y valida transacciones.' },
      { term: 'Hash', def: 'Huella digital única de un dato; cualquier cambio produce un hash totalmente distinto.' },
      { term: 'Inmutable', def: 'Que no se puede alterar una vez confirmado.' },
    ],
  },
  {
    id: 'l1-vs-l2', icon: '🧱', title: 'Layer 1 vs Layer 2',
    level: 'Básico', minutes: 6,
    summary: 'Por qué existen las L2 y cómo escalan una cadena base sin sacrificar su seguridad.',
    sections: [
      { heading: 'El trilema de la escalabilidad',
        body: 'Una blockchain busca ser segura, descentralizada y escalable a la vez, pero mejorar una suele empeorar otra. Bitcoin y Ethereum priorizan seguridad y descentralización, lo que limita cuántas transacciones por segundo procesan.' },
      { heading: 'Layer 1: la cadena base',
        body: 'Una Layer 1 (L1) es la blockchain principal: Bitcoin, Ethereum, Solana… Liquida las transacciones por sí misma y define su propia seguridad y consenso.' },
      { heading: 'Layer 2: construir encima',
        body: 'Una Layer 2 (L2) procesa transacciones fuera de la L1 y luego publica un resumen (o una prueba) en ella. Así hereda la seguridad de la L1 pero con comisiones mucho más baratas. Los "rollups" (optimistas o ZK) son el tipo de L2 dominante en Ethereum.' },
    ],
    keyTerms: [
      { term: 'Rollup', def: 'L2 que agrupa muchas transacciones y publica sus datos en la L1.' },
      { term: 'Liquidación', def: 'Registrar de forma definitiva el resultado en la cadena base.' },
    ],
  },
  {
    id: 'consenso', icon: '⚙️', title: 'Consenso: PoW vs PoS',
    level: 'Intermedio', minutes: 7,
    summary: 'Cómo una red sin jefe decide qué transacciones son válidas.',
    sections: [
      { heading: 'Proof of Work (PoW)',
        body: 'Los mineros compiten resolviendo un problema criptográfico costoso; el primero en resolverlo propone el bloque y cobra la recompensa. Falsificar la cadena exigiría rehacer todo ese trabajo, lo que la hace muy segura pero con gran consumo energético. Es el modelo de Bitcoin.' },
      { heading: 'Proof of Stake (PoS)',
        body: 'Los validadores bloquean ("stakean") monedas como garantía. La red elige quién propone el siguiente bloque en función de ese depósito. Si un validador actúa de forma maliciosa, pierde parte de su stake ("slashing"). Consume muchísima menos energía; es el modelo de Ethereum desde 2022.' },
      { heading: 'Compromisos',
        body: 'PoW aporta una seguridad muy probada y una emisión predecible; PoS es eficiente y permite finalidad más rápida, pero concentra poder en quien más monedas tiene. Cada cadena elige su equilibrio.' },
    ],
    keyTerms: [
      { term: 'Staking', def: 'Bloquear monedas como garantía para validar y ganar recompensas.' },
      { term: 'Slashing', def: 'Penalización que quema parte del stake de un validador deshonesto.' },
      { term: 'Finalidad', def: 'Momento en que una transacción se considera irreversible.' },
    ],
  },
  {
    id: 'puentes', icon: '🌉', title: 'Puentes y riesgo cross-chain',
    level: 'Intermedio', minutes: 6,
    summary: 'Cómo se mueven activos entre cadenas y por qué los puentes son un punto delicado.',
    sections: [
      { heading: '¿Por qué hacen falta puentes?',
        body: 'Cada blockchain es un mundo aislado: un BTC no existe "de forma nativa" en Ethereum. Un puente permite mover valor de una cadena a otra, normalmente bloqueando el activo en la cadena de origen y emitiendo una versión "envuelta" (wrapped) en la de destino.' },
      { heading: 'Tipos de puente',
        body: 'Los puentes con custodia dependen de un tercero que guarda los fondos. Los puentes sin confianza (trustless) usan contratos y pruebas criptográficas. Protocolos de mensajería como Wormhole, Axelar o IBC (Cosmos) mueven además datos, no solo tokens.' },
      { heading: 'El riesgo',
        body: 'Los puentes concentran mucho valor y han sido de los objetivos más atacados del sector (cientos de millones robados en varios hackeos). Regla práctica: minimiza el tiempo y la cantidad que mantienes en un puente y prefiere los más auditados.' },
    ],
    keyTerms: [
      { term: 'Wrapped', def: 'Token que representa 1:1 un activo bloqueado en otra cadena (p. ej. WBTC).' },
      { term: 'IBC', def: 'Protocolo nativo de Cosmos para comunicar blockchains sin custodios.' },
    ],
  },
  {
    id: 'wallets', icon: '🔑', title: 'Wallets, claves y autocustodia',
    level: 'Básico', minutes: 5,
    summary: 'Qué guarda realmente una wallet y qué significa "not your keys, not your coins".',
    sections: [
      { heading: 'Claves, no monedas',
        body: 'Una wallet no "contiene" tus criptomonedas: guarda tus claves. La clave pública es como tu número de cuenta (la dirección); la clave privada es la firma que autoriza gastar. Quien controla la clave privada controla los fondos.' },
      { heading: 'Frase semilla',
        body: 'La mayoría de wallets derivan todas tus claves de una "frase semilla" de 12-24 palabras. Si la pierdes, pierdes el acceso para siempre; si alguien la ve, puede vaciarte. Nunca la escribas en un dispositivo conectado ni la compartas.' },
      { heading: 'Custodia vs autocustodia',
        body: 'En un exchange, la plataforma guarda tus claves por ti (custodia). En una wallet propia, las guardas tú (autocustodia): más responsabilidad, pero control total. De ahí el lema "not your keys, not your coins".' },
    ],
    keyTerms: [
      { term: 'Clave privada', def: 'Secreto que autoriza gastar los fondos de una dirección.' },
      { term: 'Frase semilla', def: 'Palabras que reconstruyen todas tus claves; guárdala offline.' },
      { term: 'Autocustodia', def: 'Guardar tú mismo tus claves, sin intermediarios.' },
    ],
  },
  {
    id: 'gas-mev', icon: '⛽', title: 'Gas, comisiones y MEV',
    level: 'Intermedio', minutes: 6,
    summary: 'Qué pagas al enviar una transacción y qué es el valor extraíble por los validadores.',
    sections: [
      { heading: 'El gas',
        body: 'Cada operación en una cadena de contratos consume "gas", una medida del trabajo computacional. La comisión total es gas × precio del gas, y se paga en la moneda nativa (ETH, etc.). Cuando la red está congestionada, el precio del gas sube por subasta.' },
      { heading: 'Prioridad y quema',
        body: 'En Ethereum (EIP-1559) la comisión se divide en una parte base que se quema y una propina para el validador. Pagar más propina prioriza tu transacción.' },
      { heading: 'MEV',
        body: 'El MEV (Maximal Extractable Value) es el beneficio que un validador puede obtener reordenando, incluyendo o excluyendo transacciones dentro de un bloque —por ejemplo, colándose delante de una operación grande. Es una fuerza real que afecta al precio de ejecución en DeFi.' },
    ],
    keyTerms: [
      { term: 'Gas', def: 'Unidad que mide el coste computacional de una transacción.' },
      { term: 'MEV', def: 'Valor que un productor de bloques extrae ordenando transacciones a su favor.' },
    ],
  },
  {
    id: 'defi', icon: '🏦', title: 'DeFi: DEX, préstamos y stablecoins',
    level: 'Intermedio', minutes: 7,
    summary: 'Servicios financieros sin bancos, ejecutados por contratos inteligentes.',
    sections: [
      { heading: 'Exchanges descentralizados (DEX)',
        body: 'Un DEX permite intercambiar tokens sin intermediario mediante "pools de liquidez" y un creador de mercado automático (AMM): el precio lo fija una fórmula según la proporción de activos del pool. Quien aporta liquidez cobra comisiones, pero asume "pérdida impermanente".' },
      { heading: 'Préstamos y colateral',
        body: 'Protocolos como los de préstamo permiten depositar colateral y pedir prestado contra él, todo garantizado por contratos. Si el valor del colateral cae por debajo de un umbral, la posición se liquida automáticamente.' },
      { heading: 'Stablecoins',
        body: 'Son tokens diseñados para valer ~1 dólar. Las hay respaldadas por reservas (USDC, USDT) y algorítmicas (más arriesgadas). Son la "moneda de cuenta" de gran parte de DeFi y de los pagos on-chain.' },
    ],
    keyTerms: [
      { term: 'AMM', def: 'Creador de mercado automático: fija precios con una fórmula, sin libro de órdenes.' },
      { term: 'Pérdida impermanente', def: 'Pérdida relativa de proveer liquidez cuando los precios divergen.' },
      { term: 'Stablecoin', def: 'Token que busca mantener un valor estable, normalmente 1 USD.' },
    ],
  },
  {
    id: 'seguridad', icon: '🛡️', title: 'Seguridad: estafas y cómo evitarlas',
    level: 'Básico', minutes: 5,
    summary: 'Las trampas más comunes en cripto y hábitos que te protegen.',
    sections: [
      { heading: 'Phishing y aprobaciones',
        body: 'Muchos robos no rompen la criptografía: te engañan para que firmes. Un sitio falso te pide "conectar wallet" y aprobar un permiso que le deja gastar tus tokens. Revisa siempre qué estás firmando y revoca aprobaciones que no uses.' },
      { heading: 'Señales de alarma',
        body: 'Rentabilidades "garantizadas", presión para actuar ya, regalos que piden que envíes cripto primero, soporte que te escribe por privado: casi siempre son estafas. Nadie legítimo te pedirá tu frase semilla, jamás.' },
      { heading: 'Hábitos sanos',
        body: 'Usa una wallet fría (hardware) para ahorros, una "caliente" con poco saldo para el día a día, verifica direcciones de contratos en fuentes oficiales y desconfía de los enlaces. La autocustodia es poder, pero exige disciplina.' },
    ],
    keyTerms: [
      { term: 'Phishing', def: 'Engaño para que reveles claves o firmes transacciones maliciosas.' },
      { term: 'Aprobación (approval)', def: 'Permiso que concedes a un contrato para gastar tus tokens.' },
      { term: 'Wallet fría', def: 'Dispositivo sin conexión que guarda tus claves con máxima seguridad.' },
    ],
  },
]

// ── Glosario ────────────────────────────────────────────────────────

export const GLOSSARY: KeyTerm[] = [
  { term: 'Blockchain', def: 'Libro contable distribuido e inmutable mantenido por una red de nodos sin autoridad central.' },
  { term: 'L1 (Layer 1)', def: 'Cadena base que liquida sus propias transacciones (Bitcoin, Ethereum, Solana…).' },
  { term: 'L2 (Layer 2)', def: 'Cadena construida sobre una L1 que hereda su seguridad con comisiones más bajas.' },
  { term: 'Rollup', def: 'L2 que ejecuta transacciones fuera de la L1 y publica sus datos o pruebas en ella.' },
  { term: 'EVM', def: 'Máquina Virtual de Ethereum; estándar que muchas cadenas replican ("compatibles con EVM").' },
  { term: 'Consenso', def: 'Mecanismo por el que la red acuerda el estado válido (PoW, PoS…).' },
  { term: 'Gas', def: 'Medida del coste computacional de una operación; se paga en la moneda nativa.' },
  { term: 'Puente (bridge)', def: 'Protocolo que mueve activos o mensajes entre blockchains distintas.' },
  { term: 'Wrapped', def: 'Token que representa 1:1 un activo bloqueado en otra cadena (p. ej. WBTC).' },
  { term: 'DeFi', def: 'Finanzas descentralizadas: servicios financieros ejecutados por contratos inteligentes.' },
  { term: 'Stablecoin', def: 'Token diseñado para mantener un valor estable, normalmente 1 dólar.' },
  { term: 'Autocustodia', def: 'Guardar tú mismo tus claves privadas, sin intermediarios.' },
]

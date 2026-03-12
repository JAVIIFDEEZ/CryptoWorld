CAPÍTULO 1
Introducción
Para este primer capítulo nos vamos a centrar en introducir el foco de este Trabajo de Fin de Grado, el cual se enmarca en el desarrollo de CryptoWorld, una plataforma web avanzada orientada al seguimiento, análisis técnico y gestión personalizada de operaciones con criptomonedas. Este proyecto ha sido desarrollado con el objetivo de crear una solución educativa y analítica que combine la visualización de datos financieros en tiempo real con herramientas de análisis cuantitativo, permitiendo a sus usuarios gestionar un portafolio de activos, configurar sistemas de alertas y ejecutar indicadores técnicos sobre el mercado.

El sistema ha sido desarrollado adoptando un enfoque moderno y altamente escalable. En la parte del servidor (Backend), se ha utilizado Python como lenguaje principal junto al framework Django y Django REST Framework (DRF) para la construcción de una API robusta. Para la persistencia de datos se ha optado por PostgreSQL como sistema gestor de base de datos relacional. En el lado del cliente (Frontend), se ha implementado una Single Page Application (SPA) haciendo uso de React, TypeScript y Vite. Todo el ecosistema ha sido contenedorizado utilizando Docker para garantizar un despliegue homogéneo.

Para la obtención de los datos de mercado que alimentan el sistema, se emplea la API pública de CoinGecko, la cual proporciona acceso a precios actuales, volúmenes de mercado y variaciones de los activos digitales. Con el fin de garantizar la máxima seguridad en la gestión de cuentas, este proyecto incorpora un avanzado sistema de autenticación, el cual incluye verificación de correo electrónico mediante tokens HMAC, manejo seguro de sesiones mediante tokens JWT (JSON Web Tokens) con lista negra para cierres de sesión controlados, y un sistema de autenticación de múltiple factor (2FA), que requiere que el usuario escanee un código QR y valide su acceso mediante aplicaciones Time-Based One-Time Password (TOTP) como Google Authenticator.

1.1. MOTIVACIÓN
En los últimos años, se ha evidenciado un crecimiento exponencial tanto en el volumen de capitalización como en la variedad de proyectos dentro del ecosistema de los activos digitales. Actualmente existen múltiples plataformas que ofrecen la visualización de gráficos y datos del mercado en tiempo real, pero muchas adolecen de herramientas analíticas que vayan más allá de una simple consulta visual. Al limitarse a mostrar precios, obligan a los inversores (especialmente a los minoristas e inexpertos) a tomar decisiones viscerales en un mercado altamente volátil, o a recurrir a complejas plataformas de trading orientadas a expertos. Aspectos como el análisis técnico algorítmico (indicadores como RSI, MACD o Bandas de Bollinger), junto con simulaciones de portafolio y sistemas de alerta, rara vez se encuentran integrados en un entorno amigable y accesible.

Este desarrollo nace con la motivación de ofrecer una herramienta que, de forma intuitiva, ayude a los usuarios a comprender la profundidad del comportamiento del mercado criptográfico. Además, desde un punto de vista puramente técnico y académico, este proyecto tiene el propósito de aplicar prácticas de ingeniería de software de máxima exigencia. Para ello, en lugar de utilizar patrones convencionales, se ha diseñado el sistema bajo el paradigma de la Clean Architecture (Arquitectura Limpia). Esto garantiza una separación estricta de responsabilidades (SOLID), dividiendo el sistema en capas independientes (Dominio, Aplicación, Infraestructura e Interfaces) que dotan al proyecto de una mantenibilidad, modularidad y testabilidad de primer nivel.

1.2. CONTEXTO
1.2.1. Ecosistema de criptomonedas
Para comprender la relevancia del sistema, es necesario remontarse al año 2009, en el cual aparece Bitcoin como la primera criptomoneda funcional. Desde ese momento, han emergido miles de alternativas, cada una con características técnicas, propósitos y modelos de gobernanza dispares. Las criptomonedas operan sobre la tecnología de cadena de bloques (blockchain), permitiendo la transferencia de valor de manera descentralizada y sin intermediarios financieros. La extrema volatilidad de este mercado global que opera 24/7 lo convierte en un entorno inmensamente dinámico, ideal para el desarrollo de soluciones tecnológicas y de inteligencia de datos.

1.2.2. Plataformas existentes
En la actualidad contamos con referentes del sector como CoinGecko y CoinMarketCap, que permiten realizar consultas instantáneas sobre precios, capitalización de mercado mensual y variaciones porcentuales. No obstante, al concebirse como simples directorios de cotización, relegan el procesamiento matemático a un segundo plano. El desarrollo de CryptoWorld se enfoca no solo en recuperar esta información base, sino en transformarla activamente mediante algoritmos, ofreciendo al usuario la simulación de beneficios/pérdidas (gestión de portafolio) y la aplicación de indicadores matemáticos sobre dichos activos para facilitar proyecciones del comportamiento de activos en la red.

1.2.3. Simulación y análisis personalizado
Este proyecto se diferencia de las alternativas tradicionales por su vocación analítica integral. Ofrece un módulo de análisis técnico algorítmico para calcular indicadores de sobrecompra/sobreventa y fuerza de mercado, permitiendo al usuario almacenar un registro detallado de los análisis ejecutados históricamente. Complementariamente, integrarán lógicas de control del portafolio del propio inversor, y notificará asíncronamente eventos de volatilidad a través de un sistema de alertas personalizadas para una gestión proactiva de los activos seleccionados.

1.2.4. API de CoinGecko
Para alimentar y mantener actualizados los modelos matemáticos y listas de mercado, el sistema utiliza la API proporcionada por CoinGecko. La elección de este proveedor fundamenta en su disponibilidad, fiabilidad y vasto catálogo de miles de criptoactivos catalogados. Al no requerir autenticaciones obstructivas ni costes iniciales para la capa de uso básica, nos proporciona de forma instantánea parámetros clave como el precio de cierre, volumen de mercado 24h, porcentaje de cambio y metadatos históricos fundamentales para la capa analítica de la plataforma.

1.3. ESTRUCTURA DEL DOCUMENTO
A continuación, se describe la organización del presente documento de memoria, detallando el contenido abarcado por cada capítulo:

Capítulo 1: Introducción: Se contextualiza el proyecto, se expone la motivación intrínseca y académica para su realización y se explican los objetivos y decisiones tecnológicas preliminares.

Capítulo 2: Objetivos: Se establece el objetivo principal del sistema y se enumeran los objetivos parciales (funcionales y no funcionales) que permiten estructurar, guiar y evaluar el éxito del desarrollo.

Capítulo 3: Estado del Arte: Se analizan de forma crítica las tecnologías vigentes, las plataformas de la competencia en el ecosistema criptográfico y los paradigmas arquitectónicos (como la Clean Architecture e infraestructuras Dockerizadas) que avalan la viabilidad e innovación técnica del TFG.

Capítulo 4: Metodología: Se expone la metodología de trabajo iterativa para el desarrollo informático, los principios de diseño de software (p.ej. principios SOLID), así como el desglose de la arquitectura en capas y el stack tecnológico utilizado, tanto a nivel de servidor como del SPA renderizado en cliente.

Capítulo 5: Resultados: Se describe con profundidad técnica el proceso seguido para la implementación de cada módulo crítico: sistemas de doble factor de autenticación (2FA), gestión asíncrona de seguridad mediante tokens JWT, integración de bases de datos PostgreSQL, y casos de uso del análisis de mercado. Asimismo, se exhiben y analizan los resultados de los tests unitarios y de integración de las entidades de dominio y endpoints implementados.

Capítulo 6: Conclusiones: Se reflexiona sobre el cumplimiento de los parámetros del proyecto y los conocimientos profesionales asimilados. Se evalúa globalmente la solución propuesta y, para concluir, se exponen futuras líneas de investigación y ampliaciones para enriquecer iterativamente la plataforma en escenarios de producción a gran escala.






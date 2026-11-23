---
norma: "Guía práctica de datos volátiles y CCAA: IRAV, Zonas Tensionadas y Fianzas"
ambito: ES_CCAA
temas: [irav, actualizacion_renta, zona_tensionada, gran_tenedor, fianza, ccaa, irpf]
fecha_revision: 2026-11-23
---

# Datos Volátiles y Normativa por Comunidades Autónomas (España)

## 1. Índice de Referencia para la Actualización de Rentas (IRAV - INE)

### Regla general según fecha de firma del contrato de vivienda habitual
- **Contratos firmados a partir del 26 de mayo de 2023 (entrada en vigor de la Ley 12/2023):**
  - La actualización anual de la renta (siempre que exista cláusula expresa de actualización en el contrato, Art. 18 LAU) tiene como límite máximo el **IRAV** publicado mensualmente por el Instituto Nacional de Estadística (INE), salvo pacto de un porcentaje inferior.
  - Nota importante: el porcentaje mensual exacto del IRAV varía cada mes. Si el usuario necesita el dato numérico exacto del último mes publicado, indícale que consulte el último valor oficial publicado en `ine.es` (apartado IRAV) y **no inventes un porcentaje concreto**.
- **Contratos firmados antes del 26 de mayo de 2023:**
  - Siguen rigiéndose por el índice pactado en el contrato (habitualmente **IPC** o **IGC**, con los topes extraordinarios que estuvieron vigentes en 2022-2024 y las reglas que resulten aplicables según la redacción vigente de la LAU y disposiciones transitorias).
- **Si el contrato NO tiene cláusula expresa de actualización de renta (Art. 18.1 LAU):**
  - En contratos celebrados tras el 1 de abril de 2015, **no se puede actualizar la renta anualmente** durante la vigencia del contrato.

## 2. Zonas de Mercado Residencial Tensionado y Lógica Exacta de "Gran Tenedor" (Art. 3.k Ley 12/2023)

*(Nota: la definición parte del Art. 3.k de la Ley 12/2023, pero algunos umbrales en zona tensionada y criterios interpretativos pueden variar según la Comunidad Autónoma o reformas legales posteriores; contrastar siempre con `01_Normativa_Estatal_Vigente` y la resolución autonómica aplicable).*

### Tabla comparativa: Gran Tenedor vs. No Gran Tenedor (Pequeño Tenedor)
| Característica | Gran Tenedor | No Gran Tenedor (Pequeño Tenedor) |
| :--- | :--- | :--- |
| **Regla general (toda España)** | Persona física o jurídica titular de **más de 10 inmuebles** urbanos de uso residencial (**11 o más**) **O** de una superficie construida de **más de 1.500 m²** de uso residencial. | Persona física o jurídica titular de **10 o menos** inmuebles residenciales **Y** que no supere los **1.500 m²** construidos de uso residencial. |
| **En Zona Tensionada (si la CCAA rebaja el umbral)** | Titular de **5 o más inmuebles** urbanos de uso residencial ubicados dentro de la misma zona declarada tensionada (criterio aplicado, por ejemplo, en Cataluña). | Titular de **menos de 5 inmuebles** (1 a 4) en esa zona tensionada. |
| **Quién puede serlo** | Tanto **personas físicas** (particulares) como **personas jurídicas** (empresas/SL). | Tanto personas físicas como jurídicas por debajo de los umbrales. |

### Qué cuenta y qué NO cuenta para el cálculo (Matices clave)
- **Excluidos expresamente:** Los **garajes y trasteros** NO cuentan ni como inmuebles ni para los 1.500 m². Tampoco cuentan los **locales comerciales, oficinas o naves industriales** (solo computa el uso residencial).
- **Vivienda habitual del propietario:** La ley no la excluye, por lo que la propia vivienda habitual del propietario **sí computa** dentro del total de inmuebles residenciales.
- **Copropiedad (proindivisos / herencias):** Si el propietario comparte un piso (ej. 50 % con su pareja o 33 % con hermanos), a efectos de los **1.500 m²** se computa la superficie proporcional a su cuota; a efectos del **número de inmuebles**, existe litigiosidad y disparidad entre Audiencias Provinciales y CCAA (unas exigen titularidad plena y otras valoran el porcentaje de participación). Advertir siempre este matiz si hay proindivisos.

### Efectos críticos de ser Gran Tenedor vs. Pequeño Tenedor
1. **Precio del alquiler en zona tensionada:** Al **pequeño tenedor** que vuelve a alquilar una vivienda ya alquilada en los últimos 5 años se le topa la renta al contrato anterior; al **gran tenedor** se le aplica obligatoriamente el límite del **Índice de Referencia (SERPAVI)** si resulta más bajo.
2. **Desahucios (Art. 439.6 LEC):** Para admitir a trámite una demanda de desahucio de un **gran tenedor**, este debe acreditar previamente si el inquilino es vulnerable y haber pasado por un procedimiento obligatorio de **conciliación o intermediación** ante la Administración (trámite no exigido al pequeño tenedor).
3. **Prórroga extraordinaria por vulnerabilidad (Art. 10.2 LAU):** Si el inquilino acredita vulnerabilidad social y económica, el gran tenedor está obligado a aceptar la prórroga extraordinaria.

### Regla de pertinencia en el triaje (CRÍTICO)
- **Si la vivienda NO está en zona tensionada:** el estatus de gran tenedor **NO limita el precio de un nuevo contrato** tras la extinción legal del contrato anterior. Por tanto, en consultas de subida de renta o fijación de renta de un nuevo contrato en municipios fuera de zona tensionada, **NO se debe preguntar si el propietario es gran tenedor** (solo preguntar si hay desahucio o vulnerabilidad acreditada).

### Mapa orientativo de Zonas Tensionadas por Comunidad Autónoma
*(Nota: la declaración de zona tensionada depende de resoluciones autonómicas publicadas en el BOE/diarios autonómicos y del registro del Ministerio de Vivienda - MIVAU; si un municipio es dudoso, adviértelo al usuario para confirmarlo en el visor oficial del MIVAU).*

- **Comunidades Autónomas con municipios declarados en zona tensionada:**
  - **Cataluña:** amplia declaración vigente en gran parte de sus municipios (incluyendo Barcelona y su área metropolitana, Girona, Tarragona, Lleida y numerosos municipios urbanos). Umbral de gran tenedor rebajado a 5 viviendas en zona tensionada.
  - **País Vasco:** declaración progresiva por municipios (ej. Errenteria, Donostia/San Sebastián, Bilbao y otros municipios con resolución publicada).
  - **Navarra:** municipios declarados por el Gobierno de Navarra (ej. Pamplona y comarca).
  - **Galicia:** declaración municipal puntual (ej. A Coruña, sujeta a vigencia de resolución).
  - **Asturias:** trámites/declaraciones municipales puntuales (verificar resolución vigente en BOPA/MIVAU).
- **Comunidades Autónomas que NO han declarado zonas de mercado residencial tensionado (salvo resolución posterior publicada en BOE):**
  - **Comunidad de Madrid**
  - **Andalucía**
  - **Comunidad Valenciana**
  - **Región de Murcia**
  - **Aragón**
  - **Castilla y León**
  - **Castilla-La Mancha**
  - **Extremadura**
  - **Cantabria**
  - **La Rioja**
  - **Illes Balears**
  - **Canarias**

## 3. Organismos Autonómicos de Depósito de Fianzas (Referencia Rápida)

La fianza legal obligatoria en vivienda habitual es de **1 mensualidad** (Art. 36.1 LAU) y, en la mayoría de CCAA, el propietario debe depositarla ante el organismo autonómico correspondiente (generalmente en el plazo de 1 a 2 meses desde la firma):

- **Comunidad de Madrid:** Agencia de Vivienda Social (AVS, antiguo IVIMA). Plazo: 30 días hábiles.
- **Cataluña:** Institut Català del Sòl (INCASÒL). Plazo: 2 meses.
- **Comunidad Valenciana:** Generalitat Valenciana (Conselleria de Hacienda / modelo 806). Plazo: 15 días hábiles.
- **Andalucía:** Agencia de Vivienda y Rehabilitación de Andalucía (AVRA). Plazo: 1 mes.
- **País Vasco:** Servicio Bizilagun (Gobierno Vasco). Plazo: 1 mes.
- **Galicia:** Instituto Galego da Vivenda e Solo (IGVS). Plazo: 1 mes.
- **Aragón:** Dirección General de Vivienda del Gobierno de Aragón. Plazo: 2 meses.
- **Castilla y León:** Cámara de la Propiedad Urbana / Junta de Castilla y León. Plazo: 1 mes.
- **Castilla-La Mancha:** Junta de Comunidades de Castilla-La Mancha. Plazo: 1 mes.
- **Illes Balears:** Institut Balear de l'Habitatge (IBAVI). Plazo: 30 días.
- **Canarias:** Instituto Canario de la Vivienda (ICAVI). Plazo: 1 mes.
- **Extremadura:** Junta de Extremadura (Caja General de Depósitos). Plazo: 1 mes.
- **Asturias / Cantabria / Navarra / Murcia / La Rioja:** En varias de estas comunidades el depósito autonómico obligatorio está exento o tiene régimen específico (verificar en la consejería autonómica si el usuario pregunta por el trámite exacto).

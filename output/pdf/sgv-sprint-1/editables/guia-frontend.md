# SGV INCUBUNT · Guía Frontend para el Sprint 1

Material de orientación preparado el 30 de septiembre de 2026. Alcance: las **nueve tareas de la imagen adjunta**. Fuente funcional: *Plan de Inicio del Proyecto SGV (1).pdf*, 63 páginas. Los números de página de esta guía corresponden al PDF adjunto. Las pantallas son propuestas funcionales; no son diseños oficiales ni una aplicación implementada. Todos los datos ilustrativos son ficticios.

## Mensaje para abrir la reunión

«Estamos construyendo la intranet de INCUBUNT para que la información de sus voluntarios y gestiones tenga continuidad. Este sprint debe permitir entrar de forma segura, administrar cuentas dentro de la jerarquía autorizada, seleccionar una gestión y consultar las fichas. Frontend convierte esas reglas en recorridos comprensibles: pantallas, formularios, estados y permisos. Backend decide y valida las reglas; UI/UX define el diseño final. Podemos avanzar con datos de prueba y vistas temporales desde el primer día.»

## 1. Qué problema resuelve el SGV

El sistema centraliza información y enlaza las herramientas que las áreas ya usan. Conserva la trayectoria de voluntarios entre gestiones, ordena la operación y permite seguimiento de proyectos, horas y desempeño. No exige trasladar todas las herramientas existentes al SGV. El dominio previsto en el plan es `intranet.incubunt.com`; no se ha comprobado su despliegue. [pp. 1-3]

Para este sprint, el recorrido principal es:

1. Una persona autorizada crea una cuenta según su jerarquía.
2. El destinatario activa la cuenta con un enlace de un solo uso y Google.
3. Inicia sesión con el correo registrado y ve navegación acorde a permisos.
4. Un voluntario consulta su ficha; un gestor autorizado busca y consulta las de su ámbito.
5. Se trabaja en una gestión y periodo explícitos.
6. Un gestor autorizado marca Inactivo o Retirado y verifica los efectos sin borrar historia.

El historial de proyectos puede aparecer como información de la ficha si Backend lo entrega. Crear, aprobar, pausar y gestionar proyectos no figura entre las nueve tareas de tu captura. El plan original sí lo contempla en su Sprint 1: es una diferencia de alcance que debe quedar registrada, no una tarea añadida automáticamente. [pp. 56-58]

## 2. Conceptos que todos deben distinguir

| Concepto | Qué significa | Consecuencia para Frontend |
|---|---|---|
| Voluntario | Registro institucional con DNI obligatorio y único. Puede existir sin cuenta. | Mostrar cuenta «Sin cuenta» sin tratarlo como error. Mantener ID de ficha separado de ID de usuario. |
| Usuario | Cuenta de acceso, correo Google, políticas y estado de activación. | Tener cuenta activa no sustituye el estado institucional del voluntario. |
| Área base | Pertenencia organizacional. | Filtra el ámbito autorizado; no concede automáticamente roles de proyecto. |
| Cargo institucional | Autoridad dentro de la organización, vinculada a gestión. | Alimenta las políticas de Backend; no codificar toda la jerarquía en botones. |
| Rol de proyecto | Función operativa en una iniciativa. | Es distinto al cargo de área. Un DP no puede crear cuentas según el catálogo. |
| Gestión | Año/contexto institucional al que pertenecen registros y cargos. | Mostrarlo de forma persistente y enviar su identificador al consultar o mutar. |
| Periodo | Q1, Q2, Q3 o Cierre dentro de una gestión. | Las fechas exactas son configuración, no constantes inventadas. |
| PBAC | Acceso según políticas y contexto: persona, área, gestión, recurso. | Consumir capacidades del servidor; ocultar acciones y datos no autorizados. |
| Sesión sensible | Permiso temporal adicional para operaciones críticas. | No sustituye PBAC. Mostrar contador y posibilidad de finalizar. |

Fuentes: pp. 1, 4-8, 16-17, 39-44. El esquema de vínculo Usuario-Ficha debe pactarse con Backend: el plan permite ficha sin cuenta, pero no precisa todas las cardinalidades.

## 3. Alcance y tareas listas para orientar al equipo

Las nueve filas siguientes corresponden literalmente a la captura. Las subtareas Frontend y criterios de aceptación son una propuesta derivada del plan.

### T1. Inicializar aplicación

**Resultado:** base navegable React + TypeScript + Inertia + Tailwind en el proyecto SGV. [pp. 18-28, 55-57]

**Frontend:** crear los layouts y páginas prototipo de la web; preparar navegación por permisos; componentes Button, Input, Select, Badge, DataTable, EmptyState, ErrorState, FormTabs y mensajes de éxito. Mostrar gestión/periodo y zona del banner sensible. Establecer tipos y fixtures de desarrollo.

**Backend/UI/UX:** Backend configura Laravel/Inertia, sesión y props compartidas; UI/UX entrega tokens, componentes y revisión de diseño. No se ha inspeccionado un repositorio SGV: el workspace de esta conversación es Promption, otro proyecto.

**Aceptación:** arranque reproducible documentado; páginas públicas y privadas separadas; navegación por teclado; vista móvil sin pérdida de acciones; sin errores de consola; fixtures claramente identificados y sin datos personales reales. Las acciones visibles dependen de `auth.can`, no de un rol escrito en el componente.

### T2. Crear modelo de datos y migraciones

**Resultado:** datos consistentes para las pantallas. La migración es responsabilidad Backend. Frontend entrega el contrato TypeScript y verifica escenarios. [pp. 16-17, 20-28, 37, 43-44]

**Frontend:** pactar User, Volunteer, Management, Period, catálogos de áreas/roles, permisos por registro, paginación y filtros. Acordar `null`, fechas con zona horaria, errores y campos restringidos. Fixtures: voluntario con cuenta, sin cuenta, pendiente de activación, inactivo, retirado, otra área, sin métricas e historial de otra gestión.

**Aceptación:** DNI único obligatorio en servidor; correo de cuenta único; fichas sin cuenta válidas; estado de usuario separado de estado de voluntario; registros vinculados a gestión; datos sensibles ausentes del payload cuando no se permite consultarlos. Un contrato estable permite trabajar sin esperar cada migración.

### T3. Crear usuario según jerarquía

**Pantallas:** lista de usuarios y formulario de creación; estado pendiente de activación y confirmación sensible. Auditoría de solo lectura como soporte del requisito, con alcance de vista pactado. [pp. 7, 41-43]

**Frontend:** nombres, apellidos, correo Google, rol y área/subárea. Backend entrega las opciones de rol permitidas para el actor y contexto. Si existe ficha, mostrar vínculo opcional mediante selector autorizado; esta selección es propuesta de contrato, no detalle definido por el plan. Usar `useForm`, errores por campo, botón en procesamiento, éxito y retorno a lista.

**Jerarquía del documento:** Administrador puede crear roles base; Presidente crea Vicepresidente, Coordinador General, Director de Área y DP; Director de Área crea Subdirector de su área y DP; los demás no crean usuarios. No deducir que DP crea voluntarios de las flechas del diagrama de p. 3: el catálogo y el flujo detallado dicen que no crea usuarios. El creador del rol genérico Voluntario no queda claramente resuelto: confirmar con PO antes de habilitarlo. [pp. 4-6, 41-42]

**Aceptación:** sin permiso no se muestra creación; acceso directo es rechazado por servidor; roles ajenos al ámbito no son opciones válidas; correo repetido muestra error preservando formulario; doble clic no duplica; Backend crea pendiente, audita y envía activación de 72 h. Una falla del correo debe reflejar el estado real y no provocar creación repetida. Reenvío de invitación queda pendiente de acuerdo, no se promete en este sprint.

### T4. Iniciar sesión con Google

**Pantallas:** Login, Activación y resultados de acceso. [pp. 2, 7, 12, 16, 41-42]

**Frontend:** una llamada a continuar con Google; el servidor inicia OAuth y resuelve callback. No hay formulario de contraseña ni autorregistro. Aceptar cuentas Gmail o institucionales siempre que su correo coincida con el registrado. Activación con enlace de 72 h y Google vinculado; token de un solo uso.

**Aceptación:** cuenta activa registrada accede; correo no registrado, cuenta desactivada, activación pendiente, OAuth cancelado y token inválido/vencido/usado tienen mensajes y siguiente paso claros. No consumir ni invalidar el token únicamente por visitar la pantalla: Backend decide al completar correctamente la activación. El origen de un 401, un 403 y un fallo de red debe distinguirse sin mostrar detalles internos.

### T5. Configurar gestión y periodos

**Pantalla:** configuración con gestión/año y filas Q1, Q2, Q3 y Cierre; selector de contexto en la app. [pp. 1, 11, 16, 39]

**Frontend:** mostrar gestión seleccionada, nombres y fechas de periodos, formulario de guardado para actor autorizado, errores y confirmación de éxito. Backend entrega catálogos y permisos. La RACI señala Administrador responsable y Presidente aprobador; no define un workflow de aprobación de configuración. No implementar ese workflow sin acuerdo.

**Aceptación propuesta:** fin no anterior a inicio, periodos dentro de gestión y validación de solapamientos por servidor; un cambio de gestión actualiza consultas, fichas y capacidades y advierte antes de perder un formulario modificado. Las reglas de solapamiento, unicidad de gestión activa y edición de gestiones cerradas requieren ratificación del PO: no están detalladas en el plan. No generar fechas de Q1/Q2/Q3/Cierre por suposiciones.

### T6. Consultar mi ficha

**Pantalla:** `Volunteers/MyProfile` propuesta, reutilizando la ficha de detalle en modo propio. [pp. 5-8, 43-44]

**Frontend:** identidad/foto, DNI, correo, código universitario, carrera, ciclo, área y estado; trayectoria por gestión; tabs autorizadas de métricas/proyectos/sanciones/información restringida. Es consulta: no añadir edición de perfil ni carga de foto solo por existir campos.

**Aceptación:** la identidad consultada la decide el servidor desde sesión; manipular IDs no permite ver a otra persona; sin ficha vinculada muestra un vacío útil para contactar al responsable; métricas no disponibles no se presentan como cero; sección restringida y sanciones solo aparecen si la política lo permite. El documento restringe sanciones a GTH, Presidencia y Directores, por lo que no se asume que VOL ve esa tab. [p. 45]

### T7. Buscar y filtrar voluntarios

**Pantalla:** directorio paginado. [pp. 8, 27-28, 43-44; los filtros concretos son propuesta]

**Frontend:** buscar por nombre o DNI según autorización; filtrar gestión, área y estado institucional; mostrar nombre, área, estado de voluntario y estado de cuenta en columnas separadas. Usar filtros autorizados desde Backend, paginación del servidor y parámetros URL cuando sea adecuado. Proponer búsqueda con pausa breve para evitar una consulta por tecla.

**Aceptación:** filtros combinan y se pueden limpiar; filtrar reinicia página; conteos representan resultados autorizados; cambio rápido no deja una respuesta anterior en pantalla; resultados cero muestran cómo ajustar filtros; error permite reintentar conservando filtros; director no obtiene datos de otra área. No descargar todo el padrón para filtrarlo en cliente. No incluir datos de salud en el listado.

### T8. Aplicar efectos de inactividad o retiro

**Pantalla:** acción desde ficha, con diálogo de confirmación y resultado. [p. 44]

**Frontend:** mostrar estado actual y destino, resumen de consecuencias, cancelar/confirmar, estado procesando y actualización de ficha/lista tras éxito. Mostrar botón solo si Backend autoriza el cambio para ese voluntario.

**Regla expresa:** al pasar a Inactivo o Retirado se desvinculan asignaciones operativas y se desactiva la cuenta si existe. Se preserva el historial por gestión. Backend ejecuta los efectos como operación consistente; Frontend no encadena llamadas independientes para cada efecto ni informa éxito parcial como total.

**Aceptación:** cancelar no cambia datos; sin cuenta el cambio sigue siendo válido; tras éxito se muestran estado actualizado, cuenta desactivada y asignaciones desvinculadas; repetir una petición no repite efectos; rechazo o conflicto conserva datos y permite recargar. Probar en integración que una sesión previa del afectado pierde acceso. Si el gestor pierde permisos tras cambiar contexto, servidor rechaza y UI lo explica.

**Punto por acordar:** por implicar desactivación de cuenta, proponer sesión sensible para esta transición y confirmar con PO/Backend cómo se aplica a fichas sin cuenta. El plan define ambos mecanismos, pero no une explícitamente este caso al catálogo de acciones sensibles. Motivo, fecha efectiva y reactivación del voluntario tampoco están definidos; no imponerlos ni incluir reactivación por defecto.

### T9. Consultar ficha integral

**Pantalla:** detalle autorizado de un voluntario con tabs. [pp. 8, 43-45]

**Frontend:** identidad/foto; métricas diferenciadas presencial, virtual y asistencia a reuniones virtuales de área; proyectos y rol; sanciones si autorizadas; información restringida si autorizada; trayectoria por gestión. Reutilizar la misma composición que «Mi ficha» con capacidades y campos distintos.

**Aceptación:** ID inexistente presenta 404 útil; ID fuera del ámbito presenta acceso denegado; no hay fuga en props, HTML o precarga de tabs restringidas; «sin datos», «sin permiso» y «módulo aún no disponible» se distinguen. Las sanciones y métricas tienen desarrollo posterior en el roadmap: este sprint consulta información existente si se entrega; no implementa registros de sanciones ni cálculo de IncuPoints. Definir con PO qué tabs quedan disponibles ahora, en lugar de simular datos productivos. [pp. 58-62]

## 4. Seguridad que hay que representar en la interfaz

Hay **tres tiempos distintos**: activación de cuenta **72 horas**; enlace de confirmación sensible **10 minutos**; sesión elevada **15 minutos**. Son reglas expresas del plan. [pp. 6-7, 40-42]

Flujo de una acción sensible:

1. Comprobar capacidad del actor para el recurso desde las props; el servidor vuelve a comprobarla.
2. Si la sesión sensible está vigente, enviar la operación.
3. Si no lo está, conservar el borrador, mostrar confirmación por correo y solicitarla al servidor.
4. El servidor valida el enlace de un solo uso y habilita 15 minutos; mostrar banner y botón «Finalizar sesión sensible».
5. Resolver la operación pendiente según el mecanismo pactado con Backend. El plan señala que se completa al confirmar; no disparar dos POST desde callback y página original. Usar un identificador de intención/operación y protección frente a duplicados como propuesta técnica.
6. Al caducar o revocar, el próximo intento vuelve a requerir confirmación. Calcular contador con tiempo del servidor y resincronizar al volver a la pestaña; no conceder permiso por el reloj del navegador.

La vigencia normal de la sesión de acceso no se especifica: no confundir sus límites con los 15 minutos. Distinguir `can` estructural de sesión elevada; si Backend expone permisos finales que incluyen elevación, acordar cómo detectar elegibilidad para pedir confirmación.

Para datos sensibles, **ocultar una tab no basta**: Backend no debe mandar sus campos a un usuario sin permiso. Salud, emergencia y notas de clima requieren una política explícita antes de mostrarse. Auditoría es consulta inmutable; se propone vista básica como soporte de T3, sin añadir edición/desactivación general de usuarios si no está comprometida.

## 5. Cómo se conectan Frontend y Backend

Arquitectura definida por el plan: Laravel enruta y valida; el controlador delega a una Action; retorna una página Inertia o redirección; React consume props. No hace falta diseñar una API REST aparte para este sprint. [pp. 18-29, 55-56]

- Pantallas en `resources/js/Pages/{Slice}/`, layouts en `Layouts/`, componentes en `Components/`, tipos compartidos en `Types/`.
- Navegación con Inertia; formulario con `useForm`, `errors` y `processing`. Errores del FormRequest aparecen en el flujo de validación de Inertia. La semántica exacta de respuestas/estados se pacta con Backend.
- Sesión, OAuth, CSRF, tokens, auditoría, filtros autorizados y efectos de estado pertenecen al servidor.
- Props: actor autenticado, capacidades, contexto, sesión sensible, catálogos y datos de la página. Las capacidades por ficha se entregan por recurso.
- Rutas nuevas son **propuesta**, no URLs verificadas: Login, Users/Index, Users/Create, Managements/Index, Volunteers/Index, Volunteers/MyProfile y Volunteers/Show. Los enlaces auth presentes en el plan no prueban que estén desplegados.
- Ver `contratos-propuestos.ts` para la conversación del Día 1; no copiarlo como contrato aprobado.

### Contrato mínimo por pantalla

| Pantalla | Datos que necesita | Qué envía / qué hace |
|---|---|---|
| Login / Activación | Resultado OAuth, estado de activación, enlace de inicio suministrado por servidor | Redirige a Google vía Backend; informa token vencido/usado |
| Users/Create | Roles creables, áreas/subáreas permitidas, sesión sensible | Nombres, apellidos, email, rol, ámbito, vínculo opcional con ficha |
| Users/Index / Audit | Usuarios autorizados; bitácora de lectura si se acuerda | Consulta paginada, filtros autorizados |
| Managements/Index | Gestiones, periodos, permisos, errores | Datos de configuración; cambio de contexto |
| Volunteers/Index | Registros paginados, filtros, catálogos y capacidades por fila | Búsqueda, filtros, página |
| Volunteers/MyProfile | Ficha propia y campos/tabs autorizados | Consulta y cambio de gestión |
| Volunteers/Show | Ficha autorizada, campos/tabs y acciones por recurso | Consulta; cambio de estado autorizado |
| Confirmación sensible | Estado de intención, expiraciones, resultado | Solicita enlace, continúa intención una sola vez, revoca elevación |

## 6. Orden de ejecución y colaboración

El plan propone 10-11 días calendario por sprint y máximo 10 h semanales por estudiante. Es un techo, no disponibilidad garantizada. No se conoce el tamaño ni la disponibilidad del equipo; no se asignan nombres, puntos ni fechas ficticias. [pp. 53-56]

| Momento relativo | Frontend | Coordinación / salida |
|---|---|---|
| Día 1 | Contratos, fixtures, layouts, componentes mínimos | Backend entrega props de prueba; UI/UX prioriza acceso y ficha; PO resuelve ambigüedades de permisos |
| Días 2-4 | Login/activación, shell, lista y creación de usuarios, elevación | Un recorrido demostrable de acceso y creación; revisar estados de error |
| Días 4-7 | Gestión/periodos, directorio, ficha compartida y transición | Trabajar por capacidad disponible; integrar cada caso completo |
| Días 8-10/11 | Integración, estilos de Figma, QA y correcciones | Demostración y validación con stakeholders; dejar feedback para siguiente sprint |

Distribución sugerida por bloques, adaptable al número real de personas: **Base y acceso** (T1/T3/T4 + sesión sensible), **Contexto y consultas** (T5/T6/T7/T9), **Transición e integración** (T8 + QA). T2 se acuerda entre ambos equipos desde Día 1. Cada bloque tiene una persona responsable y una revisora, aunque una misma persona cubra varios bloques. No imponer ejecución simultánea si la capacidad no alcanza.

Para evitar bloqueos: primero acordar props con ejemplos válidos y de error; construir vistas provisionales; integrar Backend por flujo; aplicar Figma; revisar diseño y aceptación. Reservar tiempo real para revisión, aprendizaje y transferencia. Si el alcance no cabe en disponibilidad declarada, presentar el avance y replanificar con PO; la estimación del documento no garantiza la capacidad.

## 7. Definition of Done del sprint

- Las nueve tareas tienen evidencia verificable; T2 se valida con Backend, no solo con interfaces TypeScript.
- Permisos probados con al menos Admin/Presidente, Director de Área y Voluntario, además de persona sin autorización. Rol genérico Voluntario se prueba con cuenta de fixture creada por mecanismo acordado.
- Flujo completo de invitación, activación, acceso y creación sensible probado con correo/OAuth de entorno de pruebas.
- Ficha sin cuenta y sin datos funciona; no hay valores inventados ni métricas falsas.
- Filtros y páginas respetan contexto; cambios de gestión no mezclan historiales ni conservan capacidades obsoletas.
- Inactivo/Retirado tiene efectos comprobados en servidor y revoca acceso de la cuenta vinculada según contrato.
- Loading, vacío, error, éxito y denegación cubiertos; errores no borran formularios o filtros; envíos duplicados controlados.
- Formularios con etiquetas, foco de diálogo, teclado y mensajes legibles; estado no comunicado solo por color. Verificación recomendada en móvil y escritorio.
- Typecheck/build/lint del proyecto SGV según los comandos que adopte; smoke y pruebas de flujos con QA. No se ejecutaron pruebas SGV en esta entrega de orientación.
- Pull request revisada, instrucciones de ejecución y decisiones documentadas; fixtures distinguidos de datos reales; integración sin errores de consola.

## 8. Casos de QA y guion de demo

| Caso | Resultado esperado | Tareas |
|---|---|---|
| Google registrado y activo | Accede a navegación autorizada | T1/T4 |
| Correo no registrado / cuenta desactivada | Acceso denegado y siguiente paso claro | T4/T8 |
| Activación vencida o ya usada | Mensaje útil, sin nueva cuenta ni activación indebida | T3/T4 |
| Director intenta crear rol presidencial | UI no lo ofrece; servidor rechaza petición manipulada | T3 |
| Correo repetido / doble envío | Error visible / una creación | T3 |
| Token sensible >10 min; elevación >15 min | Token rechazado / se solicita nueva confirmación | T3 |
| Gestión cambia con formulario modificado | Advertencia y estado consistente | T5 |
| Búsqueda combinada sin resultados | Vacío útil; limpiar filtros | T7 |
| Ficha sin cuenta y sin métricas | Muestra «Sin cuenta» y «Sin datos» | T6/T9 |
| URL de ficha fuera del ámbito | Denegado, sin payload sensible | T7/T9 |
| Inactivar con cuenta; retirar sin cuenta | Efectos correctos y conservación de historia | T8 |
| Servidor falla durante transición | No mostrar éxito; recargar para conocer estado real | T8 |

**Reunión de orientación sugerida, 35 min:** 5 min propósito y conceptos; 5 min alcance/jerarquía; 10 min pantallas y recorridos; 10 min contratos y tareas; 5 min responsables y dudas. Esta es una reunión de arranque, distinta a la validación de cierre.

**Demo de cierre propuesta, 20 min:** entrar y mostrar permisos (3 min); creación con confirmación sensible y activación (5 min); cambiar gestión y revisar periodos (3 min); buscar, consultar ficha propia/integral y ficha sin cuenta (5 min); inactivar/retirar y verificar historia/acceso (4 min). Continuar con feedback y siguiente sprint según la sesión de 30-45 min del plan. [p. 55]

## 9. Decisiones que deben resolverse, sin frenar trabajo independiente

| Decisión | Por qué importa | Quién la resuelve | Mientras tanto |
|---|---|---|---|
| Quién crea cuentas de Voluntario genérico | Catálogo jerárquico no lo explicita; no conceder autoridad inventada | PO + Backend | Fixture; no habilitar rol sin política |
| Permisos de sección sensible y ficha propia | Información sensible y sanciones tienen restricciones | PO + GTH + Backend | Omitir campos/tabs no autorizados |
| Quién marca Inactivo/Retirado y si exige elevación | Efectos sobre cuenta; alcance por área/gestión | PO + GTH + Backend | Contrato de capacidad por recurso |
| Fechas y reglas de periodos; edición de gestiones cerradas | Documento enumera periodos, no toda su validación | PO + Admin + Backend | Diseñar formulario con catálogos de prueba |
| Estado «Selección»/«En Selección» y «Retirado»/«Egresado» | Variantes del texto entre pp. 8 y 44 | PO + GTH | Backend entrega códigos/etiquetas canónicos |
| Qué datos hay ahora en métricas/proyectos/sanciones | Backend de varios módulos es posterior | PO + Backend | Estado «Aún no disponible», sin cifras ficticias |
| Persistencia de acción pendiente al abrir correo | Evitar perder formulario o duplicar operaciones | Frontend + Backend | Mock de estados de intención |
| Alcance de lista/auditoría dentro de T3 | Requisito transversal del plan, sin tarjeta separada en captura | PO + Backend | Vista mínima de lectura propuesta |

## 10. Material visual y fuentes

`briefing-frontend-sprint-1.pdf` contiene 20 láminas para proyectar: contexto, alcance, modelo conceptual, permisos, arquitectura, pantallas propuestas, transición, seguridad y ejecución. La carpeta `imagenes/` incluye imágenes de las láminas para incorporar a una reunión o herramienta de diseño.

Los colores y distribución de los wireframes son provisionales. UI/UX decide tokens y estilo final. Las acciones y campos deben permanecer sujetos al contrato aprobado.

**Trazabilidad:** visión y alcance pp. 1-3; actores pp. 4-6; OAuth, seguridad y auditoría pp. 6-7 y 40-43; ficha, estados y efectos pp. 8 y 43-45; arquitectura y componentes pp. 18-28; gestiones/periodos pp. 1, 11, 16 y 39; trabajo Frontend y roadmap pp. 53-63. La imagen de tareas define el alcance específico de esta guía. Las instrucciones de proceso del documento se presentan como contenido del plan, no como autorización para enviar correos, modificar otros proyectos o desplegar aplicaciones.

VER EL ESQUEMA DE COLORES DE INCU.

RESULTADO:
- JHEZZER, NAHUEL y 

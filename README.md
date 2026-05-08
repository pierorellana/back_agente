# Backend Agente IA

Backend en Python con FastAPI y una estructura inspirada en arquitectura hexagonal.

## Estructura

```text
app/
├── api/                 # Adaptador de entrada HTTP: routers, deps y handlers
├── application/         # Casos de uso, servicios de aplicacion, puertos y DTOs
├── domain/              # Entidades, reglas de negocio y errores del dominio
├── infrastructure/      # Adaptadores externos: config y clientes Notion
└── main.py              # Punto de entrada FastAPI
```

## Principios

- `api` no contiene reglas de negocio.
- `application` coordina casos de uso y depende de puertos, no de detalles externos.
- `domain` no depende de FastAPI ni librerias de infraestructura.
- `infrastructure` implementa los puertos definidos por la aplicacion.

## Instalacion

```bash
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements/base.txt
```

## Variables de entorno

Copia `.env.example` a `.env` y ajusta los valores necesarios.

```env
APP_NAME=backend-agente-ia
APP_DEBUG=false
NOTION_TOKEN=ntn_xxxxxxxxx
NOTION_ROOT_PAGE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
NOTION_VERSION=2026-03-11
NOTION_TABLES_MAP_PATH=config/notion_tables.json
```

## Ejecucion

```bash
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Notion connection check: http://localhost:8000/api/notion/connection
- Notion tables discovery: http://localhost:8000/api/notion/tables/discover
- Care estimate flow: POST http://localhost:8000/api/care-estimates
- Insurance providers: http://localhost:8000/api/insurance-providers
- Insurance plans: http://localhost:8000/api/insurance-plans
- Users: http://localhost:8000/api/users
- Specialties: http://localhost:8000/api/specialties
- Hospitals: http://localhost:8000/api/hospitals
- Symptoms: http://localhost:8000/api/symptoms
- Hospital specialties: http://localhost:8000/api/hospital-specialties
- Symptom specialty map: http://localhost:8000/api/symptom-specialty-map
- Insurance network: http://localhost:8000/api/insurance-network
- Emergency keywords: http://localhost:8000/api/emergency-keywords

Los endpoints de catalogos usan `GeneralResponse`, y `data` contiene directamente el arreglo:

```json
{
  "success": true,
  "message": "Insurance providers loaded",
  "data": [
    {
      "provider_id": "prov_bluecare",
      "provider_name": "BlueCare Health"
    }
  ],
  "error": null
}
```

## Endpoint principal del hackathon

El flujo principal para Angular es:

```text
POST /api/care-estimates
```

Request:

```json
{
  "document_number": "0922334455",
  "symptom_text": "Tengo dolor en el pecho y me cuesta respirar."
}
```

Resumen del flujo:

```text
Buscar paciente -> validar plan activo -> revisar EMERGENCY_KEYWORDS ->
inferir especialidad con Gemini -> calcular copago -> rankear top 3 hospitales ->
redactar recomendacion -> guardar historial en Notion
```

## Tablas de Notion recomendadas para el MVP

Mantener:

- `USERS`
- `INSURANCE_PLANS`
- `SPECIALTIES`
- `HOSPITALS`
- `SYMPTOM_SPECIALTY_MAP`
- `COVERAGES`
- `INSURANCE_NETWORK`
- `CONSULTATION_PRICES`
- `EMERGENCY_KEYWORDS`
- `ESTIMATION_HISTORY`

Opcionales o prescindibles para este MVP:

- `INSURANCE_PROVIDERS`
- `SYMPTOMS`
- `HOSPITAL_SPECIALTIES`

La implementacion nueva ya no depende de esas 3 tablas opcionales para resolver el flujo principal.

## Gemini

Para este MVP se usa `gemini-2.5-flash` por defecto. Solo se utiliza para:

- interpretar el texto libre del paciente
- elegir una especialidad probable entre las especialidades validas de Notion
- redactar la explicacion final en lenguaje natural

Si `GEMINI_API_KEY` no esta configurado, el backend hace fallback a reglas basadas en
`SYMPTOM_SPECIALTY_MAP` y a una explicacion deterministica.

## Mapa de tablas de Notion

Si la pagina de Notion contiene varias tablas, sincroniza el mapa con:

```bash
curl -X POST http://localhost:8000/api/notion/tables/sync
```

Esto crea `config/notion_tables.json` con el `database_id`, `data_source_id` y propiedades de cada tabla encontrada.

## Tests

```bash
pytest
```

## Siguiente paso

Cuando definas el flujo del backend, agrega cada modulo siguiendo este recorrido:

```text
api/router -> application/use_case -> application/port -> infrastructure/adapter
                         |
                         v
                      domain
```
